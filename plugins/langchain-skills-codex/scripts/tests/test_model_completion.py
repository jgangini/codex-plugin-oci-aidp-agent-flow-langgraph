import asyncio
from pathlib import Path
import sys
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from oci.generative_ai_inference import models

from aidp_agent_flow.model import OCIModel
from aidp_agent_flow.project import FlowError, initialize
from aidp_agent_flow.worker import experiment


class ModelCompletionTests(unittest.TestCase):
    def model(self, *, finish_reason="stop", text="Reviewed final answer"):
        model = OCIModel("never-read", "DEFAULT", {"region": "us-chicago-1", "model_id": "synthetic",
                         "compartment_id": "synthetic", "max_calls": 1, "max_tokens": 20})
        choice = models.ChatChoice(index=0, finish_reason=finish_reason,
                                   message=models.AssistantMessage(content=[models.TextContent(text=text)]),
                                   usage=models.Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7))
        model.client = Mock()
        model.client.chat.return_value = SimpleNamespace(data=SimpleNamespace(
            chat_response=SimpleNamespace(choices=[choice])))
        return model, choice

    def test_only_complete_final_text_returns_with_safe_usage_metadata(self):
        model, _ = self.model()
        self.assertEqual(asyncio.run(model.complete("system", "question")), "Reviewed final answer")
        model.assert_complete()
        self.assertEqual(model.response_metadata, [{"finish_reason": "stop", "complete": True,
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}])

    def test_incomplete_unknown_and_missing_termination_cannot_return_text(self):
        for reason in ("length", "content_filter", "tool_calls", "error", None, "", "private-provider-error"):
            with self.subTest(reason=reason):
                model, _ = self.model(finish_reason=reason)
                with self.assertRaises(FlowError) as error:
                    asyncio.run(model.complete("system", "question"))
                self.assertNotIn("private-provider-error", str(error.exception))
                with self.assertRaises(FlowError):
                    model.assert_complete()

    def test_unsupported_response_shapes_and_nontext_or_empty_content_are_rejected(self):
        model, choice = self.model()
        variants = [None, SimpleNamespace(data=None),
            SimpleNamespace(data=SimpleNamespace(chat_response=SimpleNamespace(choices=[]))),
            SimpleNamespace(data=SimpleNamespace(chat_response=SimpleNamespace(choices=[choice, choice])))]
        for response in variants:
            with self.subTest(response=response):
                candidate, _ = self.model()
                candidate.client.chat.return_value = response
                with self.assertRaises(FlowError):
                    asyncio.run(candidate.complete("system", "question"))
                with self.assertRaises(FlowError):
                    candidate.assert_complete()
        for content in (None, [], [models.TextContent(text=" ")], [SimpleNamespace(type="IMAGE", text="fake")],
                        [SimpleNamespace(type="TEXT", text=42)]):
            with self.subTest(content=content):
                candidate, changed = self.model()
                changed.message.content = content
                with self.assertRaises(FlowError):
                    asyncio.run(candidate.complete("system", "question"))

    def test_tool_call_or_nonassistant_message_is_not_a_supported_final_text(self):
        for change in ("tool", "role"):
            model, choice = self.model()
            if change == "tool":
                choice.message.tool_calls = [models.ToolCall(type="FUNCTION")]
            else:
                choice.message = models.UserMessage(content=[models.TextContent(text="not assistant")])
            with self.subTest(change=change), self.assertRaises(FlowError):
                asyncio.run(model.complete("system", "question"))

    def test_budget_recovery_does_not_turn_a_valid_completion_into_protocol_failure(self):
        model, _ = self.model()
        asyncio.run(model.complete("system", "question"))
        with self.assertRaisesRegex(FlowError, "budget"):
            asyncio.run(model.complete("system", "another"))
        model.assert_complete()
        self.assertEqual(model.calls, 1)
        model.client.chat.assert_called_once()

    def test_graph_cannot_hide_a_truncated_model_response_with_a_plausible_fallback(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=base) as temporary:
            root = Path(temporary) / "project"
            initialize(root, "Model completion", sync=False)
            config = root / "aidp-agent.toml"
            config.write_text(config.read_text(encoding="utf-8").replace("core.graph:build_graph", "truncation_graph:build_graph"), encoding="utf-8")
            (root / "agent/truncation_graph.py").write_text('''from typing import TypedDict
from langgraph.graph import StateGraph, START, END
class State(TypedDict):
    answer: str
def build_graph(runtime):
    async def respond(state):
        try:
            await runtime["model"].complete("system", "question")
        except Exception:
            pass
        return {"answer": "looks correct"}
    graph = StateGraph(State)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=runtime["checkpointer"])
''', encoding="utf-8")
            model, _ = self.model(finish_reason="length")
            progress = {}
            job = {"project": str(root), "real": True, "max_steps": 10, "case": {
                "id": "caught-truncation", "input": {}, "assertions": [{"path": "answer", "equals": "looks correct"}]}}
            try:
                with patch("aidp_agent_flow.worker.OCIModel", return_value=model), self.assertRaises(FlowError):
                    asyncio.run(experiment(job, progress))
                self.assertEqual(progress["stage"], "model_contract")
                self.assertEqual(progress["model_calls"], 1)
                self.assertEqual(progress["model_response_metadata"][0]["finish_reason"], "length")
            finally:
                sys.modules.pop("truncation_graph", None)


if __name__ == "__main__":
    unittest.main()
