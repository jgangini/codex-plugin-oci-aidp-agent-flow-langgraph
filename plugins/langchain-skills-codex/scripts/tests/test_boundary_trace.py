import asyncio
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import TypedDict
import unittest
from unittest.mock import patch

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from aidp_agent_flow.boundary_trace import BoundaryTrace
from aidp_agent_flow.model import OCIModel
from aidp_agent_flow.project import FlowError
from aidp_agent_flow.worker import experiment, main


class State(TypedDict, total=False):
    answer: str
    route: str
    evidence: list


class BoundaryExecutionTests(unittest.TestCase):
    def graph(self, runtime, *, alternate=False, dynamic=False, fail=False, checkpoint=True):
        def first(state):
            return {"evidence": [{"id": "doc-1"}]} if alternate else {"answer": "computed", "evidence": [{"id": "doc-1"}]}

        def second(state):
            if fail:
                raise FlowError("PRIVATE NODE EXCEPTION RESPONSE")
            if dynamic:
                interrupt("PRIVATE INTERRUPT PAYLOAD")
            return {"answer": "delivered"}

        graph = StateGraph(State)
        graph.add_node("first", first)
        graph.add_node("second", second)
        graph.add_node("deliver", lambda state: {"answer": "done"})
        graph.add_edge(START, "first")
        if alternate:
            graph.add_conditional_edges("first", lambda state: END if state.get("route") == "end" else "second")
        else:
            graph.add_edge("first", "second")
        graph.add_edge("second", "deliver")
        graph.add_edge("deliver", END)
        return graph.compile(checkpointer=runtime["checkpointer"] if checkpoint else None)

    def run_case(self, case, *, factory=None, envelope=False, real=False):
        factory = factory or self.graph
        root = Path(__file__).resolve().parents[2]
        config = {"agent": {"python_path": "scripts", "factory": "_boundary_fixture:build_graph"}}
        job = {"project": str(root), "real": real, "max_steps": 20, "case": case}
        with patch("aidp_agent_flow.worker.load_project", return_value=(root, config)), \
                patch.dict(sys.modules, {"_boundary_fixture": SimpleNamespace(build_graph=factory)}), \
                patch.object(sys, "path", sys.path.copy()):
            if not envelope:
                return asyncio.run(experiment(job))
            output = io.StringIO()
            with patch("aidp_agent_flow.worker.json.load", return_value=job), redirect_stdout(output):
                main()
            return json.loads(output.getvalue())

    def case(self, **kwargs):
        return {"id": "boundary", "input": {}, "assertions": [{"path": "answer", "not_empty": True}], **kwargs}

    def test_linear_partial_confirms_checkpoint_frontier_and_field_hashes(self):
        result = self.run_case(self.case(stop_before="deliver", trace_boundaries=True))
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["visited_nodes"], ["first", "second"])
        self.assertEqual(result["stop_reason"], "requested_stop_before")
        self.assertEqual(result["frontier"], {"expected": ["deliver"], "observed": ["deliver"], "snapshot_supported": True})
        trace = result["boundary_trace"]
        self.assertEqual(trace["nodes"][0]["update"]["fields"]["evidence"], trace["output"]["fields"]["evidence"])
        self.assertNotIn("doc-1", json.dumps(trace))
        self.assertNotIn("computed", json.dumps(trace))

    def test_alternate_terminal_cannot_pass_preloaded_output_assertion(self):
        case = self.case(input={"answer": "preloaded", "route": "end"}, stop_before="deliver",
                         assertions=[{"path": "answer", "equals": "preloaded"}])
        result = self.run_case(case, factory=lambda runtime: self.graph(runtime, alternate=True))
        self.assertFalse(result["passed"])
        self.assertEqual(result["stop_reason"], "terminal_before_requested")
        self.assertEqual(result["frontier"]["observed"], [])
        self.assertTrue(result["assertions"][0]["passed"])
        self.assertFalse(result["assertions"][-1]["passed"])
        self.assertNotIn("output", result)

    def test_dynamic_interrupt_is_not_requested_static_stop(self):
        result = self.run_case(self.case(stop_before="deliver", trace_boundaries=True),
                               factory=lambda runtime: self.graph(runtime, dynamic=True))
        self.assertFalse(result["passed"])
        self.assertEqual(result["stop_reason"], "dynamic_interrupt")
        self.assertEqual(result["frontier"]["observed"], ["second"])
        self.assertEqual(result["visited_nodes"], ["first"])
        self.assertEqual([node["node"] for node in result["boundary_trace"]["nodes"]], ["first"])
        self.assertNotIn("PRIVATE INTERRUPT PAYLOAD", json.dumps(result))

    def test_dynamic_interrupt_without_stop_request_cannot_pass(self):
        result = self.run_case(self.case(), factory=lambda runtime: self.graph(runtime, dynamic=True))
        self.assertFalse(result["passed"])
        self.assertEqual(result["stop_reason"], "dynamic_interrupt")

    def test_start_after_uses_fresh_seed_and_stops_before_delivery(self):
        result = self.run_case(self.case(start_after="first", stop_before="deliver", input={"answer": "seeded"}))
        self.assertTrue(result["passed"])
        self.assertEqual(result["visited_nodes"], ["second"])
        self.assertEqual(result["stop_reason"], "requested_stop_before")

    def test_stop_before_alone_requires_supplied_checkpointer(self):
        with self.assertRaisesRegex(FlowError, "supplied checkpointer"):
            self.run_case(self.case(stop_before="deliver"), factory=lambda runtime: self.graph(runtime, checkpoint=False))

    def test_failure_retains_only_completed_boundary_metadata(self):
        result = self.run_case(self.case(trace_boundaries=True), envelope=True,
                               factory=lambda runtime: self.graph(runtime, fail=True))
        self.assertFalse(result["ok"])
        progress = result["result"]
        self.assertEqual(progress["stop_reason"], "error")
        self.assertEqual(progress["frontier"]["observed"], ["second"])
        self.assertEqual(progress["last_completed_node"], "first")
        self.assertEqual([node["node"] for node in progress["boundary_trace"]["nodes"]], ["first"])
        self.assertNotIn("output", progress)
        self.assertNotIn("PRIVATE NODE EXCEPTION RESPONSE", json.dumps(result))

    def test_node_failure_never_records_completed_boundary(self):
        result = self.run_case(self.case(node="second", trace_boundaries=True), envelope=True,
                               factory=lambda runtime: self.graph(runtime, fail=True))["result"]
        self.assertEqual(result["stop_reason"], "error")
        self.assertEqual(result["boundary_trace"]["nodes"], [])
        self.assertIsNone(result["last_completed_node"])

    def test_tracing_is_opt_in_and_fixed_clock_only_enters_factory(self):
        seen = []

        def factory(runtime):
            seen.extend([runtime["clock"](), runtime["clock"]()])
            return self.graph(runtime)

        result = self.run_case(self.case(clock_at="2020-02-03T04:05:06+00:00"), factory=factory)
        self.assertTrue(result["passed"])
        self.assertEqual(seen, [datetime(2020, 2, 3, 4, 5, 6, tzinfo=timezone.utc)] * 2)
        self.assertNotIn("boundary_trace", result)
        self.assertGreater(datetime.now(timezone.utc).year, 2020)

    def test_failed_fixture_call_retains_attempts_and_completed_responses_separately(self):
        def factory(runtime):
            async def respond(state):
                await runtime["model"].complete("private system", "private question")
                try:
                    await runtime["model"].complete("private system", "private question")
                except FlowError:
                    pass
                return {"answer": "fallback"}

            graph = StateGraph(State)
            graph.add_node("respond", respond)
            graph.add_edge(START, "respond")
            graph.add_edge("respond", END)
            return graph.compile(checkpointer=runtime["checkpointer"])

        result = self.run_case(self.case(model_responses=["private response"]), factory=factory, envelope=True)["result"]
        self.assertFalse(result["passed"])
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["completed_model_responses"], 1)
        self.assertEqual(result["mode"], "local_fixture_model")
        self.assertEqual(result["failure_code"], "fixture_contract")
        self.assertNotIn("private", json.dumps(result))

    def test_caught_provider_failure_only_passes_without_required_model_completion(self):
        def factory(runtime):
            async def respond(state):
                try:
                    await runtime["model"].complete("synthetic", "synthetic")
                except FlowError:
                    return {"answer": "reviewed fallback"}
                return {"answer": "unexpected completion"}

            graph = StateGraph(State)
            graph.add_node("respond", respond)
            graph.add_edge(START, "respond")
            graph.add_edge("respond", END)
            return graph.compile(checkpointer=runtime["checkpointer"])

        for required in (True, False):
            model = OCIModel("unused", "DEFAULT", {"region": "us-chicago-1", "model_id": "fixture", "compartment_id": "fixture"})
            with self.subTest(required=required), patch("aidp_agent_flow.worker.OCIModel", return_value=model), \
                    patch.object(model, "_complete", side_effect=TimeoutError("private provider body")):
                result = self.run_case(self.case(require_model_call=required,
                    assertions=[{"path": "answer", "equals": "reviewed fallback"}]), factory=factory, real=True)
            self.assertEqual(result["passed"], not required)
            self.assertEqual(result["model_calls"], 1)
            self.assertEqual(result["completed_model_responses"], 0)
            self.assertEqual(result["mode"], "local_real_oci_model")
            self.assertNotIn("private provider body", json.dumps(result))


