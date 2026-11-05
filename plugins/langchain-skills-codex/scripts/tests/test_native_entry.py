from contextlib import contextmanager
from pathlib import Path
import sys
from types import ModuleType
from typing import TypedDict
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from aidp_agent_flow.model_boundary import final_text, final_text_scope


class EntryState(TypedDict):
    question: str
    answer: str


@contextmanager
def loaded_entry(pre_invoke, *, recovered_invalid_completion=False):
    """Execute the shipped entry against real LangGraph and fake native setup."""
    saver = InMemorySaver()
    observed = []

    def build_graph(runtime):
        async def respond(state, config: RunnableConfig):
            observed.append({"thread_id": config["configurable"]["thread_id"],
                             "prepared": pre_invoke.called})
            if recovered_invalid_completion:
                try:
                    final_text(None)
                except ValueError:
                    return {"answer": "Plausible recovered response"}
            return {"answer": "Reply to: " + state["question"]}

        graph = StateGraph(EntryState)
        graph.add_node("respond", respond)
        graph.add_edge(START, "respond")
        graph.add_edge("respond", END)
        return graph.compile(checkpointer=runtime["checkpointer"])

    native_runtime = Mock(side_effect=lambda checkpointer: {"checkpointer": checkpointer})
    modules = {name: ModuleType(name) for name in (
        "core", "core.graph", "core.native", "core.model_boundary", "aidputils", "aidputils.agents",
        "aidputils.agents.toolkit", "aidputils.agents.toolkit.agent_helper")}
    for name, module in modules.items():
        module.__path__ = []
        parent, _, child = name.rpartition(".")
        if parent:
            setattr(modules[parent], child, module)
    modules["core.graph"].build_graph = build_graph
    modules["core.native"].native_runtime = native_runtime
    modules["core.model_boundary"].final_text_scope = final_text_scope
    modules["aidputils.agents.toolkit.agent_helper"].pre_invoke_setup = pre_invoke
    template = Path(__file__).resolve().parents[1] / "aidp_agent_flow/templates/agent/agent.py.tmpl"
    namespace = {"__name__": "generated_native_entry", "checkpointer": saver}
    with patch.dict(sys.modules, modules):
        exec(compile(template.read_text(encoding="utf-8"), str(template), "exec"), namespace)
        agent = namespace["Agent"]()
        agent.setup()
        yield agent, saver, observed, native_runtime


class NativeEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_entry_rejects_graph_recovery_from_invalid_model_completion(self):
        prepare = Mock(return_value={"configurable": {"thread_id": "synthetic-thread"}})
        with loaded_entry(prepare, recovered_invalid_completion=True) as (agent, _, _, _):
            with self.assertRaisesRegex(ValueError, "even if the graph recovered"):
                await agent.invoke("Synthetic question")

    async def test_managed_setup_supplies_required_checkpoint_thread_and_output_contract(self):
        managed_config = {"configurable": {"thread_id": "synthetic-native-thread"},
                          "metadata": {"prepared_by_native_helper": True}}
        prepare = Mock(return_value=managed_config)
        with loaded_entry(prepare) as (agent, saver, observed, native_runtime):
            # Native kwargs deliberately contain no config/thread_id. The helper
            # supplies it, so bypassing that helper makes InMemorySaver fail.
            response = await agent.invoke("Synthetic support question", session_id="synthetic-session")
            prepare.assert_called_once_with(session_id="synthetic-session")
            native_runtime.assert_called_once_with(saver)
            self.assertEqual(observed, [{"thread_id": "synthetic-native-thread", "prepared": True}])
            self.assertEqual(set(response), {"messages"})
            self.assertEqual(len(response["messages"]), 1)
            self.assertIsInstance(response["messages"][0], AIMessage)
            self.assertEqual(response["messages"][0].content, "Reply to: Synthetic support question")
            checkpoint = await saver.aget_tuple(managed_config)
            self.assertIsNotNone(checkpoint)
            self.assertEqual(checkpoint.checkpoint["channel_values"]["answer"], "Reply to: Synthetic support question")

    async def test_native_setup_rejection_stops_before_graph_even_with_caller_config(self):
        prepare = Mock(side_effect=RuntimeError("Synthetic rejected native context"))
        caller_config = {"configurable": {"thread_id": "caller-supplied-thread"}}
        with loaded_entry(prepare) as (agent, _, observed, _):
            with self.assertRaisesRegex(RuntimeError, "rejected native context"):
                await agent.invoke("Must not execute", config=caller_config)
            prepare.assert_called_once_with(config=caller_config)
            self.assertEqual(observed, [])


if __name__ == "__main__":
    unittest.main()
