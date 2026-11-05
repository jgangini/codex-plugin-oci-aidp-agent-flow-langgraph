import asyncio
import json
from pathlib import Path
import sys
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
import unittest
from unittest.mock import patch

from aidp_agent_flow.evaluation import run_cases
from aidp_agent_flow.project import FlowError, initialize
from aidp_agent_flow.model import FixtureModel
from aidp_agent_flow.worker import assertion_results, experiment


class EvaluationContractsTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Evaluation checks", sync=False)

    def tearDown(self):
        self.temporary.cleanup()

    def run_case(self, case):
        path = self.root / "tests/selected.json"
        path.write_text(json.dumps([case]), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            return run_cases(self.root, path)

    def write_graph(self, body):
        source = '''from langgraph.graph import StateGraph, START, END
from typing import TypedDict
class State(TypedDict):
    question: str
    answer: str
def build_graph(runtime):
'''
        (self.root / "agent/core/graph.py").write_text(source + body, encoding="utf-8")

    def test_invalid_assertions_fail_before_constructing_real_model(self):
        invalid = [
            {"path": "answer", "unknown": True},
            {"path": "answer", "equals": "x", "contains": "x"},
            {"path": "answer", "not_empty": "yes"},
            {"path": "", "equals": "x"},
        ]
        for assertion in invalid:
            case = {"id": "invalid", "input": {"question": "Review"}, "assertions": [assertion]}
            with self.subTest(assertion=assertion), patch("aidp_agent_flow.worker.OCIModel", return_value=FixtureModel(["ok"])) as model:
                with self.assertRaises(FlowError):
                    asyncio.run(experiment({"project": str(self.root), "case": case,
                                            "real": True, "max_steps": 10}))
                model.assert_not_called()

    def test_all_selected_cases_validated_before_any_worker(self):
        path = self.root / "tests/invalid.json"
        path.write_text(json.dumps([
            {"id": "valid", "input": {}, "assertions": [{"path": "answer", "equals": "ok"}]},
            {"id": "invalid", "input": {}, "assertions": [{"path": "answer", "typo": True}]},
        ]), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.subprocess.run") as process:
            with self.assertRaises(FlowError):
                run_cases(self.root, path)
            process.assert_not_called()

    def test_unselected_incomplete_case_does_not_block_focused_run(self):
        path = self.root / "tests/focused.json"
        path.write_text(json.dumps([
            {"id": "valid", "input": {"question": "Review"},
             "assertions": [{"path": "answer", "not_empty": True}]},
            {"id": "not-ready", "input": {}, "assertions": [{"path": "answer", "typo": True}]},
        ]), encoding="utf-8")
        with patch("aidp_agent_flow.evaluation.python_path", return_value=Path(sys.executable)):
            result = run_cases(self.root, path, selected=["valid"])
        self.assertTrue(result["passed"], result)
        self.assertEqual(len(result["cases"]), 1)

    def test_missing_null_and_json_type_mismatches_cannot_pass(self):
        cases = [({}, {"path": "missing", "equals": None}, False),
                 ({"field": None}, {"path": "field", "equals": None}, True),
                 ({"field": True}, {"path": "field", "equals": 1}, False),
                 ({"field": {"nested": [True]}}, {"path": "field", "equals": {"nested": [1]}}, False),
                 ({"field": [True]}, {"path": "field", "contains": 1}, False),
                 ({"field": [1]}, {"path": "field", "contains": 1}, True),
                 ({}, {"path": "field", "not_empty": False}, False)]
        for output, assertion, expected in cases:
            with self.subTest(output=output, assertion=assertion):
                self.assertEqual(assertion_results(output, [assertion])[0]["passed"], expected)

    def test_known_secret_markers_in_flow_error_are_not_exposed(self):
        self.write_graph('''    from aidp_agent_flow.project import FlowError
    def fail(state):
        raise FlowError("apify_api_" + "A" * 25)
    graph = StateGraph(State)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "secret-error", "input": {},
                                "assertions": [{"path": "answer", "not_empty": True}]})
        self.assertFalse(result["passed"])
        self.assertNotIn("apify_api_", json.dumps(result))
        self.assertNotIn("apify_api_", Path(result["artifact"]).read_text(encoding="utf-8"))

    def test_configured_tool_error_can_pass_a_reviewed_recovery(self):
        self.write_graph('''    async def respond(state):
        from aidp_agent_flow.services import ServiceError
        try:
            await runtime["services"].call("table", "lookup", {})
        except ServiceError:
            return {"answer": "Source unavailable; no claim of success"}
        return {"answer": "unexpected"}
    graph = StateGraph(State)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "expected-error", "input": {},
            "service_records": [{"kind": "table", "name": "lookup", "arguments": {}, "error": {"code": "timeout"}}],
            "assertions": [{"path": "answer", "equals": "Source unavailable; no claim of success"}]})
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["cases"][0]["service_calls"][0]["status"], "error")

    def test_caught_unexpected_tool_call_cannot_pass(self):
        self.write_graph('''    async def respond(state):
        await runtime["services"].call("table", "lookup", {})
        try:
            await runtime["services"].call("table", "lookup", {})
        except Exception:
            pass
        return {"answer": "looks correct"}
    graph = StateGraph(State)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "unexpected", "input": {},
            "service_records": [{"kind": "table", "name": "lookup", "arguments": {}, "result": []}],
            "assertions": [{"path": "answer", "equals": "looks correct"}]})
        self.assertFalse(result["passed"], result)
        case = result["cases"][0]
        self.assertEqual(case["failure_stage"], "service_contract")
        self.assertEqual(case["visited_nodes"], ["respond"])
        self.assertEqual([call["status"] for call in case["service_calls"]], ["ok", "unmatched"])

    def test_failure_retains_completed_path_and_calls_without_exception_body(self):
        self.write_graph('''    async def first(state):
        return {"answer": await runtime["model"].complete("review", "question")}
    async def fail(state):
        raise RuntimeError("DO-NOT-PRINT provider data")
    graph = StateGraph(State)
    graph.add_node("first", first)
    graph.add_node("fail", fail)
    graph.add_edge(START, "first")
    graph.add_edge("first", "fail")
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "failure", "input": {}, "model_responses": ["recorded"],
                                "assertions": [{"path": "answer", "not_empty": True}]})
        case = result["cases"][0]
        self.assertFalse(case["passed"])
        self.assertEqual(case["failure_stage"], "execution")
        self.assertEqual(case["visited_nodes"], ["first"])
        self.assertEqual(case["last_completed_node"], "first")
        self.assertEqual(case["model_calls"], 1)
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_caught_unrecorded_model_call_cannot_pass(self):
        self.write_graph('''    async def respond(state):
        answer = await runtime["model"].complete("review", "question")
        try:
            await runtime["model"].complete("review", "again")
        except Exception:
            pass
        return {"answer": answer}
    graph = StateGraph(State)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "unexpected-model-call", "input": {},
            "model_responses": ["looks correct"], "require_model_call": True,
            "assertions": [{"path": "answer", "equals": "looks correct"}]})
        case = result["cases"][0]
        self.assertFalse(case["passed"], result)
        self.assertEqual(case["failure_stage"], "model_contract")
        self.assertEqual(case["model_calls"], 2)
        self.assertEqual(case["visited_nodes"], ["respond"])

    def test_node_failure_does_not_claim_selected_node_completed(self):
        self.write_graph('''    def fail(state):
        raise ValueError("private")
    graph = StateGraph(State)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''')
        result = self.run_case({"id": "node-failure", "node": "fail", "input": {},
                                "assertions": [{"path": "answer", "not_empty": True}]})
        case = result["cases"][0]
        self.assertFalse(case["passed"])
        self.assertEqual(case["selection"], {"node": "fail"})
        self.assertEqual(case["visited_nodes"], [])
        self.assertIsNone(case["last_completed_node"])

    def test_changed_assertion_or_fixture_changes_experiment_identity(self):
        case = {"id": "identity", "input": {"question": "same"}, "model_responses": ["first"],
                "assertions": [{"path": "answer", "equals": "first"}]}
        first = self.run_case(case)["cases"][0]
        case["assertions"][0]["equals"] = "different"
        second = self.run_case(case)["cases"][0]
        self.assertEqual(first["input_sha256"], second["input_sha256"])
        self.assertEqual(first["package_sha256"], second["package_sha256"])
        self.assertNotEqual(first["case_sha256"], second["case_sha256"])
        self.assertNotEqual(first["experiment_sha256"], second["experiment_sha256"])
        case["model_responses"] = ["different"]
        third = self.run_case(case)["cases"][0]
        self.assertNotEqual(second["experiment_sha256"], third["experiment_sha256"])
        case["model_responses"] = ["secret apify_api_" + "A" * 25]
        protected = self.run_case(case)
        artifact = json.loads(Path(protected["artifact"]).read_text(encoding="utf-8"))
        self.assertNotIn("apify_api_", json.dumps(artifact))
        self.assertTrue(artifact["experiments"][0]["case_snapshot_redacted"])


if __name__ == "__main__":
    unittest.main()