class BoundaryMetadataTests(unittest.TestCase):
    def test_trace_contains_hashes_sizes_and_wall_intervals_without_values(self):
        with patch("aidp_agent_flow.boundary_trace.time.monotonic", side_effect=[10.0, 10.5]):
            trace = BoundaryTrace({"evidence": "PRIVATE EVIDENCE"})
            trace.completed("assess", {"answer": "PRIVATE ANSWER"})
            trace.finish({"answer": "PRIVATE ANSWER"})
        self.assertEqual(trace.data["nodes"][0]["wall_seconds_since_previous_event"], 0.5)
        self.assertEqual(trace.data["input"]["fields"]["evidence"]["bytes"], 18)
        self.assertEqual(len(trace.data["output"]["fields"]["answer"]["sha256"]), 64)
        self.assertNotIn("PRIVATE", json.dumps(trace.data))

    def test_metadata_caps_nodes_fields_and_serialization_without_calling_repr(self):
        class Secret:
            def __repr__(self):
                raise AssertionError("must not serialize arbitrary objects")

        trace = BoundaryTrace({"oversized": "x" * 100000, "unsupported": Secret()})
        for index in range(70):
            trace.completed("node", {str(field): [index] for field in range(40)})
        trace.finish({"answer": "x" * 100000})
        self.assertEqual(len(trace.data["nodes"]), 64)
        self.assertTrue(trace.data["nodes_truncated"])
        self.assertEqual(len(trace.data["nodes"][0]["update"]["fields"]), 32)
        self.assertTrue(trace.data["nodes"][0]["update"]["fields_truncated"])
        self.assertEqual(trace.data["input"]["fields"]["oversized"]["status"], "omitted_unsupported_or_limit")
        self.assertNotIn("sha256", trace.data["input"]["fields"]["unsupported"])


if __name__ == "__main__":
    unittest.main()
