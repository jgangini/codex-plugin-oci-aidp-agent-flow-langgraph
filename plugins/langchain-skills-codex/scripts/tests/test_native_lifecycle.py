from aidp_agent_flow.identity import execution_identity
import hashlib
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from aidp_agent_flow import __version__
from aidp_agent_flow import native_lifecycle as lifecycle
from aidp_agent_flow.native_lifecycle import NativeLifecycle
from aidp_agent_flow.packaging import inspect_package
from aidp_agent_flow.project import FlowError, initialize, load_project
from aidp_agent_flow.project import canonical_hash, private_json
from aidp_agent_flow.progress import record_test_review


class FakeResponse:
    def __init__(self, value=None, status=200, headers=None, raw=False):
        self.status_code = status
        self.headers = headers or {}
        self.content = value if raw else json.dumps(value if value is not None else {}).encode()


class FakeHTTP:
    def __init__(self):
        self.calls, self.agents, self.tests, self.prod = [], [], [], []
        self.objects, self.operations, self.sessions = {}, {}, {}
        self.timeout_post = False
        self.drift_upload = False
        self.page_forever = False
        self.session_state = "ACTIVE"
        self.closed = False

    def close(self):
        self.closed = True

    def deployment(self, kind="TEST", version=1):
        row = {"key": kind.lower() + "-deployment", "deploymentType": kind,
               "deploymentVersion": version, "lifecycleState": "ACTIVE"}
        if kind == "TEST":
            row.update(agentFlowKey="agent-one", agentFlowComputeKey="compute-one",
                       endpointUrl="https://test-endpoint.oci.oraclecloud.com/invoke")
        else:
            row.update(agentKey="agent-one", agentComputeKey="compute-one")
        return row

    def complete_deployment(self, kind="TEST", version=1):
        for operation in self.operations.values():
            operation["status"] = "SUCCEEDED"
        if kind == "TEST":
            self.tests = [self.deployment("TEST", version)]
        else:
            self.prod = [self.deployment("PROD", version)]

    def request(self, method, url, *, data, headers, timeout, allow_redirects):
        parsed = urlsplit(url)
        route = parsed.path[parsed.path.index("/workspaces/"):] if "/workspaces/" in parsed.path else "/asyncOperations/" + parsed.path.rsplit("/", 1)[-1]
        query = parse_qs(parsed.query)
        payload = json.loads(data) if headers.get("Content-Type") == "application/json" else None
        self.calls.append({"method": method, "route": route, "url": url, "payload": payload,
                           "data": data, "headers": headers, "timeout": timeout, "redirects": allow_redirects})
        if method == "POST" and self.timeout_post:
            raise TimeoutError("DO-NOT-PRINT provider body")
        if method == "GET":
            if route.endswith("/objects"):
                root = query.get("path", [None])[0]
                objects = {}
                for remote, content in self.objects.items():
                    if not remote.startswith(root + "/"):
                        continue
                    relative = remote[len(root) + 1:]
                    first = relative.split("/", 1)[0]
                    objects[root + "/" + first] = "FOLDER" if "/" in relative or (content == b"" and "." not in first) else "FILE"
                return FakeResponse({"items": [{"path": path, "type": kind} for path, kind in sorted(objects.items())]})
            if "/objects/" in route:
                remote = unquote(route.split("/objects/", 1)[1])
                return FakeResponse(self.objects[remote], raw=True) if remote in self.objects else FakeResponse(status=404)
            if route == "/workspaces/workspace-one/agents":
                page = int(query.get("page", ["0"])[0])
                if self.page_forever:
                    return FakeResponse({"items": []}, headers={"opc-next-page": str(page + 1)})
                batch = self.agents[page * 100:(page + 1) * 100]
                next_page = {"opc-next-page": str(page + 1)} if len(self.agents) > (page + 1) * 100 else {}
                return FakeResponse({"items": batch}, headers=next_page)
            if route.endswith("/agentFlowDeployments"):
                if query.get("deploymentType") != ["TEST"] or query.get("agentFlowKey") != ["agent-one"]:
                    raise AssertionError("Unscoped TEST list")
                return FakeResponse({"items": self.tests})
            if route.endswith("/deployments"):
                return FakeResponse({"items": self.prod})
            if "/sessions/" in route:
                key = route.rsplit("/", 1)[-1]
                return FakeResponse(self.sessions[key])
            if route.startswith("/asyncOperations/"):
                return FakeResponse(self.operations[route.rsplit("/", 1)[-1]])
            if "/agents/" in route:
                key = route.rsplit("/", 1)[-1]
                return FakeResponse(next(item for item in self.agents if item["key"] == key))
        if method == "POST":
            if route.endswith("/objects"):
                self.objects[headers["path"]] = b"DRIFTED" if self.drift_upload and headers["type"] == "FILE" else data or b""
                return FakeResponse()
            if route == "/workspaces/workspace-one/agents":
                self.agents.append({**payload, "key": "agent-one"})
                return FakeResponse({"key": "agent-one"})
            if route.endswith("/agentFlowSessions"):
                key = "session-one"
                self.sessions[key] = {"key": key, "agentKey": "agent-one", "agentComputeKey": "compute-one",
                                      "endpointUrl": self.tests[0]["endpointUrl"], "lifecycleState": self.session_state}
                return FakeResponse({"key": key})
            if route.endswith("/redeployAgentFlow") or "/deployments/actions/" in route:
                key = "operation-" + str(len(self.operations) + 1)
                self.operations[key] = {"key": key, "actionType": "DEPLOY_AGENT", "resourceType": "AGENT", "status": "IN_PROGRESS"}
                return FakeResponse({"lifecycleState": "CREATING"}, headers={"datalake-async-operation-key": key})
        raise AssertionError("Unexpected fake request")


