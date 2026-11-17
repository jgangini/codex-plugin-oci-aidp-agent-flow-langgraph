import json
from pathlib import Path
from types import SimpleNamespace
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import patch

from aidp_agent_flow import __version__
from aidp_agent_flow import native_invoke
from aidp_agent_flow.campaign import campaign_status, initialize_campaign
from aidp_agent_flow.cli import _campaign_invoke
from aidp_agent_flow.native_invoke import invoke
from aidp_agent_flow.native_lifecycle import NativeLifecycle
from aidp_agent_flow.project import FlowError, initialize


def output_event(text):
    return {"response": {"output": [{"role": "assistant", "content": [{"type": "output_text", "text": text}]}]}}


def stream(*events):
    return b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events) + b"data: [DONE]\n\n"


class FakeSSE:
    def __init__(self, chunks, *, status=200, content_type="text/event-stream; charset=utf-8"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.chunks = [chunks] if isinstance(chunks, bytes) else chunks
        self.closed = False

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, endpoint, **kwargs):
        self.calls.append({"method": method, "endpoint": endpoint, **kwargs})
        return self.response


class FakeLifecycle:
    _deployments = NativeLifecycle._deployments
    _session_info = NativeLifecycle._session_info

    def __init__(self, root, response):
        self.root = root
        self.base = "https://aidp.region-one.oci.oraclecloud.com/20260430/aiDataPlatforms/platform-one"
        self.workspace, self.compute, self.agent_key = "workspace-one", "compute-one", "agent-one"
        self.ws = "/workspaces/workspace-one"
        self.config = {"model": {"region": "region-one"}}
        self.state = {"test_session_key": "session-one"}
        self.transport = FakeTransport(response)
        self.rows = {
            "TEST": [{"key": "test-one", "deploymentType": "TEST", "agentFlowKey": self.agent_key,
                      "agentFlowComputeKey": self.compute, "lifecycleState": "ACTIVE", "deploymentVersion": 1,
                      "timeCreated": "2026-11-01T00:00:00Z",
                      "endpointUrl": "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat"}],
            "PROD": [{"key": "prod-one", "deploymentType": "PROD", "agentKey": self.agent_key,
                      "agentComputeKey": self.compute, "lifecycleState": "ACTIVE", "deploymentVersion": 1,
                      "timeCreated": "2026-11-01T00:00:00Z",
                      "endpointUrl": "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one/chat"}]}
        self.session = {"key": "session-one", "agentKey": self.agent_key, "agentComputeKey": self.compute,
                        "lifecycleState": "ACTIVE", "endpointUrl": self.rows["TEST"][0]["endpointUrl"]}
        self.metadata_calls = []

    def _agent(self):
        self.metadata_calls.append("agent")
        return {"key": self.agent_key}

    def _rows(self, path, *, legacy=False, query=None):
        return self.rows["TEST" if legacy else "PROD"]

    def _request(self, method, path):
        self.metadata_calls.append(path)
        return self.session, {}

    def _session(self):
        return self.transport


class NativeInvokeTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Native fixture", sync=False)
        self.question = self.root / "question.json"
        self.question.write_text(json.dumps({"id": "stable-case", "question": "Synthetic support question"}), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, data=None, **kwargs):
        response = FakeSSE(stream(output_event("Verified support answer")) if data is None else data, **kwargs)
        return FakeLifecycle(self.root, response), response

    def artifact(self, result):
        return json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))

    def advance(self, selected, *, key="test-two", version=2):
        selected.rows["TEST"].append({**selected.rows["TEST"][-1], "key": key,
            "deploymentVersion": version, "timeCreated": f"2026-11-01T00:0{version}:00Z"})

    def bind_package(self, selected, package="a" * 64):
        selected.state["test_receipt"] = {"package_sha256": package,
                                           "deployments": NativeLifecycle._snapshot(selected.rows["TEST"])}

    def campaign_args(self):
        policy = {"version": 1, "max_attempts": 10, "max_model_calls": 10, "max_identical_trials": 1,
                  "native_call_ceiling": 2, "budget_usd": "5", "real_cost_ceiling_usd": "1",
                  "native_cost_ceiling_usd": "2"}
        (self.root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        initialize_campaign(self.root, "policy.json")
        return SimpleNamespace(question_file="question.json", surface="TEST", session=None, expect=[],
                               timeout=90, hypothesis="Verify the reviewed native response", evidence=[], repeat_reason=None)

    def test_preflight_does_not_claim_new_case_or_archive_prior_revision(self):
        selected, _ = self.fixture()
        prepared = native_invoke.preflight_invoke(selected, "question.json")
        self.assertFalse(prepared["artifact"].parent.exists())
        self.assertEqual(selected.transport.calls, [])
        first = invoke(selected, "question.json")
        original = Path(first["artifact"]).read_bytes()
        self.advance(selected)
        prepared = native_invoke.preflight_invoke(selected, "question.json")
        self.assertEqual(prepared["artifact"].read_bytes(), original)
        self.assertFalse((prepared["artifact"].parent / "history").exists())
        self.assertEqual(len(selected.transport.calls), 1)

    def test_campaign_frozen_question_failure_preserves_ledger_and_receipt(self):
        args = self.campaign_args()
        selected, _ = self.fixture()
        first = invoke(selected, "question.json")
        original = Path(first["artifact"]).read_bytes()
        self.advance(selected)
        self.question.write_text(json.dumps({"id": "stable-case", "question": "Changed question"}), encoding="utf-8")
        before = campaign_status(self.root)
        with self.assertRaisesRegex(FlowError, "frozen question"):
            _campaign_invoke(args, selected, self.root, selected.config)
        self.assertEqual(campaign_status(self.root), before)
        self.assertEqual(Path(first["artifact"]).read_bytes(), original)
        self.assertEqual(len(selected.transport.calls), 1)
        self.assertFalse((Path(first["artifact"]).parent / "history").exists())

    def test_campaign_invalid_inputs_or_native_bindings_do_not_reserve(self):
        args = self.campaign_args()
        failures = [("timeout", 0, "timeout"), ("expect", [""], "expected substrings"),
                    ("surface", "UNKNOWN", "surface"), ("session", "missing-session", "session")]
        for field, value, message in failures:
            with self.subTest(field=field):
                selected, _ = self.fixture()
                candidate = SimpleNamespace(**{**vars(args), field: value})
                with self.assertRaisesRegex(FlowError, message):
                    _campaign_invoke(candidate, selected, self.root, selected.config)
                self.assertEqual(campaign_status(self.root)["attempts"], [])
                self.assertEqual(selected.transport.calls, [])
        selected, _ = self.fixture()
        selected.rows["TEST"][0]["endpointUrl"] = "https://unapproved.example/chat"
        with self.assertRaisesRegex(FlowError, "approved native gateway"):
            _campaign_invoke(args, selected, self.root, selected.config)
        self.assertEqual(campaign_status(self.root)["attempts"], [])
        self.assertFalse((self.root / ".aidp-local/invocations").exists())

    def test_campaign_duplicate_and_uncertain_prior_case_do_not_reserve(self):
        args = self.campaign_args()
        selected, _ = self.fixture()
        first = invoke(selected, "question.json")
        with self.assertRaisesRegex(FlowError, "same deployment"):
            _campaign_invoke(args, selected, self.root, selected.config)
        self.assertEqual(campaign_status(self.root)["attempts"], [])
        prior = self.artifact(first)
        prior["state"] = "UNCERTAIN"
        Path(first["artifact"]).write_text(json.dumps(prior), encoding="utf-8")
        self.advance(selected)
        with self.assertRaisesRegex(FlowError, "uncertain response"):
            _campaign_invoke(args, selected, self.root, selected.config)
        self.assertEqual(campaign_status(self.root)["attempts"], [])
        self.assertEqual(len(selected.transport.calls), 1)

    def test_case_claim_rechecks_a_conflict_after_read_only_preflight(self):
        selected, _ = self.fixture()
        preflight = native_invoke.preflight_invoke

        def competing_claim(*args, **kwargs):
            prepared = preflight(*args, **kwargs)
            native_invoke._claim_case(prepared["artifact"], prepared["record"])
            return prepared

        with patch.object(native_invoke, "preflight_invoke", side_effect=competing_claim):
            with self.assertRaisesRegex(FlowError, "uncertain response"):
                invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_campaign_success_reserves_once_and_keeps_native_usage_unknown(self):
        args = self.campaign_args()
        selected, _ = self.fixture()
        result = _campaign_invoke(args, selected, self.root, selected.config)
        status = campaign_status(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(len(status["attempts"]), 1)
        self.assertEqual(status["attempts"][0]["id"], result["campaign_attempt_id"])
        self.assertEqual(status["attempts"][0]["state"], "COMPLETED")
        self.assertIsNone(status["attempts"][0]["model_calls"])
        self.assertEqual(status["model_calls_used_or_reserved"], 2)
        self.assertEqual(len(selected.transport.calls), 1)

    def test_campaign_transport_failure_retains_uncertain_reservations(self):
        args = self.campaign_args()
        selected, _ = self.fixture()
        with patch.object(selected.transport, "request", side_effect=TimeoutError("Synthetic uncertain POST")) as request:
            result = _campaign_invoke(args, selected, self.root, selected.config)
        status = campaign_status(self.root)
        self.assertFalse(result["passed"])
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")
        self.assertEqual(status["attempts"][0]["state"], "UNCERTAIN")
        self.assertIsNone(status["attempts"][0]["model_calls"])
        self.assertEqual(status["unresolved_attempts"], [result["campaign_attempt_id"]])
        self.assertEqual(status["model_calls_used_or_reserved"], 2)
        self.assertEqual(status["cost_used_or_reserved_usd"], "2")
        request.assert_called_once()

    def test_reconciled_snapshot_binds_the_package_and_is_rechecked_after_response(self):
        selected, _ = self.fixture()
        self.bind_package(selected)
        result = invoke(selected, "question.json")
        saved = self.artifact(result)
        self.assertTrue(result["package_binding_verified"])
        self.assertTrue(saved["package_binding_verified"])
        self.assertEqual(saved["package_sha256"], "a" * 64)
        self.assertEqual(saved["deployment_snapshot"], NativeLifecycle._snapshot(selected.rows["TEST"]))

    def test_changed_native_revision_cannot_inherit_a_previous_package_hash(self):
        selected, _ = self.fixture()
        self.bind_package(selected)
        self.advance(selected)
        result = invoke(selected, "question.json")
        saved = self.artifact(result)
        self.assertTrue(result["passed"])
        self.assertEqual(saved["deployment_version"], 2)
        self.assertIsNone(saved["package_sha256"])
        self.assertFalse(result["package_binding_verified"])
        self.assertFalse(saved["package_binding_verified"])

    def test_global_package_hash_without_surface_receipt_does_not_prove_binding(self):
        selected, _ = self.fixture()
        selected.state["package_sha256"] = "a" * 64
        result = invoke(selected, "question.json")
        self.assertFalse(result["package_binding_verified"])
        self.assertIsNone(self.artifact(result)["package_sha256"])

    def test_revision_changed_during_stream_invalidates_initial_binding(self):
        selected, response = self.fixture()
        self.bind_package(selected)
        data = response.chunks[0]
        def changed_stream(chunk_size):
            self.advance(selected)
            yield data
        response.iter_content = changed_stream
        result = invoke(selected, "question.json")
        self.assertTrue(result["passed"])
        self.assertFalse(result["package_binding_verified"])
        self.assertIsNone(self.artifact(result)["package_sha256"])
        self.assertEqual(self.artifact(result)["package_binding_reason"], "deployment_changed_during_invocation")

    def test_failed_post_response_readback_does_not_reuse_initial_binding(self):
        selected, _ = self.fixture()
        self.bind_package(selected)
        with patch.object(selected, "_deployments", side_effect=[selected.rows["TEST"], FlowError("DO-NOT-PRINT provider")]):
            result = invoke(selected, "question.json")
        self.assertTrue(result["passed"])
        self.assertFalse(result["package_binding_verified"])
        saved = self.artifact(result)
        self.assertIsNone(saved["package_sha256"])
        self.assertEqual(saved["package_binding_reason"], "deployment_readback_unavailable")
        self.assertNotIn("DO-NOT-PRINT", json.dumps(saved))

    def test_test_invocation_uses_validated_session_and_keeps_answer_private(self):
        selected, response = self.fixture()
        result = invoke(selected, "question.json", expected=["Verified support"])
        self.assertTrue(result["passed"])
        self.assertTrue(response.closed)
        post = selected.transport.calls[0]
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["headers"]["x-deployment-type"], "TEST")
        self.assertEqual(post["headers"]["x-session-id"], "session-one")
        self.assertEqual(post["json"]["sessionId"], "session-one")
        self.assertEqual(post["json"]["session_id"], "session-one")
        self.assertEqual(post["json"]["metadata"], {})
        self.assertFalse(post["allow_redirects"])
        self.assertEqual(post["timeout"][0], 5)
        self.assertTrue(0 < post["timeout"][1] <= 90)
        self.assertNotIn("answer", result)
        self.assertNotIn("events", result)
        self.assertEqual(self.artifact(result)["answer"], "Verified support answer")
        self.assertEqual(self.artifact(result)["state"], "RESPONDED")
        self.assertFalse(result["native_test_accepted"])

    def test_native_receipt_and_summary_bind_the_current_evaluator_version(self):
        selected, _ = self.fixture()
        result = invoke(selected, "question.json")
        self.assertEqual(result["evaluator_version"], __version__)
        self.assertEqual(self.artifact(result)["evaluator_version"], __version__)

    def test_prod_invocation_uses_exact_owned_prod_endpoint_without_test_session(self):
        selected, _ = self.fixture()
        result = invoke(selected, "question.json", surface="PROD")
        self.assertTrue(result["passed"])
        post = selected.transport.calls[0]
        self.assertTrue(post["endpoint"].endswith("/agentendpoint/agent-one/chat"))
        self.assertEqual(post["headers"]["x-deployment-type"], "PROD")
        self.assertNotIn("x-session-id", post["headers"])
        self.assertNotIn("sessionId", post["json"])

    def test_wrong_surface_or_prod_session_is_rejected_before_post(self):
        for kwargs in ({"surface": "PRODUCTION"}, {"surface": "PROD", "session_key": "session-one"}):
            with self.subTest(kwargs=kwargs):
                selected, _ = self.fixture()
                with self.assertRaises(FlowError):
                    invoke(selected, "question.json", **kwargs)
                self.assertEqual(selected.transport.calls, [])

    def test_wrong_session_binding_or_state_is_rejected_before_post(self):
        for field, value in (("key", "other-session"), ("agentKey", "another-agent"),
                             ("agentComputeKey", "another-compute"),
                             ("endpointUrl", "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one/chat"),
                             ("lifecycleState", "CREATING"), ("lifecycleState", "INACTIVE"),
                             ("lifecycleState", "FAILED"), ("lifecycleState", "DELETED"), ("lifecycleState", "EXPIRED")):
            with self.subTest(field=field):
                selected, _ = self.fixture()
                selected.session[field] = value
                with self.assertRaises(FlowError):
                    invoke(selected, "question.json")
                self.assertEqual(selected.transport.calls, [])

    def test_binding_verified_unreported_session_allows_one_explicit_invocation_honestly(self):
        selected, _ = self.fixture()
        selected.session.update(lifecycleState=None, timeStarted=None, timeEnded=None)
        result = invoke(selected, "question.json", expected=["Verified support answer"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["session_binding_verified"])
        self.assertIsNone(result["session_state"])
        self.assertFalse(result["session_state_reported"])
        receipt = self.artifact(result)
        self.assertIsNone(receipt["session_state"])
        self.assertFalse(receipt["session_state_reported"])
        with self.assertRaisesRegex(FlowError, "same deployment"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)

    def test_unreported_state_does_not_relax_session_identity_checks(self):
        selected, _ = self.fixture()
        selected.session.update(lifecycleState=None, agentKey="foreign-agent")
        with self.assertRaisesRegex(FlowError, "TEST agent, compute and endpoint"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_missing_session_or_active_deployment_is_rejected_before_post(self):
        selected, _ = self.fixture()
        selected.state.clear()
        with self.assertRaisesRegex(FlowError, "validated TEST session"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])
        selected, _ = self.fixture()
        selected.rows["TEST"][0]["lifecycleState"] = "INACTIVE"
        with self.assertRaisesRegex(FlowError, "no ACTIVE"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_foreign_host_agent_path_region_query_or_surface_path_is_rejected(self):
        endpoints = [
            "https://gateway.aidp.region-one.oci.oraclecloud.com.evil.test/agentendpoint/agent-one_TEST/chat",
            "https://gateway.aidp.region-two.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat",
            "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/another-agent_TEST/chat",
            "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one/chat",
            "https://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat?target=other",
            "http://gateway.aidp.region-one.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat"]
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                selected, _ = self.fixture()
                selected.rows["TEST"][0]["endpointUrl"] = endpoint
                with self.assertRaisesRegex(FlowError, "approved native gateway"):
                    invoke(selected, "question.json")
                self.assertEqual(selected.transport.calls, [])

    def test_reference_assertions_never_enter_model_input(self):
        selected, _ = self.fixture()
        result = invoke(selected, "question.json", expected=["REFERENCE_ONLY_LABEL"])
        self.assertFalse(result["passed"])
        self.assertNotIn("REFERENCE_ONLY_LABEL", json.dumps(selected.transport.calls[0]["json"]))
        self.assertEqual(result["assertions"], [{"index": 0, "passed": False}])

    def test_cumulative_and_final_events_do_not_duplicate_answer(self):
        selected, _ = self.fixture(stream(output_event("Hello"), output_event("Hello world"), output_event("Hello world")))
        result = invoke(selected, "question.json", expected=["Hello world"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["event_count"], 4)
        self.assertEqual(self.artifact(result)["answer"], "Hello world")

    def test_nested_stream_error_cannot_pass_even_with_a_matching_answer(self):
        error = output_event("Verified support answer")
        error["response"]["metadata"] = {"nested": {"error": {"message": "DO-NOT-PRINT secret provider context"}}}
        selected, _ = self.fixture(stream(output_event("Verified support answer"), error))
        result = invoke(selected, "question.json", expected=["Verified support"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["failure"], "stream_error")
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")
        self.assertNotIn("DO-NOT-PRINT", Path(result["artifact"]).read_text(encoding="utf-8"))
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_uncertain_stream_is_not_repeated_even_if_question_changes(self):
        selected, response = self.fixture([stream(output_event("Partial"))[:-14], TimeoutError("DO-NOT-PRINT")])
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")
        self.assertTrue(response.closed)
        self.question.write_text(json.dumps({"id": "stable-case", "question": "Changed question"}), encoding="utf-8")
        with self.assertRaisesRegex(FlowError, "already recorded"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)

    def test_completed_case_advances_once_to_latest_native_revision_and_preserves_history(self):
        selected, _ = self.fixture()
        self.bind_package(selected, "a" * 64)
        first = invoke(selected, "question.json")
        original = Path(first["artifact"]).read_bytes()
        self.advance(selected)
        self.bind_package(selected, "b" * 64)
        second = invoke(selected, "question.json")
        self.assertTrue(second["passed"])
        self.assertEqual(second["deployment_key"], "test-two")
        self.assertEqual(second["deployment_version"], 2)
        self.assertEqual(first["artifact"], second["artifact"])
        current = self.artifact(second)
        self.assertEqual(current["package_sha256"], "b" * 64)
        history = Path(second["artifact"]).parent / current["previous_receipt"]
        self.assertEqual(history.read_bytes(), original)
        self.assertEqual(json.loads(history.read_text())["deployment_key"], "test-one")
        with self.assertRaisesRegex(FlowError, "same deployment"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 2)
        self.assertEqual(list(history.parent.glob("*.json")), [history])

    def test_same_case_has_immutable_receipts_across_multiple_native_revisions(self):
        selected, _ = self.fixture()
        first = invoke(selected, "question.json")
        original = Path(first["artifact"]).read_bytes()
        self.advance(selected)
        second = invoke(selected, "question.json")
        second_bytes = Path(second["artifact"]).read_bytes()
        self.advance(selected, key="test-three", version=3)
        third = invoke(selected, "question.json")
        archived = [path.read_bytes() for path in (Path(third["artifact"]).parent / "history").glob("*.json")]
        self.assertCountEqual(archived, [original, second_bytes])
        self.assertEqual(third["deployment_key"], "test-three")
        self.assertEqual(len(selected.transport.calls), 3)

    def test_completed_assertion_failure_can_be_rechecked_on_a_new_native_revision(self):
        selected, _ = self.fixture()
        first = invoke(selected, "question.json", expected=["Corrected fact"])
        self.assertFalse(first["passed"])
        self.assertEqual(self.artifact(first)["state"], "RESPONDED")
        self.advance(selected)
        selected.transport.response = FakeSSE(stream(output_event("Corrected fact")))
        second = invoke(selected, "question.json", expected=["Corrected fact"])
        self.assertTrue(second["passed"])
        self.assertEqual(len(selected.transport.calls), 2)

    def test_uncertain_revision_blocks_even_a_new_native_deployment(self):
        selected, _ = self.fixture(b"Uncertain", content_type="application/json")
        first = invoke(selected, "question.json")
        self.assertEqual(self.artifact(first)["state"], "UNCERTAIN")
        self.advance(selected)
        with self.assertRaisesRegex(FlowError, "uncertain response"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)
        self.assertFalse((Path(first["artifact"]).parent / "history").exists())

    def test_new_deployment_does_not_allow_changing_the_frozen_case_question(self):
        selected, _ = self.fixture()
        first = invoke(selected, "question.json")
        self.advance(selected)
        self.question.write_text(json.dumps({"id": "stable-case", "question": "A different question"}), encoding="utf-8")
        with self.assertRaisesRegex(FlowError, "frozen question"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)
        self.assertFalse((Path(first["artifact"]).parent / "history").exists())

    def test_local_package_change_without_native_revision_does_not_allow_rerun(self):
        selected, _ = self.fixture()
        selected.state["package_sha256"] = "a" * 64
        invoke(selected, "question.json")
        selected.state["package_sha256"] = "b" * 64
        with self.assertRaisesRegex(FlowError, "same deployment"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)

    def test_changed_prior_target_identity_cannot_be_replaced(self):
        selected, _ = self.fixture()
        first = invoke(selected, "question.json")
        prior = self.artifact(first)
        prior["agent_key"] = "foreign-agent"
        Path(first["artifact"]).write_text(json.dumps(prior), encoding="utf-8")
        self.advance(selected)
        with self.assertRaisesRegex(FlowError, "different target identity"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)

    def test_retained_active_deployments_require_unique_latest_creation_time(self):
        selected, _ = self.fixture()
        selected.rows["TEST"].append({**selected.rows["TEST"][0], "key": "test-two", "deploymentVersion": 2})
        with self.assertRaisesRegex(FlowError, "creation time is ambiguous"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_non_sse_response_fails_without_consuming_body_and_records_uncertainty(self):
        selected, response = self.fixture(b"DO-NOT-PRINT", content_type="application/json")
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure"], "http_or_content_type")
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")
        self.assertTrue(response.closed)
        self.assertNotIn("DO-NOT-PRINT", Path(result["artifact"]).read_text(encoding="utf-8"))

    def test_empty_final_output_does_not_reuse_an_earlier_partial_answer(self):
        selected, _ = self.fixture(stream(output_event("Earlier partial"), {"response": {"output": []}}))
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(self.artifact(result)["answer"], "")

    def test_multiline_sse_data_and_comments_parse_without_duplicate_output(self):
        final = output_event("Final answer")
        final.update(type="response.completed")
        final["response"]["status"] = "completed"
        encoded = json.dumps(final, indent=2).splitlines()
        sse = b": heartbeat\n\n" + b"\n".join(b"data: " + line.encode() for line in encoded) + b"\n\n"
        selected, _ = self.fixture([sse[:11], sse[11:]])
        result = invoke(selected, "question.json", expected=["Final answer"])
        self.assertTrue(result["passed"])
        self.assertEqual(self.artifact(result)["answer"], "Final answer")

    def test_eof_after_in_progress_output_is_uncertain_even_when_expected_text_matches(self):
        partial = output_event("Verified support answer")
        partial.update(type="response.in_progress")
        partial["response"]["status"] = "in_progress"
        selected, _ = self.fixture(b"data: " + json.dumps(partial).encode() + b"\n\n")
        result = invoke(selected, "question.json", expected=["Verified support answer"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["stream_complete"])
        self.assertEqual(result["failure"], "incomplete_stream")
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")
        self.advance(selected)
        with self.assertRaisesRegex(FlowError, "uncertain response"):
            invoke(selected, "question.json")
        self.assertEqual(len(selected.transport.calls), 1)

    def test_sse_completed_event_name_completes_a_created_data_payload(self):
        final = output_event("Final answer")
        final.update(type="response.created")
        selected, _ = self.fixture(b"event: response.completed\ndata: " + json.dumps(final).encode() + b"\n\n")
        result = invoke(selected, "question.json", expected=["Final answer"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["stream_complete"])
        saved = self.artifact(result)
        self.assertEqual(saved["completion_marker"], "response.completed")
        self.assertEqual(saved["events"][0]["sse_event"], "response.completed")

    def test_explicit_completed_response_status_is_terminal_without_done(self):
        final = output_event("Final answer")
        final["response"]["status"] = "completed"
        selected, _ = self.fixture(b"data: " + json.dumps(final).encode() + b"\n\n")
        result = invoke(selected, "question.json", expected=["Final answer"])
        self.assertTrue(result["passed"])
        self.assertEqual(self.artifact(result)["completion_marker"], "response.status.completed")

    def test_completed_event_with_in_progress_status_cannot_pass(self):
        final = output_event("A partial answer")
        final.update(type="response.completed")
        final["response"]["status"] = "in_progress"
        selected, _ = self.fixture(b"data: " + json.dumps(final).encode() + b"\n\n")
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure"], "invalid_completion")

    def test_failed_framing_event_is_detected_even_when_data_has_no_error_field(self):
        final = output_event("Verified support answer")
        selected, _ = self.fixture(b"event: response.failed\ndata: " + json.dumps(final).encode() + b"\n\ndata: [DONE]\n\n")
        result = invoke(selected, "question.json", expected=["Verified"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(self.artifact(result)["state"], "UNCERTAIN")

    def test_native_region_ignores_cross_region_model_and_uses_platform_region(self):
        for native_host, platform in (
            ("aidp.us-chicago-1.oci.oraclecloud.com", "platform-one"),
            ("tenant.datalake.oci.oraclecloud.com", "ocid1.datalake.oc1.us-chicago-1.fixture"),
            ("tenant.datalake.oci.oraclecloud.com", "ocid1.datalake.oc1.ord.fixture")):
            with self.subTest(host=native_host, platform=platform):
                selected, _ = self.fixture()
                selected.base = "https://" + native_host + "/20260430/aiDataPlatforms/" + platform
                selected.config = {"native": {"platform_id": platform}, "model": {"region": "us-phoenix-1"}}
                endpoint = "https://gateway.aidp.us-chicago-1.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat"
                selected.rows["TEST"][0]["endpointUrl"] = endpoint
                selected.session["endpointUrl"] = endpoint
                self.assertTrue(invoke(selected, "question.json")["passed"])
                self.assertEqual(selected.transport.calls[0]["endpoint"], endpoint)

    def test_platform_region_rejects_mismatched_gateway_even_when_model_matches_it(self):
        selected, _ = self.fixture()
        platform = "ocid1.datalake.oc1.us-chicago-1.fixture"
        selected.base = "https://tenant.datalake.oci.oraclecloud.com/20260430/aiDataPlatforms/" + platform
        selected.config = {"native": {"platform_id": platform}, "model": {"region": "us-phoenix-1"}}
        selected.rows["TEST"][0]["endpointUrl"] = "https://gateway.aidp.us-phoenix-1.oci.oraclecloud.com/agentendpoint/agent-one_TEST/chat"
        with self.assertRaisesRegex(FlowError, "approved native gateway"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_tenant_host_without_native_region_never_falls_back_to_model_region(self):
        selected, _ = self.fixture()
        selected.base = "https://tenant.datalake.oci.oraclecloud.com/20260430/aiDataPlatforms/platform-one"
        with self.assertRaisesRegex(FlowError, "native invocation region"):
            invoke(selected, "question.json")
        self.assertEqual(selected.transport.calls, [])

    def test_byte_frame_and_event_limits_fail_closed(self):
        for constant, value, expected in (("_MAX_BYTES", 40, "byte_limit"),
                                          ("_MAX_FRAME", 40, "frame_limit"),
                                          ("_MAX_EVENTS", 1, "event_limit")):
            with self.subTest(constant=constant):
                self.question.write_text(json.dumps({"id": constant.lstrip("_"), "question": "Synthetic question"}), encoding="utf-8")
                selected, response = self.fixture(stream(output_event("x" * 50), output_event("x" * 50)))
                with patch.object(native_invoke, constant, value):
                    result = invoke(selected, "question.json")
                self.assertFalse(result["passed"])
                self.assertEqual(result["failure"], expected)
                self.assertTrue(response.closed)

    def test_large_native_trace_is_not_public_output_or_a_failure(self):
        event = output_event("Safe answer")
        part = event["response"]["output"][0]["content"][0]
        part["spans"] = [{"status": "failed", "trace": "PRIVATE-TRACE" * 30000}]
        part["resources"] = {"diagnostic": "PRIVATE-TRACE"}
        event["response"]["output"][0]["content"].append(
            {"type": "trace", "text": "PRIVATE-TRACE" * 30000})
        selected, _ = self.fixture(stream(event))
        result = invoke(selected, "question.json")
        self.assertTrue(result["passed"])
        saved = json.loads(Path(result["artifact"]).read_bytes())
        self.assertEqual(saved["answer"], "Safe answer")
        self.assertNotIn("PRIVATE-TRACE", json.dumps(saved["events"]))
        self.assertLess(Path(result["artifact"]).stat().st_size, 20000)

    def test_public_nested_error_is_not_hidden_by_trace_projection(self):
        event = output_event("Unsafe result")
        event["response"]["output"][0]["content"].append(
            {"type": "tool_result", "result": {"isError": True}})
        selected, _ = self.fixture(stream(event))
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertGreater(result["error_count"], 0)

    def test_public_capture_has_a_separate_finite_limit(self):
        selected, response = self.fixture(stream(output_event("Safe answer")))
        with patch.object(native_invoke, "_MAX_CAPTURE", 40):
            result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure"], "capture_limit")
        self.assertTrue(response.closed)

    def test_control_and_done_frames_also_obey_capture_bound(self):
        for end in (b"\n\n", b"\ndata: [DONE]\n\n"):
            with self.subTest(end=end):
                self.question.write_text(json.dumps({"id": "control-" + str(len(end)),
                                                      "question": "Synthetic question"}))
                selected, response = self.fixture(b"event: " + b"control" * 8 + end)
                with patch.object(native_invoke, "_MAX_CAPTURE", 40):
                    result = invoke(selected, "question.json")
                self.assertFalse(result["passed"])
                self.assertEqual(result["failure"], "capture_limit")
                self.assertTrue(response.closed)

    def test_cumulative_public_transcript_can_exceed_twenty_thousand_characters(self):
        text = "Public progress packet\n" * 2500
        selected, _ = self.fixture(stream(output_event(text)))
        result = invoke(selected, "question.json")
        self.assertTrue(result["passed"])
        self.assertTrue(result["stream_complete"])
        self.assertEqual(json.loads(Path(result["artifact"]).read_bytes())["answer"], text)

    def test_answer_still_has_finite_limit_and_preserves_observed_completion(self):
        selected, response = self.fixture(stream(output_event("x" * (native_invoke._MAX_ANSWER + 1))))
        result = invoke(selected, "question.json")
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure"], "answer_limit")
        self.assertTrue(result["stream_complete"])
        self.assertTrue(response.closed)

    def test_elapsed_budget_is_checked_during_stream(self):
        selected, response = self.fixture()
        with patch.object(native_invoke.time, "monotonic", side_effect=[0, 0, 2]):
            result = invoke(selected, "question.json", timeout=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure"], "timeout")
        self.assertTrue(response.closed)

    def test_sensitive_event_fields_are_redacted_in_private_evidence(self):
        event = output_event("Safe answer")
        event["metadata"] = {"Authorization": "DO-NOT-PRINT", "nested": {"private_key": "DO-NOT-PRINT"}}
        selected, _ = self.fixture(stream(event))
        result = invoke(selected, "question.json")
        self.assertTrue(result["passed"])
        self.assertNotIn("DO-NOT-PRINT", Path(result["artifact"]).read_text(encoding="utf-8"))

    def test_explicit_long_research_deadlines_keep_streaming_and_record_the_control(self):
        for timeout in (600, 1800):
            with self.subTest(timeout=timeout):
                self.question.write_text(json.dumps({"id": "long-" + str(timeout), "question": "Synthetic"}), encoding="utf-8")
                selected, response = self.fixture()
                result = invoke(selected, "question.json", timeout=timeout)
                self.assertTrue(result["passed"])
                self.assertEqual(self.artifact(result)["timeout_seconds"], timeout)
                self.assertTrue(selected.transport.calls[0]["stream"])
                self.assertEqual(len(selected.transport.calls), 1)
                self.assertTrue(response.closed)

    def test_question_path_shape_size_and_timeout_are_validated_before_post(self):
        selected, _ = self.fixture()
        for path in (str(self.question), "../question.json"):
            with self.subTest(path=path), self.assertRaises(FlowError):
                invoke(selected, path)
        for value in ({"question": "Missing stable id"}, {"id": "case", "question": "x" * 4001}):
            self.question.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(FlowError):
                invoke(selected, "question.json")
        self.question.write_text(json.dumps({"id": "case", "question": "Valid"}), encoding="utf-8")
        for timeout in (0, -1, 1801, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(FlowError):
                invoke(selected, "question.json", timeout=timeout)
        self.assertEqual(selected.transport.calls, [])


if __name__ == "__main__":
    unittest.main()
