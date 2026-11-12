"""Binding relocation preserves identity, old source and explicit TEST acceptance."""
import json
import unittest
from urllib.parse import urlsplit

from aidp_agent_flow.project import FlowError, private_json
import test_native_lifecycle as fixtures
from test_native_lifecycle import FakeHTTP, FakeResponse


class RebindHTTP(FakeHTTP):
    def __init__(self):
        super().__init__()
        self.etag = "agent-before"
        self.provide_etag = True
        self.timeout_before_put = False
        self.timeout_after_put = False
        self.before_put = None

    def request(self, method, url, **arguments):
        route = urlsplit(url).path
        if method == "PUT":
            self.calls.append({"method": method, "url": url, "headers": arguments["headers"],
                               "payload": json.loads(arguments["data"])})
            if self.before_put:
                self.before_put()
            if self.timeout_before_put:
                raise TimeoutError("private provider body")
            if not route.endswith("/agents/agent-one") or ("if-match" in arguments["headers"] and arguments["headers"]["if-match"] != self.etag):
                return FakeResponse(status=412)
            payload = json.loads(arguments["data"])
            if set(payload) != {"entryFilePath", "dependenciesFilePath"}:
                raise AssertionError("Rebind attempted an unrelated metadata change")
            self.agents[0].update(payload)
            self.etag = "agent-after"
            if self.timeout_after_put:
                raise TimeoutError("private provider body")
            return FakeResponse(self.agents[0])
        response = super().request(method, url, **arguments)
        if method == "GET" and route.endswith("/agents/agent-one") and self.provide_etag:
            response.headers["etag"] = self.etag
        return response


