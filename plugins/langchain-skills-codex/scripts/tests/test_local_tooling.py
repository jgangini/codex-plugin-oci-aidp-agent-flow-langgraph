import asyncio
import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from aidp_agent_flow.cli import main
from aidp_agent_flow.evaluation import run_cases
from aidp_agent_flow.model import OCIModel
from aidp_agent_flow.packaging import inspect_package
from aidp_agent_flow.project import FlowError, adopt, doctor, initialize, private_json
from aidp_agent_flow.remote import WorkbenchClient


class LocalToolingTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "agent-project"
        initialize(self.root, "Test agent", sync=False)

    def tearDown(self):
        self.temporary.cleanup()

    def test_init_preserves_existing_code(self):
        before = (self.root / "agent/agent.py").read_bytes()
        with self.assertRaises(FlowError):
            initialize(self.root, "Overwrite", sync=False)
        self.assertEqual(before, (self.root / "agent/agent.py").read_bytes())

    def test_doctor_needs_no_auth_or_sdk_request(self):
        with patch("aidp_agent_flow.remote.signer_for", side_effect=AssertionError("Must not sign")):
            result = doctor(self.root)
        self.assertFalse(result["local_ready"])
        self.assertFalse(result["auth_checked"])

    def test_cli_publication_defaults_to_plan_and_closes_client(self):
        client = Mock()
        client.publish.return_value = {"action": "publish", "applied": False}
        output = io.StringIO()
        with patch("aidp_agent_flow.native_lifecycle.NativeLifecycle", return_value=client), redirect_stdout(output):
            code = main(["--project", str(self.root), "--json", "native", "publish"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["result"]["applied"])
        client.publish.assert_called_once_with(apply=False)
        client.close.assert_called_once()

    def test_modular_package_hash_and_secret_exclusion(self):
        result = inspect_package(self.root)
        self.assertIn("core/graph.py", result["files"])
        self.assertIn("core/native.py", result["files"])
        (self.root / "agent/leaked.pem").write_text("synthetic", encoding="utf-8")
        with self.assertRaises(FlowError):
            inspect_package(self.root)

    def test_secret_marker_inside_noncredential_file_rejected(self):
        (self.root / "agent/data.json").write_text('{"value":"-----BEGIN PRIVATE KEY-----"}', encoding="utf-8")
        with self.assertRaises(FlowError):
            inspect_package(self.root)

    def test_secret_marker_split_across_read_chunks_is_rejected(self):
        marker = b"-----BEGIN PRIVATE KEY-----"
        path = self.root / "agent/large.txt"
        path.write_bytes(b"x" * (1024 * 1024 - 12) + marker)
        with self.assertRaises(FlowError):
            inspect_package(self.root)

    def test_private_artifact_rejects_linked_ancestor_before_mkdir(self):
        with patch.object(Path, "is_symlink", lambda path: path.name == ".aidp-local"):
            with self.assertRaises(FlowError):
                private_json(self.root / ".aidp-local/runs/result.json", {"value": "private"})
        self.assertFalse((self.root / ".aidp-local").exists())

    def test_failed_artifact_update_preserves_previous_receipt(self):
        target = self.root / ".aidp-local/runs/retained.json"
        original = {"passed": True, "case_id": "first"}
        private_json(target, original)
        for boundary in ("json.dump", "os.replace"):
            with self.subTest(boundary=boundary), patch("aidp_agent_flow.project." + boundary, side_effect=OSError("Write failed")):
                with self.assertRaises(OSError):
                    private_json(target, {"passed": False, "case_id": "second"}, overwrite=True)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), original)
            self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_adoption_rejects_parent_paths_without_writing(self):
        (self.root / "aidp-agent.toml").unlink()
        with self.assertRaises(FlowError):
            adopt(self.root, "module:build_graph", "../external.py", "agent/requirements.txt")
        self.assertFalse((self.root / "aidp-agent.toml").exists())

    def test_whole_graph_and_individual_node_execute_actual_langgraph(self):
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, self.root / "tests/cases.json")
        self.assertTrue(result["passed"], result)
        self.assertEqual([case["visited_nodes"] for case in result["cases"]], [["respond"], ["respond"]])
        self.assertEqual(result["cases"][1]["checkpointer_scope"], "bypassed_by_node")
        self.assertFalse(result["native_test_accepted"])
        artifact = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
        self.assertEqual(artifact["results"][0]["output"]["answer"], "Recorded fixture response")

    def test_relative_cases_resolve_from_project_outside_cwd(self):
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, "tests/cases.json", selected=["graph-fixture"])
        self.assertTrue(result["passed"], result)

    def test_assertion_failure_does_not_become_success(self):
        path = self.root / "tests/cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))[:1]
        cases[0]["assertions"][0]["equals"] = "Wrong answer"
        path.write_text(json.dumps(cases), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, path)
        self.assertFalse(result["passed"])

    def test_partial_graph_executes_only_intended_middle_node(self):
        source = '''from langgraph.graph import StateGraph, START, END
from typing import TypedDict
class State(TypedDict):
    question: str
    answer: str
def build_graph(runtime):
    graph = StateGraph(State)
    graph.add_node("admit", lambda state: {"question": state["question"]})
    graph.add_node("assess", lambda state: {"answer": "Verified middle"})
    graph.add_node("publish", lambda state: {"answer": "Must not run"})
    graph.add_edge(START, "admit")
    graph.add_edge("admit", "assess")
    graph.add_edge("assess", "publish")
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
'''
        (self.root / "agent/core/graph.py").write_text(source, encoding="utf-8")
        path = self.root / "tests/partial.json"
        path.write_text(json.dumps([{"id": "middle", "input": {"question": "Review"},
            "start_after": "admit", "stop_before": "publish", "expected_nodes": ["assess"],
            "assertions": [{"path": "answer", "equals": "Verified middle"}]}]), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, path)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["cases"][0]["visited_nodes"], ["assess"])

    def test_real_model_requires_explicit_case_selection(self):
        with self.assertRaises(FlowError):
            run_cases(self.root, self.root / "tests/cases.json", real=True)

    def test_graph_replays_mcp_rag_and_table_without_live_connections(self):
        source = '''from langgraph.graph import StateGraph, START, END
from typing import TypedDict
class State(TypedDict):
    question: str
    answer: str
def build_graph(runtime):
    async def retrieve(state):
        for kind in ("mcp", "rag", "table"):
            await runtime["services"].call(kind, "approved_source", {"limit": 3})
        return {"answer": await runtime["model"].complete("Summarize", state["question"])}
    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
'''
        (self.root / "agent/core/graph.py").write_text(source, encoding="utf-8")
        records = [{"kind": kind, "name": "approved_source", "arguments": {"limit": 3}, "result": []}
                   for kind in ("mcp", "rag", "table")]
        path = self.root / "tests/services.json"
        path.write_text(json.dumps([{"id": "replay", "input": {"question": "Review"},
            "service_records": records, "model_responses": ["No admitted evidence"],
            "expected_nodes": ["retrieve"], "assertions": [{"path": "answer", "equals": "No admitted evidence"}]}]), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, path)
        self.assertTrue(result["passed"], result)
        self.assertEqual([call["kind"] for call in result["cases"][0]["service_calls"]], ["mcp", "rag", "table"])

    def test_unused_service_record_cannot_pass_by_ignoring_retrieval(self):
        path = self.root / "tests/cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))[:1]
        cases[0]["service_records"] = [{"kind": "table", "name": "lookup", "arguments": {}, "result": []}]
        path.write_text(json.dumps(cases), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, path)
        self.assertFalse(result["passed"])

    def test_missing_case_and_unsupported_partial_mode_fail_closed(self):
        with self.assertRaises(FlowError):
            run_cases(self.root, self.root / "tests/cases.json", selected=["absent"])
        path = self.root / "tests/cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))[1:]
        cases[0]["start_after"] = "respond"
        path.write_text(json.dumps(cases), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.subprocess.run") as process:
            with self.assertRaises(FlowError):
                run_cases(self.root, path)
            process.assert_not_called()

    def test_real_sdk_request_shape_and_call_limit_without_network(self):
        import oci
        model = OCIModel("unused-config", "DEFAULT", {"region": "us-chicago-1", "model_id": "model",
                         "compartment_id": "compartment", "max_calls": 1, "max_tokens": 23})
        client = Mock()
        models = oci.generative_ai_inference.models
        client.chat.return_value.data.chat_response.choices = [models.ChatChoice(finish_reason="stop",
            message=models.AssistantMessage(content=[models.TextContent(text="Actual SDK fixture")]))]
        model.client = client
        result = asyncio.run(model.complete("System", "Question"))
        self.assertEqual(result, "Actual SDK fixture")
        details = client.chat.call_args.args[0]
        self.assertIsInstance(details, oci.generative_ai_inference.models.ChatDetails)
        self.assertEqual(details.chat_request.max_tokens, 23)
        with self.assertRaises(FlowError):
            asyncio.run(model.complete("System", "Again"))
        self.assertEqual(client.chat.call_count, 1)

    def test_native_template_passes_actual_sdk_config_validation(self):
        import oci
        settings = {"credential_name": "SyntheticRuntime", "region": "us-chicago-1",
                    "model_id": "synthetic", "compartment_id": "synthetic", "max_tokens": 10}
        identity = {"tenancy": "ocid1.tenancy.oc1..synthetic", "user": "ocid1.user.oc1..synthetic",
                    "fingerprint": ":".join(["ab"] * 16), "private_key": "synthetic-value"}
        (self.root / "agent/runtime.json").write_text(json.dumps(settings), encoding="utf-8")
        package = ModuleType("synthetic_agent_core")
        package.__path__ = [str(self.root / "agent/core")]
        spec = importlib.util.spec_from_file_location("synthetic_agent_core.native", self.root / "agent/core/native.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"synthetic_agent_core": package}):
            spec.loader.exec_module(module)
        def validate_client(config, **kwargs):
            oci.config.validate_config(config, signer=kwargs["signer"])
            self.assertEqual(config["key_content"], identity["private_key"])
            return Mock()
        secrets = SimpleNamespace(get=lambda **kwargs: identity[kwargs["key"]])
        with patch.dict(sys.modules, {"aidputils": SimpleNamespace(secrets=secrets)}):
            with patch("oci.signer.Signer", return_value=Mock()):
                with patch("oci.generative_ai_inference.GenerativeAiInferenceClient", side_effect=validate_client):
                    runtime = module.native_runtime(None)
        self.assertIn("model", runtime)

    def client(self):
        return WorkbenchClient(self.root, {"native": {"endpoint": "https://test.datalake.oci.oraclecloud.com",
                               "platform_id": "platform"}})

    def test_uncertain_write_cannot_escape_ledger_by_identity_change(self):
        client = self.client()
        client.prepare_operation("credential-create:SECRET_TOKEN:Shared", {"fingerprint": "first"})
        with self.assertRaises(FlowError):
            client.prepare_operation("credential-create:SECRET_TOKEN:Shared", {"fingerprint": "second"})

    def test_completion_requires_same_existing_operation(self):
        client = self.client()
        with self.assertRaises(FlowError):
            client.complete_operation("missing", {}, "key")
        client.prepare_operation("create", {"identity": "first"})
        with self.assertRaises(FlowError):
            client.complete_operation("create", {"identity": "second"}, "key")

    def test_no_write_without_explicit_credential_intent(self):
        with self.assertRaises(FlowError):
            self.client().request("POST", "/credentials", {})
        with self.assertRaises(FlowError):
            self.client().request("POST", "/workspaces/work/agents/agent/deployments/actions/redeploy", {})

    def test_no_redirect_or_retry_after_uncertain_create(self):
        client = self.client()
        client.session = Mock()
        client.session.request.side_effect = RuntimeError("SECRET MUST NOT BE PRINTED")
        client.prepare_operation("create", {"name": "Shared"})
        with self.assertRaises(FlowError) as caught:
            client.request("POST", "/credentials", {"token": "synthetic"})
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(client.session.request.call_count, 1)
        self.assertFalse(client.session.request.call_args.kwargs["allow_redirects"])
        with self.assertRaises(FlowError):
            client.prepare_operation("create", {"name": "Shared"})

    def test_cli_json_errors_and_offline_capabilities(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--json", "test"])
        self.assertNotEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["ok"])
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--json", "capabilities"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["result"]["registry_registration"],
                         "explicit_legacy_aidp_a2a_inspect_register_active_readback_target_verified")


if __name__ == "__main__":
    unittest.main()