class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        observed_python = patch("aidp_agent_flow.identity.python_path", return_value=Path(sys.executable))
        observed_python.start()
        self.addCleanup(observed_python.stop)
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Fixture agent", sync=False)
        _, self.config = load_project(self.root)
        self.config["native"] = {"endpoint": "https://aidp.region-one.oci.oraclecloud.com", "platform_id": "platform-one",
            "workspace_key": "workspace-one", "compute_key": "compute-one", "display_name": "FixtureAgent",
            "remote_root": "/Workspace/fixture/agent"}
        self.http = FakeHTTP()

    def tearDown(self):
        self.temporary.cleanup()

    def instance(self, bound=False):
        if bound:
            self.config["native"]["agent_key"] = "agent-one"
        return NativeLifecycle(self.root, self.config, transport=self.http)

    def seed_package(self):
        package = inspect_package(self.root)
        folder = self.root / "agent"
        for relative in package["files"]:
            self.http.objects["/Workspace/fixture/agent/" + relative] = (folder / relative).read_bytes()
        return package

    def bound_instance(self):
        selected = self.instance(bound=True)
        self.http.agents = [{**selected._binding(), "key": "agent-one"}]
        self.seed_package()
        return selected

    def posts(self):
        return [call for call in self.http.calls if call["method"] == "POST"]

    def accept_candidate(self, selected):
        config_path = self.root / "aidp-agent.toml"
        prefix = config_path.read_text(encoding="utf-8").split("[native]", 1)[0]
        config_path.write_text(prefix + "[native]\n" + "".join(
            key + "=" + json.dumps(value) + "\n" for key, value in self.config["native"].items()), encoding="utf-8")
        case = {"id": "node-positive", "input": {}, "assertions": [{"path": "answer", "equals": "verified"}]}
        cases = self.root / "tests/publication.json"
        cases.write_text(json.dumps([case]), encoding="utf-8")
        test_criterion = {"id": "native-positive", "description": "Native node result meets the rubric",
                          "layer": "TEST", "case_id": "native-reviewed"}
        plan = {"version": 1, "requirements_ref": "README.md", "nodes": [{"id": "respond", "criteria": [
            {"id": "local-positive", "description": "Node result meets the rubric", "layer": "local",
             "case_id": "node-positive", "cases_file": "tests/publication.json"}, test_criterion]}],
            "acceptance": [{**test_criterion, "id": "agent-integrated"}]}
        (self.root / "node-progress.json").write_text(json.dumps(plan), encoding="utf-8")
        _, config = load_project(self.root)
        package = inspect_package(self.root)["package_sha256"]
        result = {"case_id": case["id"], "case_sha256": canonical_hash(case), "config_sha256": canonical_hash(config),
                  "progress_plan_sha256": canonical_hash(plan), "package_sha256": package, "evaluator_version": __version__, **execution_identity(self.root),
                  "mode": "local_fixture_model", "passed": True, "visited_nodes": ["respond"], "model_calls": 0,
                  "recorded_at": datetime.now(timezone.utc).isoformat()}
        private_json(self.root / ".aidp-local/runs/publication.json", {"results": [result]})
        deployment = self.http.tests[0]
        receipt = {"target": selected.base, "workspace": selected.workspace, "agent_key": selected.agent_key,
                   "evaluator_version": __version__, **execution_identity(self.root),
                   "surface": "TEST", "case_id": "native-reviewed", "package_sha256": package,
                   "deployment_key": deployment["key"], "deployment_version": deployment["deploymentVersion"],
                   "deployment_snapshot": selected._snapshot(self.http.tests), "package_binding_verified": True,
                   "question_sha256": "synthetic-frozen-question", "state": "RESPONDED", "passed": True,
                   "stream_complete": True, "failure": None, "error_count": 0}
        relative = ".aidp-local/invocations/publication.json"
        private_json(self.root / relative, receipt)
        record_test_review(self.root, "respond", "native-positive", relative, "accepted", "Node result reviewed")
        record_test_review(self.root, "__agent__", "agent-integrated", relative, "accepted", "Agent integration reviewed")

    def test_binding_inspection_reports_path_drift_without_writes(self):
        selected = self.bound_instance()
        self.http.agents[0].update(pathInfo="/Workspace/legacy/metadata",
                                   entryFilePath="/Workspace/legacy/code/agent.py",
                                   dependenciesFilePath="/Workspace/legacy/code/requirements.txt")
        self.http.tests = [self.http.deployment("TEST")]
        self.http.prod = [self.http.deployment("PROD")]
        result = selected.inspect_binding()
        self.assertFalse(result["binding_verified"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["relocation_required"])
        self.assertTrue(result["entry_update_required"])
        self.assertEqual(result["metadata_location"], "/Workspace/legacy/metadata")
        self.assertEqual(result["code_root"], "/Workspace/legacy/code")
        self.assertEqual(result["migration_blockers"], ["metadata_object_not_verified"])
        self.assertFalse(result["metadata_object_verified"])
        self.assertFalse(result["migration_applied"])
        self.assertFalse(result["native_test_accepted"])
        self.assertEqual([row["deploymentType"] for row in result["test"]], ["TEST"])
        self.assertEqual([row["deploymentType"] for row in result["prod"]], ["PROD"])
        self.assertTrue(all(call["method"] == "GET" for call in self.http.calls))
        self.assertEqual(len(self.http.calls), 3)
        self.assertFalse(selected.journal.exists())
        with self.assertRaises(FlowError):
            selected.status()

    def test_binding_inspection_does_not_turn_a_match_into_acceptance(self):
        selected = self.bound_instance()
        result = selected.inspect_binding()
        self.assertTrue(result["binding_verified"])
        self.assertEqual(result["differences"], {})
        self.assertFalse(result["relocation_required"])
        self.assertFalse(result["native_test_accepted"])
        self.assertFalse(selected.journal.exists())

    def test_binding_inspection_refuses_foreign_identity_before_deployments(self):
        for field, value in (("key", "another-agent"), ("type", "DIAGRAM"),
                             ("computeKey", "another-compute")):
            with self.subTest(field=field):
                selected = self.bound_instance()
                item = {**self.http.agents[0], field: value}
                self.http.calls.clear()
                with patch.object(selected, "_request", return_value=(item, {})) as request:
                    with self.assertRaises(FlowError):
                        selected.inspect_binding()
                self.assertEqual(request.call_count, 1)
                self.assertFalse(selected.journal.exists())

    def test_binding_cli_is_read_only_and_dispatches_without_apply(self):
        from contextlib import redirect_stdout
        import io
        from aidp_agent_flow.cli import main, parser

        self.assertEqual(parser().parse_args(["native", "inspect-binding"]).action, "inspect-binding")
        with self.assertRaises(FlowError):
            parser().parse_args(["native", "inspect-binding", "--apply"])
        selected = self.bound_instance()
        output = io.StringIO()
        with patch("aidp_agent_flow.cli.load_project", return_value=(self.root, self.config)), \
                patch.object(lifecycle, "NativeLifecycle", return_value=selected), redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "native", "inspect-binding"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["result"]["read_only"])
        self.assertTrue(self.http.closed)
        self.assertFalse(selected.journal.exists())

    def test_binding_inspection_requires_known_identity(self):
        selected = self.instance()
        with self.assertRaises(FlowError):
            selected.inspect_binding()
        self.assertEqual(self.http.calls, [])

    def test_sync_plan_reads_without_auth_or_creating_journal(self):
        selected = self.instance()
        with patch.object(lifecycle, "signer_for", side_effect=AssertionError("Must not authenticate")):
            plan = selected.sync_package()
        self.assertTrue(plan["files_to_write"])
        self.assertFalse(plan["applied"])
        self.assertFalse(selected.journal.exists())
        self.assertEqual(self.posts(), [])

    def test_sync_uploads_exact_bytes_and_repeat_is_noop(self):
        selected = self.instance()
        result = selected.sync_package(apply=True)
        self.assertTrue(result["readback_verified"])
        self.assertTrue(result["applied"])
        self.assertFalse(result["remote_extra_files_checked"])
        for relative, digest in inspect_package(self.root)["files"].items():
            self.assertEqual(hashlib.sha256(self.http.objects[selected.remote_root + "/" + relative]).hexdigest(), digest)
        count = len(self.posts())
        self.assertFalse(selected.sync_package(apply=True)["applied"])
        self.assertEqual(len(self.posts()), count)
        self.assertTrue(all(call["headers"].get("opc-retry-token") for call in self.posts()))
        self.assertTrue(all(not call["redirects"] for call in self.http.calls))

    def test_upload_readback_drift_leaves_pending_journal_and_blocks_repeat(self):
        selected = self.instance()
        self.http.drift_upload = True
        with self.assertRaisesRegex(FlowError, "exact byte readback"):
            selected.sync_package(apply=True)
        count = len(self.posts())
        with self.assertRaisesRegex(FlowError, "pending or uncertain"):
            self.instance().sync_package(apply=True)
        self.assertEqual(len(self.posts()), count)

    def test_source_escape_link_and_remote_traversal_fail_before_write(self):
        for remote in ("/Workspace/../foreign", "/Workspace/a\\b", "/Workspace/a//b", "/other/agent", "/Workspace/a/%2e%2e"):
            with self.subTest(remote=remote):
                self.config["native"]["remote_root"] = remote
                with self.assertRaises(FlowError):
                    self.instance()
        self.config["native"]["remote_root"] = "/Workspace/fixture/agent"
        with patch.object(lifecycle.Path, "is_symlink", lambda path: path.name == "core"):
            with self.assertRaisesRegex(FlowError, "linked|symlink"):
                self.instance().sync_package(apply=True)
        self.assertEqual(self.posts(), [])

    def test_foreign_agent_source_overlap_is_never_overwritten(self):
        selected = self.instance()
        self.http.agents = [{**selected._binding(), "displayName": "AnotherAgent", "key": "foreign-agent"}]
        with self.assertRaisesRegex(FlowError, "another agent"):
            selected.sync_package(apply=True)
        with self.assertRaisesRegex(FlowError, "another agent"):
            selected.ensure_agent(apply=True)
        self.assertEqual(self.posts(), [])

    def test_shared_root_allows_exact_readback_but_blocks_any_source_change(self):
        selected = self.bound_instance()
        self.http.agents.append({**selected._binding(), "displayName": "OtherOwnedAgent", "key": "another-agent"})
        self.assertTrue(selected.sync_package(apply=True)["readback_verified"])
        self.assertEqual(self.posts(), [])
        (self.root / "agent/core/state.py").write_text("# Changed shared source\n", encoding="utf-8")
        with self.assertRaisesRegex(FlowError, "another agent"):
            selected.sync_package(apply=True)
        self.assertEqual(self.posts(), [])

    def test_dependency_path_outside_entry_folder_is_rejected(self):
        config_path = self.root / "aidp-agent.toml"
        text = config_path.read_text(encoding="utf-8")
        old = 'dependencies = "agent/requirements.txt"'
        self.assertIn(old, text)
        config_path.write_text(text.replace(old, 'dependencies = "pyproject.toml"'), encoding="utf-8")
        _, self.config = load_project(self.root)
        self.config["native"] = {"endpoint": "https://aidp.region-one.oci.oraclecloud.com", "platform_id": "platform-one",
            "workspace_key": "workspace-one", "compute_key": "compute-one", "display_name": "FixtureAgent", "remote_root": "/Workspace/fixture/agent"}
        with self.assertRaisesRegex(FlowError, "packaged entry folder"):
            self.instance().sync_package(apply=True)
        self.assertEqual(self.http.calls, [])

    def test_ensure_creates_code_agent_then_reuses_its_recorded_binding(self):
        selected = self.instance()
        self.seed_package()
        self.assertTrue(selected.ensure_agent()["would_create"])
        self.assertEqual(self.posts(), [])
        created = selected.ensure_agent(apply=True)
        self.assertTrue(created["applied"])
        self.assertEqual(created["agent_key"], "agent-one")
        self.assertEqual(self.posts()[0]["payload"]["type"], "CODE")
        self.assertFalse(self.instance().ensure_agent(apply=True)["applied"])
        self.assertEqual(len(self.posts()), 1)

    def test_foreign_existing_agent_requires_explicit_key_and_exact_binding(self):
        selected = self.instance()
        self.http.agents = [{**selected._binding(), "key": "agent-one"}]
        with self.assertRaisesRegex(FlowError, "explicit native.agent_key"):
            selected.ensure_agent(apply=True)
        selected = self.instance(bound=True)
        self.http.agents[0]["computeKey"] = "foreign-compute"
        with self.assertRaisesRegex(FlowError, "binding differs"):
            selected.ensure_agent(apply=True)
        self.assertEqual(self.posts(), [])

    def test_exact_name_duplicates_across_pages_fail(self):
        selected = self.instance(bound=True)
        matching = {**selected._binding(), "key": "agent-one"}
        self.http.agents = [matching] + [{"displayName": "Other", "key": "other-" + str(i)} for i in range(99)] + [{**matching, "key": "duplicate"}]
        with self.assertRaisesRegex(FlowError, "Multiple"):
            selected.ensure_agent(apply=True)
        self.assertEqual(self.posts(), [])

    def test_incomplete_pagination_blocks_any_write(self):
        self.http.page_forever = True
        with patch.object(lifecycle, "_MAX_PAGES", 2):
            with self.assertRaisesRegex(FlowError, "incomplete"):
                self.instance().ensure_agent(apply=True)
        self.assertEqual(self.posts(), [])

    def test_test_init_only_uses_legacy_workspace_test_action_and_preserves_prod(self):
        selected = self.bound_instance()
        self.http.prod = [self.http.deployment("PROD")]
        plan = selected.test_init()
        self.assertEqual(plan["deployment_type"], "TEST")
        self.assertEqual(self.posts(), [])
        result = selected.test_init(apply=True)
        post = self.posts()[0]
        self.assertTrue(result["submitted"])
        self.assertIn("/20240831/dataLakes/", post["url"])
        self.assertEqual(post["route"], "/workspaces/workspace-one/actions/redeployAgentFlow")
        self.assertEqual(post["payload"], {"agentFlowKey": "agent-one", "agentFlowComputeKey": "compute-one", "deploymentType": "TEST"})
        self.assertEqual(self.http.prod, [self.http.deployment("PROD")])
        self.assertFalse(result["native_test_accepted"])

    def test_init_requires_no_existing_test_and_refresh_requires_active_test(self):
        selected = self.bound_instance()
        with self.assertRaisesRegex(FlowError, "existing ACTIVE"):
            selected.test_refresh(apply=True)
        self.http.tests = [self.http.deployment()]
        with self.assertRaisesRegex(FlowError, "no existing TEST"):
            selected.test_init(apply=True)
        self.assertEqual(self.posts(), [])

    def test_pending_post_is_not_retried_even_after_payload_source_change(self):
        selected = self.bound_instance()
        self.http.timeout_post = True
        with self.assertRaises(FlowError) as caught:
            selected.test_init(apply=True)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))
        record = selected._intents()[0][1]
        self.assertEqual(record["state"], "SUBMITTED")
        self.assertTrue(record["retry_token"])
        (self.root / "agent/core/state.py").write_text("# New fixture revision\n", encoding="utf-8")
        self.seed_package()
        with self.assertRaisesRegex(FlowError, "pending or uncertain"):
            self.instance(bound=True).test_init(apply=True)
        self.assertEqual(len(self.posts()), 1)

    def test_async_status_reconciles_test_then_refresh_uses_nested_test_route(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        status = selected.status()
        self.assertEqual(status["operations"][0]["state"], "RECONCILED")
        self.assertTrue(selected.test_refresh(apply=True)["up_to_date"])
        (self.root / "agent/core/state.py").write_text("# New fixture revision\n", encoding="utf-8")
        self.seed_package()
        result = selected.test_refresh(apply=True)
        post = self.posts()[-1]
        self.assertEqual(post["route"], "/workspaces/workspace-one/agentFlows/agent-one/deployments/actions/redeploy")
        self.assertEqual(post["payload"]["deploymentType"], "TEST")
        self.assertEqual(result["deployment_type"], "TEST")

    def test_deployment_receipt_is_saved_before_intent_is_closed(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        with patch.object(selected, "_save_state", side_effect=OSError("Synthetic save failure")):
            with self.assertRaises(OSError):
                selected.status()
        self.assertNotEqual(selected._intents()[0][1]["state"], "RECONCILED")
        recovered = self.instance(bound=True)
        recovered.status()
        self.assertEqual(recovered.state["test_receipt"]["deployments"], recovered._snapshot(self.http.tests))
        self.assertEqual(recovered._intents()[0][1]["state"], "RECONCILED")
        self.assertEqual(len(self.posts()), 1)

    def test_deployment_receipt_survives_lost_intent_close_without_second_post(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        with patch.object(selected, "_reconciled", side_effect=OSError("Synthetic close failure")):
            with self.assertRaises(OSError):
                selected.status()
        recovered = self.instance(bound=True)
        self.assertIn("test_receipt", recovered.state)
        recovered.status()
        self.assertEqual(recovered._intents()[0][1]["state"], "RECONCILED")
        self.assertEqual(len(self.posts()), 1)

    def test_test_reconciliation_detects_production_change(self):
        selected = self.bound_instance()
        self.http.prod = [self.http.deployment("PROD")]
        selected.test_init(apply=True)
        self.http.complete_deployment()
        self.http.prod[0]["deploymentVersion"] = 2
        with self.assertRaisesRegex(FlowError, "Production deployment changed"):
            selected.status()
        self.assertNotEqual(selected._intents()[0][1]["state"], "RECONCILED")

    def test_failed_async_operation_is_not_retried(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        next(iter(self.http.operations.values()))["status"] = "FAILED"
        self.assertEqual(selected.status()["operations"][0]["operation_status"], "FAILED")
        record = selected._intents()[0][1]
        self.assertEqual(record["state"], "FAILED_RECONCILED")
        self.assertIn("deployment_after", record)
        self.assertIn("prod_after", record)
        self.assertEqual(record["operation_key"], "operation-1")
        with self.assertRaisesRegex(FlowError, "already recorded"):
            selected.test_init(apply=True)
        self.assertEqual(len(self.posts()), 1)

    def test_known_failed_operation_allows_only_a_changed_explicit_intent(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        next(iter(self.http.operations.values()))["status"] = "FAILED"
        selected.status()
        (self.root / "agent/core/state.py").write_text("# Corrected fixture revision\n", encoding="utf-8")
        self.seed_package()
        selected.test_init(apply=True)
        self.assertEqual(len(self.posts()), 2)
        self.assertNotEqual(self.posts()[0]["headers"]["opc-retry-token"], self.posts()[1]["headers"]["opc-retry-token"])
        self.assertEqual(len(selected._intents()), 2)

    def test_failed_operation_with_unverified_changed_production_remains_blocked(self):
        selected = self.bound_instance()
        self.http.prod = [self.http.deployment("PROD")]
        selected.test_init(apply=True)
        next(iter(self.http.operations.values()))["status"] = "FAILED"
        self.http.prod[0]["deploymentVersion"] = 2
        with self.assertRaisesRegex(FlowError, "Production changed during a failed TEST"):
            selected.status()
        self.assertEqual(selected._intents()[0][1]["state"], "ACKNOWLEDGED")

    def test_package_readback_drift_blocks_deployment(self):
        selected = self.bound_instance()
        self.http.objects[selected.remote_root + "/agent.py"] = b"different saved code"
        with self.assertRaisesRegex(FlowError, "Saved native package bytes differ"):
            selected.test_init(apply=True)
        self.assertEqual(self.posts(), [])

    def test_publish_uses_ga_only_after_matching_test_package_receipt(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        with self.assertRaisesRegex(FlowError, "TEST receipt"):
            selected.publish(apply=True)
        self.assertFalse(selected.publish()["test_package_verified"])
        self.http.tests = []
        selected.test_init(apply=True)
        self.http.complete_deployment()
        selected.status()
        self.accept_candidate(selected)
        selected.publish(apply=True)
        post = self.posts()[-1]
        self.assertIn("/20260430/aiDataPlatforms/", post["url"])
        self.assertTrue(post["route"].endswith("/agents/agent-one/deployments/actions/deploy"))
        self.assertEqual(post["payload"]["agentKey"], "agent-one")
        self.assertNotIn("deploymentType", post["payload"])
        self.assertIn("displayName", post["payload"])

    def test_ga_redeploy_omits_create_only_display_name(self):
        selected = self.bound_instance()
        self.http.prod = [self.http.deployment("PROD")]
        selected.test_init(apply=True)
        self.http.complete_deployment()
        selected.status()
        self.accept_candidate(selected)
        selected.publish(apply=True)
        post = self.posts()[-1]
        self.assertTrue(post["route"].endswith("/deployments/actions/redeploy"))
        self.assertEqual(set(post["payload"]), {"agentKey", "agentComputeKey", "description"})
        self.assertNotIn("displayName", post["payload"])

    def test_publish_blocks_open_functional_criteria_before_any_production_write(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        selected.status()
        count = len(self.posts())
        with self.assertRaisesRegex(FlowError, "agent integration acceptance"):
            selected.publish(apply=True)
        self.assertEqual(len(self.posts()), count)

    def test_publish_up_to_date_branch_still_requires_functional_acceptance(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        selected.status()
        self.http.prod = [self.http.deployment("PROD")]
        selected.state["prod_receipt"] = {"package_sha256": inspect_package(self.root)["package_sha256"],
                                          "deployments": selected._snapshot(self.http.prod)}
        count = len(self.posts())
        with self.assertRaisesRegex(FlowError, "agent integration acceptance"):
            selected.publish(apply=True)
        self.assertEqual(len(self.posts()), count)

    def test_publish_rejects_old_semantic_receipts_after_same_package_TEST_redeployment(self):
        selected = self.bound_instance()
        selected.test_init(apply=True)
        self.http.complete_deployment()
        selected.status()
        self.accept_candidate(selected)
        self.http.tests[0]["deploymentVersion"] = 2
        selected.state["test_receipt"] = {"package_sha256": inspect_package(self.root)["package_sha256"],
                                          "deployments": selected._snapshot(self.http.tests)}
        count = len(self.posts())
        with self.assertRaisesRegex(FlowError, "different deployment"):
            selected.publish(apply=True)
        self.assertEqual(len(self.posts()), count)

    def test_test_session_creation_and_reuse_verify_ga_agent_compute_and_test_endpoint(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        self.assertFalse(selected.create_test_session()["applied"])
        result = selected.create_test_session(apply=True)
        self.assertTrue(result["session_ready"])
        self.assertEqual(self.posts()[0]["payload"]["deploymentType"], "TEST")
        self.assertTrue(any(call["route"].endswith("/agents/agent-one/sessions/session-one") for call in self.http.calls))
        self.assertFalse(selected.create_test_session(apply=True)["applied"])
        self.http.sessions["session-one"]["endpointUrl"] = "https://production.oci.oraclecloud.com/invoke"
        with self.assertRaisesRegex(FlowError, "TEST agent, compute and endpoint"):
            selected.create_test_session(apply=True)
        self.assertEqual(len(self.posts()), 1)

    def test_existing_binding_with_unreported_session_state_is_reused_without_post(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        selected.state["test_session_key"] = "session-one"
        selected._save_state()
        self.http.sessions["session-one"] = {"key": "session-one", "agentKey": "agent-one", "agentComputeKey": "compute-one",
            "endpointUrl": self.http.tests[0]["endpointUrl"], "lifecycleState": None, "timeStarted": None, "timeEnded": None}
        result = selected.create_test_session(apply=True)
        self.assertFalse(result["applied"])
        self.assertTrue(result["binding_verified"])
        self.assertIsNone(result["session_ready"])
        self.assertIsNone(result["session_state"])
        self.assertFalse(result["session_state_reported"])
        self.assertEqual(self.posts(), [])

    def test_created_unreported_session_is_persisted_and_never_duplicated(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        self.http.session_state = None
        result = selected.create_test_session(apply=True)
        self.assertTrue(result["applied"])
        self.assertTrue(result["binding_verified"])
        self.assertIsNone(result["session_ready"])
        self.assertEqual(selected.state["test_session_key"], "session-one")
        receipt = selected._intents()[0][1]
        self.assertEqual(receipt["state"], "RECONCILED")
        self.assertEqual(receipt["resource_key"], "session-one")
        self.assertIsNone(receipt["session_state"])
        self.assertFalse(receipt["session_state_reported"])
        restored = self.instance(bound=True)
        reused = restored.create_test_session(apply=True)
        self.assertEqual(reused["session_key"], "session-one")
        self.assertFalse(reused["applied"])
        self.assertIsNone(reused["session_ready"])
        self.assertEqual(len(self.posts()), 1)

    def test_pending_create_reconciles_matching_unreported_state_without_another_post(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        self.http.session_state = "CREATING"
        created = selected.create_test_session(apply=True)
        self.assertFalse(created["session_ready"])
        self.assertNotIn("test_session_key", selected.state)
        self.http.sessions["session-one"]["lifecycleState"] = None
        restored = self.instance(bound=True)
        self.assertEqual(restored.status()["operations"][0]["state"], "RECONCILED")
        self.assertEqual(restored.state["test_session_key"], "session-one")
        self.assertIsNone(restored.create_test_session(apply=True)["session_ready"])
        self.assertEqual(len(self.posts()), 1)

    def test_unknown_or_missing_session_state_still_blocks_without_creating_replacement(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment()]
        selected.state["test_session_key"] = "session-one"
        original = {"key": "session-one", "agentKey": "agent-one", "agentComputeKey": "compute-one",
                    "endpointUrl": self.http.tests[0]["endpointUrl"]}
        for fields in ({"lifecycleState": "EXPIRED"}, {}):
            with self.subTest(fields=fields):
                self.http.sessions["session-one"] = {**original, **fields}
                with self.assertRaisesRegex(FlowError, "unsupported lifecycle state"):
                    selected.create_test_session(apply=True)
        self.assertEqual(self.posts(), [])

    def test_unjournaled_or_unsupported_request_is_rejected_before_http(self):
        selected = self.instance()
        with self.assertRaisesRegex(FlowError, "Unsupported"):
            selected._request("POST", "/workspaces/workspace-one/agents", payload={})
        with self.assertRaisesRegex(FlowError, "Unsupported"):
            selected._request("DELETE", "/workspaces/workspace-one/agents/agent-one")
        self.assertEqual(self.http.calls, [])


    def test_refresh_cycle_can_return_to_a_historical_package_with_distinct_deployment_scope(self):
        selected = self.bound_instance()
        self.http.tests = [self.http.deployment("TEST", 1)]
        path = self.root / "agent/core/state.py"
        original = path.read_bytes()
        for version, content in ((2, b"# revision B\n"), (3, original), (4, b"# revision B\n")):
            path.write_bytes(content)
            self.seed_package()
            selected.test_refresh(apply=True)
            self.http.complete_deployment(version=version)
            selected = self.instance(bound=True)
            selected.status()
            plan = selected.test_refresh()
            self.assertTrue(plan["up_to_date"])
            self.assertEqual(plan["package_sha256"], inspect_package(self.root)["package_sha256"])
        self.assertEqual(len(self.posts()), 3)
        self.assertEqual(len({row["headers"]["opc-retry-token"] for row in self.posts()}), 3)
        self.assertTrue(all(row["state"] == "RECONCILED" for _, row in selected._intents()))

    def test_sync_cycles_keep_terminal_history_and_never_renew_uncertain_writes(self):
        selected = self.bound_instance()
        path = self.root / "agent/core/state.py"
        original = path.read_bytes()
        for content in (b"# revision B\n", original, b"# revision B\n"):
            path.write_bytes(content)
            selected.sync_package(apply=True)
            selected = self.instance(bound=True)
        file_posts = [row for row in self.posts() if row["headers"].get("type") == "FILE"]
        self.assertEqual(len(file_posts), 3)
        self.assertEqual(len({row["headers"]["opc-retry-token"] for row in file_posts}), 3)
        path.write_bytes(b"# revision C\n")
        self.http.timeout_post = True
        with self.assertRaises(FlowError):
            selected.sync_package(apply=True)
        before = len(self.posts())
        with self.assertRaises(FlowError):
            self.instance(bound=True).sync_package(apply=True)
        self.assertEqual(len(self.posts()), before)

    def test_guarded_sync_rejects_foreign_drift_before_any_write_and_accepts_verified_noop(self):
        selected = self.bound_instance()
        package = inspect_package(self.root)
        definition = {"version": 1, "package_sha256": package["package_sha256"],
                      "files": {name: [digest] for name, digest in package["files"].items()}}
        path = self.root / ".aidp-local/sync-conditions.json"
        private_json(path, definition)
        result = selected.sync_package(apply=True, expected_inventory=".aidp-local/sync-conditions.json")
        self.assertFalse(result["applied"])
        self.assertTrue(result["preconditions_checked"] and result["readback_verified"])
        self.http.objects["/Workspace/fixture/agent/core/state.py"] = b"foreign manual edit"
        self.http.calls.clear()
        with self.assertRaisesRegex(FlowError, "drift was preserved"):
            selected.sync_package(apply=True, expected_inventory=".aidp-local/sync-conditions.json")
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.http.objects["/Workspace/fixture/agent/core/state.py"], b"foreign manual edit")

    def test_guarded_sync_rechecks_each_file_immediately_before_upload(self):
        selected = self.bound_instance()
        old = inspect_package(self.root)
        (self.root / "agent/core/state.py").write_bytes(b"# new revision\n")
        package = inspect_package(self.root)
        definition = {"version": 1, "package_sha256": package["package_sha256"],
                      "files": {name: list({old["files"][name], digest}) for name, digest in package["files"].items()}}
        private_json(self.root / ".aidp-local/sync-conditions.json", definition)
        original = selected._object
        reads = []
        def drift(remote, **kwargs):
            if remote == "/Workspace/fixture/agent/core/state.py":
                reads.append(remote)
                if len(reads) == 2:
                    self.http.objects[remote] = b"foreign after preflight"
            return original(remote, **kwargs)
        with patch.object(selected, "_object", side_effect=drift):
            with self.assertRaisesRegex(FlowError, "drift was preserved"):
                selected.sync_package(apply=True, expected_inventory=".aidp-local/sync-conditions.json")
        self.assertFalse(any(row["headers"].get("type") == "FILE" for row in self.posts()))
        self.assertEqual(self.http.objects["/Workspace/fixture/agent/core/state.py"], b"foreign after preflight")


if __name__ == "__main__":
    unittest.main()
