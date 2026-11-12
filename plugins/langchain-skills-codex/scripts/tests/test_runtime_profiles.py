import asyncio
import json
from pathlib import Path
import sys
import tomllib
import unittest

from aidp_agent_flow.compatibility import assess_runtime, select_profile, observe_capabilities
from aidp_agent_flow.project import FlowError, initialize
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory


class RuntimeProfileTests(unittest.TestCase):
    def local(self):
        return {"status":"observed","python":"3.11.13","packages":{
            "langgraph":"1.2.4","langgraph-checkpoint":"4.1.1","langgraph-prebuilt":"1.1.0"}}

    def test_managed_profile_requires_all_three_observed_packages(self):
        report=assess_runtime(self.local(), runtime_profile="aidp-managed-1.2.4")
        self.assertEqual(report["selected_profile_status"],"target_match")
        self.assertEqual(report["local_profile_status"],"outside_documented_profile")
        self.assertFalse(report["oracle_certified"])
        self.assertFalse(report["native_functional_acceptance"])
        for name in ("langgraph","langgraph-checkpoint","langgraph-prebuilt"):
            local=self.local()
            local["packages"].pop(name)
            self.assertEqual(assess_runtime(local,runtime_profile="aidp-managed-1.2.4")["selected_profile_status"],"unknown")
            local["packages"][name]="0.0.0"
            self.assertEqual(assess_runtime(local,runtime_profile="aidp-managed-1.2.4")["selected_profile_status"],"target_mismatch")

    def test_legacy_observation_keeps_its_original_contract(self):
        local={"status":"observed","packages":{"langgraph":"1.0.1"}}
        report=assess_runtime(local)
        self.assertEqual(report["local_profile_status"],"documented_match")
        self.assertEqual(report["selected_profile_status"],"target_match")

    def test_unknown_and_contradictory_profiles_are_rejected(self):
        with self.assertRaises(FlowError): select_profile("unknown")
        with self.assertRaises(FlowError): select_profile("aidp-managed-1.2.4","1.0.1")
        with self.assertRaises(FlowError): select_profile("custom")

    def test_new_and_legacy_projects_generate_consistent_dependencies(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=base) as directory:
            for profile,version in ((None,"1.2.4"),("oracle-aidp-langgraph-1.0.1","1.0.1")):
                root=Path(directory)/version
                initialize(root,"Runtime profile",sync=False,runtime_profile=profile)
                config=tomllib.loads((root/"aidp-agent.toml").read_text())
                self.assertEqual(config["runtime"]["langgraph_version"],version)
                self.assertIn("langgraph=="+version,(root/"pyproject.toml").read_text())
                self.assertIn("langgraph=="+version,(root/"agent/requirements.txt").read_text())
                constraints=tomllib.loads((root/"pyproject.toml").read_text())["tool"]["uv"].get("constraint-dependencies",[])
                self.assertEqual(bool(constraints),version=="1.2.4")

    def test_unknown_environment_does_not_claim_capabilities(self):
        self.assertEqual(observe_capabilities(None),{"status":"unknown","executed_probe":False})

    def test_timeout_discards_failed_attempt_and_calls_typed_handler(self):
        from importlib.metadata import version
        major_minor=tuple(int(part) for part in version("langgraph").split(".")[:2])
        if major_minor < (1,2):
            self.skipTest("This historical runtime does not expose node timeouts")
        capabilities=observe_capabilities(sys.executable)
        self.assertEqual(capabilities["status"],"observed")
        self.assertTrue(capabilities["node_timeout"])
        self.assertTrue(capabilities["node_error_handler"])
        from typing import TypedDict
        from langgraph.graph import StateGraph,START,END
        from langgraph.types import TimeoutPolicy,RetryPolicy
        from langgraph.errors import NodeError
        class State(TypedDict):
            status:str
        calls=[]
        async def slow(state):
            calls.append("attempt")
            await asyncio.sleep(1)
            return {"status":"uncommitted"}
        def recover(state,error:NodeError):
            calls.append(type(error.error).__name__)
            self.assertEqual(state["status"],"initial")
            return {"status":"timed_out"}
        graph=(StateGraph(State).add_node("slow",slow,timeout=TimeoutPolicy(run_timeout=0.01),
            retry_policy=RetryPolicy(max_attempts=1),error_handler=recover)
            .add_edge(START,"slow").add_edge("slow",END).compile())
        self.assertEqual(asyncio.run(graph.ainvoke({"status":"initial"}))["status"],"timed_out")
        self.assertEqual(calls,["attempt","NodeTimeoutError"])