class NativeRebindTests(unittest.TestCase):
    tearDown = fixtures.NativeLifecycleTests.tearDown
    instance = fixtures.NativeLifecycleTests.instance
    seed_package = fixtures.NativeLifecycleTests.seed_package
    bound_instance = fixtures.NativeLifecycleTests.bound_instance
    posts = fixtures.NativeLifecycleTests.posts

    def setUp(self):
        fixtures.NativeLifecycleTests.setUp(self)
        self.http = RebindHTTP()
        self.config["native"].update(agent_key="agent-one", metadata_root=self.config["native"]["remote_root"])
        self.selected = self.instance(bound=True)
        self.http.agents = [{**self.selected._binding(), "key": "agent-one",
            "entryFilePath": "/Workspace/legacy/agent.py",
            "dependenciesFilePath": "/Workspace/legacy/requirements.txt"}]
        self.old_files = {"/Workspace/legacy/agent.py": b"original entry",
                          "/Workspace/legacy/requirements.txt": b"original dependencies",
                          "/Workspace/legacy/old_module.py": b"original module"}
        self.http.objects.update(self.old_files)
        self.http.tests = [self.http.deployment()]

    def puts(self):
        return [call for call in self.http.calls if call["method"] == "PUT"]

    def staged(self):
        plan = self.selected.rebind()
        self.selected.sync_package(apply=True, for_rebind=True)
        return plan

    def test_read_only_plan_keeps_actual_metadata_and_creates_no_journal(self):
        plan = self.selected.rebind()
        self.assertFalse(plan["applied"])
        self.assertTrue(plan["etag_present"])
        self.assertFalse(plan["metadata_moved"])
        self.assertEqual(plan["binding_before"]["pathInfo"], plan["binding_after"]["pathInfo"])
        self.assertNotEqual(plan["binding_before"]["entryFilePath"], plan["binding_after"]["entryFilePath"])
        self.assertTrue(all(call["method"] == "GET" for call in self.http.calls))
        self.assertFalse(self.selected.journal.exists())

    def test_separate_metadata_plan_is_read_only_and_apply_rejects_before_effects(self):
        self.selected.metadata_root = "/Workspace/legacy"
        self.http.agents[0]["pathInfo"] = "/Workspace/legacy"
        plan = self.selected.rebind()
        self.assertFalse(plan["applied"])
        self.http.calls.clear()
        with self.assertRaisesRegex(FlowError, "metadata_root and remote_root"):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertEqual(self.http.calls, [])
        self.assertFalse(self.selected.journal.exists())

    def test_rebind_requires_staged_bytes_and_current_plan(self):
        plan = self.selected.rebind()
        with self.assertRaisesRegex(FlowError, "package bytes differ"):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.assertEqual(self.puts(), [])
        self.selected.sync_package(apply=True, for_rebind=True)
        with self.assertRaisesRegex(FlowError, "current binding_sha256"):
            self.selected.rebind(apply=True, expected_binding="stale")
        self.assertEqual(self.puts(), [])

    def test_rebind_records_intent_before_conditional_put_and_invalidates_old_test_receipt(self):
        plan = self.staged()
        self.selected.state["test_receipt"] = {"package_sha256": "old"}
        def intent_exists():
            record, = [record for _, record in self.selected._intents() if record["kind"] == "rebind"]
            self.assertEqual(record["state"], "SUBMITTED")
            self.assertEqual(record["binding_before"]["entryFilePath"], "/Workspace/legacy/agent.py")
        self.http.before_put = intent_exists
        result = self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.assertTrue(result["binding_verified"])
        self.assertTrue(result["test_refresh_required"])
        self.assertFalse(result["native_test_accepted"])
        self.assertFalse(result["old_source_deleted"])
        self.assertEqual(len(self.puts()), 1)
        self.assertEqual(self.http.agents[0]["pathInfo"], self.selected.remote_root)
        self.assertEqual(self.http.agents[0]["computeKey"], "compute-one")
        self.assertEqual(self.http.agents[0]["key"], "agent-one")
        self.assertNotIn("test_receipt", self.selected.state)
        self.assertTrue(all(self.http.objects[path] == raw for path, raw in self.old_files.items()))
        self.assertTrue(all(record["state"] == "RECONCILED" for _, record in self.selected._intents()))
        self.assertFalse(self.selected.rebind(apply=True)["applied"])
        self.assertEqual(len(self.puts()), 1)

    def test_lost_reply_after_put_is_reconciled_without_resubmission(self):
        plan = self.staged()
        self.http.timeout_after_put = True
        with self.assertRaises(FlowError):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.assertEqual(len(self.puts()), 1)
        self.assertFalse(self.selected.rebind(apply=True)["applied"])
        self.assertEqual(len(self.puts()), 1)
        self.assertTrue(all(record["state"] == "RECONCILED" for _, record in self.selected._intents()))

    def test_unknown_put_that_has_not_changed_binding_blocks_retry(self):
        plan = self.staged()
        self.http.timeout_before_put = True
        with self.assertRaises(FlowError):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        with self.assertRaisesRegex(FlowError, "pending or uncertain"):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.assertEqual(len(self.puts()), 1)

    def test_active_production_or_creating_deployment_blocks_staging_and_rebind(self):
        for kind, state in (("PROD", "ACTIVE"), ("TEST", "CREATING")):
            with self.subTest(kind=kind):
                row = self.http.deployment(kind)
                row["lifecycleState"] = state
                self.http.prod = [row] if kind == "PROD" else []
                self.http.tests = [row] if kind == "TEST" else [self.http.deployment()]
                with self.assertRaises(FlowError):
                    self.selected.rebind()
                with self.assertRaises(FlowError):
                    self.selected.sync_package(apply=True, for_rebind=True)
                self.assertEqual(self.posts() + self.puts(), [])

    def test_staging_refuses_conflicting_files_and_foreign_code_ownership(self):
        remote = self.selected.remote_root + "/agent.py"
        self.http.objects[remote] = b"foreign bytes"
        with self.assertRaisesRegex(FlowError, "absent or identical"):
            self.selected.sync_package(apply=True, for_rebind=True)
        self.assertEqual(self.http.objects.pop(remote), b"foreign bytes")
        self.http.agents.append({"key": "foreign", "pathInfo": "/Workspace/unrelated-metadata",
                                 "entryFilePath": self.selected.remote_root + "/other/entry.py"})
        with self.assertRaisesRegex(FlowError, "overlaps another agent"):
            self.selected.sync_package(apply=True, for_rebind=True)
        self.assertEqual(self.posts() + self.puts(), [])

    def test_pending_write_in_another_context_for_same_agent_blocks_rebind(self):
        path = self.root / ".aidp-local/native/another/intents/pending.json"
        private_json(path, {"agent_key": "agent-one", "state": "SUBMITTED", "target_context": "another"})
        with self.assertRaisesRegex(FlowError, "Another native context"):
            self.selected.rebind()
        self.assertEqual(self.puts(), [])

    def test_missing_etag_or_changed_metadata_is_not_silently_adopted(self):
        plan = self.staged()
        self.http.provide_etag = False
        with self.assertRaisesRegex(FlowError, "ETag"):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.http.agents[0]["pathInfo"] = "/Workspace/foreign"
        with self.assertRaisesRegex(FlowError, "metadata location"):
            self.selected.rebind()
        self.assertEqual(self.puts(), [])

    def test_rebind_finalization_recovers_across_each_local_write_boundary(self):
        from unittest.mock import patch
        for boundary in ("_save_state", "_reconciled"):
            with self.subTest(boundary=boundary):
                # Each independent fixture keeps the failure boundary unambiguous.
                if boundary == "_reconciled":
                    self.http.agents[0].update(entryFilePath="/Workspace/legacy/agent.py",
                        dependenciesFilePath="/Workspace/legacy/requirements.txt")
                    self.http.etag = "another-before"
                plan = self.staged()
                self.selected.state["test_receipt"] = {"package_sha256": plan["package_sha256"],
                    "deployments": self.selected._snapshot(self.http.tests)}
                self.selected._save_state()
                with patch.object(self.selected, boundary, side_effect=OSError("simulated interruption")):
                    with self.assertRaises(OSError):
                        self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
                count = len(self.puts())
                resumed = self.instance(bound=True)
                self.assertFalse(resumed.rebind(apply=True)["applied"])
                self.assertNotIn("test_receipt", resumed.state)
                self.assertIn("rebind_receipt", resumed.state)
                self.assertEqual(len(self.puts()), count)
                self.assertTrue(all(record["state"] == "RECONCILED" for _, record in resumed._intents()))
                self.selected = resumed

    def test_normal_sync_protects_foreign_code_with_separate_metadata(self):
        plan = self.staged()
        self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        remote = self.selected._binding()["entryFilePath"]
        original = self.http.objects[remote]
        entry = self.root / self.config["agent"]["entry"]
        entry.write_text(entry.read_text() + "\n# Proposed revision.\n")
        self.http.agents.append({"key": "foreign", "pathInfo": "/Workspace/foreign-metadata",
                                 "entryFilePath": remote})
        count = len(self.posts())
        with self.assertRaisesRegex(FlowError, "overlaps another agent"):
            self.selected.sync_package(apply=True)
        self.assertEqual(len(self.posts()), count)
        self.assertEqual(self.http.objects[remote], original)

    def test_staging_rechecks_conflicting_bytes_before_upload(self):
        from unittest.mock import patch
        target = self.selected._binding()["entryFilePath"]
        original = self.selected._object
        reads = 0
        def changed_target(remote, **arguments):
            nonlocal reads
            if remote == target:
                reads += 1
                if reads == 2:
                    self.http.objects[target] = b"concurrent target bytes"
            return original(remote, **arguments)
        with patch.object(self.selected, "_object", side_effect=changed_target):
            with self.assertRaisesRegex(FlowError, "changed during staging"):
                self.selected.sync_package(apply=True, for_rebind=True)
        self.assertEqual(self.http.objects[target], b"concurrent target bytes")
        self.assertFalse(any(call["headers"].get("path") == target for call in self.posts()))
        self.assertEqual(self.http.agents[0]["entryFilePath"], "/Workspace/legacy/agent.py")

    def test_cli_dispatches_rebind_and_explicit_staging(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import Mock, patch
        from aidp_agent_flow.cli import main, parser
        from aidp_agent_flow import native_lifecycle
        flags = parser().parse_args(["native", "rebind", "--apply", "--expected-binding", "reviewed"])
        self.assertEqual(flags.expected_binding, "reviewed")
        for arguments, method, expected in (
            (["native", "rebind"], "rebind", {"apply": False, "expected_binding": None, "allow_no_etag": False}),
            (["native", "sync", "--for-rebind", "--apply"], "sync_package", {"apply": True, "for_rebind": True}),
        ):
            selected = Mock()
            getattr(selected, method).return_value = {"action": method, "applied": False}
            with patch("aidp_agent_flow.cli.load_project", return_value=(self.root, self.config)), \
                    patch.object(native_lifecycle, "NativeLifecycle", return_value=selected), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--project", str(self.root), "--json", *arguments]), 0)
            getattr(selected, method).assert_called_once_with(**expected)
            selected.close.assert_called_once_with()

    def test_staging_never_writes_inside_the_prior_source_tree(self):
        self.config["native"]["remote_root"] = "/Workspace/legacy/new"
        selected = self.instance(bound=True)
        with self.assertRaisesRegex(FlowError, "prior source tree"):
            selected.sync_package(apply=True, for_rebind=True)
        self.assertEqual(self.posts() + self.puts(), [])


    def test_explicit_missing_etag_updates_with_readback_and_journal(self):
        self.http.provide_etag = False
        plan = self.staged()
        result = self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertTrue(result["binding_verified"])
        self.assertEqual(result["concurrency_control"], "explicit_readback_without_cas")
        self.assertNotIn("if-match", self.puts()[0]["headers"])
        record = [row for _, row in self.selected._intents() if row["kind"] == "rebind"][0]
        self.assertEqual(record["concurrency_control"], "explicit_readback_without_cas")

    def test_opt_in_still_uses_etag_and_rejects_malformed_value(self):
        plan = self.staged()
        self.http.etag = "bad\nvalue"
        with self.assertRaisesRegex(FlowError, "valid observed"):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertEqual(self.puts(), [])
        self.http.etag = "valid"
        self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertEqual(self.puts()[0]["headers"]["if-match"], "valid")

    def test_no_etag_rechecks_record_version_before_put(self):
        from unittest.mock import patch
        self.http.provide_etag = False
        self.http.agents[0]["version"] = 2
        plan = self.staged()
        original = self.selected._source_agent
        reads = 0
        def changed():
            nonlocal reads
            reads += 1
            if reads == 2:
                self.http.agents[0]["version"] = 3
            return original()
        with patch.object(self.selected, "_source_agent", side_effect=changed):
            with self.assertRaisesRegex(FlowError, "changed before"):
                self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertEqual(self.puts(), [])

    def test_no_etag_lost_reply_reconciles_without_second_put(self):
        self.http.provide_etag = False
        plan = self.staged()
        self.http.timeout_after_put = True
        with self.assertRaises(FlowError):
            self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"], allow_no_etag=True)
        self.assertFalse(self.selected.rebind(apply=True, allow_no_etag=True)["applied"])
        self.assertEqual(len(self.puts()), 1)

    def test_failed_test_requires_explicit_recovery_without_creating_an_agent(self):
        # Failed-deployment recovery is measured on a metadata-aligned fixture.
        self.selected.metadata_root = self.selected.remote_root
        self.http.agents[0]["pathInfo"] = self.selected.remote_root
        plan = self.staged()
        self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        self.http.tests[0]["lifecycleState"] = "FAILED"
        with self.assertRaisesRegex(FlowError, "ACTIVE TEST"):
            self.selected.test_refresh(apply=True)
        result = self.selected.test_refresh(apply=True, recover_failed=True)
        self.assertTrue(result["submitted"])
        deployments = [c for c in self.posts() if c["url"].endswith("/deployments/actions/redeploy")]
        self.assertEqual(len(deployments), 1)
        self.assertFalse(any(c["url"].endswith("/agents") for c in self.posts()))

    def test_recovery_does_not_bypass_creating_or_unknown_state(self):
        plan = self.staged()
        self.selected.rebind(apply=True, expected_binding=plan["binding_sha256"])
        for state in ["CREATING", "UNKNOWN", "CANCELED"]:
            self.http.tests[0]["lifecycleState"] = state
            with self.assertRaises(FlowError):
                self.selected.test_refresh(apply=True, recover_failed=True)

    def test_file_upload_accepts_exact_non_json_echo_and_checks_readback(self):
        original = self.http.request
        def echoed(method, url, **arguments):
            response = original(method, url, **arguments)
            if method == "POST" and arguments.get("headers", {}).get("type") == "FILE":
                response.content = arguments["data"]
                response.headers["content-type"] = "application/x-yaml"
            return response
        self.http.request = echoed
        result = self.selected.sync_package(apply=True, for_rebind=True)
        self.assertTrue(result["readback_verified"])
        records = [record for _, record in self.selected._intents() if record["kind"] == "file"]
        self.assertTrue(records)
        self.assertTrue(all(r["state"] == "RECONCILED" for r in records))

if __name__ == "__main__":
    unittest.main()
