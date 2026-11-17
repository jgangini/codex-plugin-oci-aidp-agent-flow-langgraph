"""The real OCI request constrains syntax without changing semantic validation or budgets."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oci
from aidp_agent_flow.model import OCIModel, FixtureModel
from aidp_agent_flow.project import FlowError
from aidp_agent_flow.diagnostics import ModelSetupError, ProviderInvocationError, QualityContractError
from aidp_agent_flow.quality_grader import ASSESSMENT_SCHEMA, build_graph, grade_response
from test_quality import packet, assessment


class StructuredQualityTests(unittest.TestCase):
    def model(self):
        model = OCIModel("unused", "SELECTED", {"region": "us-chicago-1", "model_id": "synthetic-model",
            "compartment_id": "synthetic-compartment", "max_calls": 1, "max_tokens": 6000, "reasoning_effort": "LOW"})
        model.client = Mock()
        model.client.chat.return_value.data.chat_response.choices = [
            oci.generative_ai_inference.models.ChatChoice(finish_reason="stop",
                message=oci.generative_ai_inference.models.AssistantMessage(content=[
                    oci.generative_ai_inference.models.TextContent(text=json.dumps(assessment()))]))]
        return model

    def test_strict_schema_reaches_sdk_and_preserves_selected_settings_and_one_call(self):
        model = self.model()
        value = asyncio.run(model.complete_json("System", "Question", ASSESSMENT_SCHEMA))
        self.assertTrue(grade_response(packet(), value)["semantic_pass"])
        request = model.client.chat.call_args.args[0].chat_request
        self.assertEqual(request.response_format.type, "JSON_SCHEMA")
        self.assertEqual(request.response_format.json_schema.schema, ASSESSMENT_SCHEMA)
        self.assertTrue(request.response_format.json_schema.is_strict)
        self.assertEqual((request.reasoning_effort, request.temperature, request.max_tokens), ("LOW", 0, 6000))
        self.assertEqual(model.calls, 1)
        with self.assertRaisesRegex(FlowError, "budget"):
            asyncio.run(model.complete_json("System", "Again", ASSESSMENT_SCHEMA))
        self.assertEqual(model.client.chat.call_count, 1)

    def test_ordinary_agent_model_request_is_unchanged(self):
        model = self.model()
        asyncio.run(model.complete("System", "Question"))
        self.assertIsNone(model.client.chat.call_args.args[0].chat_request.response_format)

    def test_sdk_dropping_schema_fails_before_provider_call(self):
        model = self.model()
        with patch("oci.generative_ai_inference.models.GenericChatRequest", return_value=SimpleNamespace(response_format=None)):
            with self.assertRaises(ModelSetupError):
                asyncio.run(model.complete_json("System", "Question", ASSESSMENT_SCHEMA))
        model.client.chat.assert_not_called()

    def test_provider_rejection_does_not_retry_without_schema(self):
        model = self.model()
        model.client.chat.side_effect = RuntimeError("synthetic private provider detail")
        with self.assertRaises(ProviderInvocationError) as raised:
            asyncio.run(model.complete_json("System", "Question", ASSESSMENT_SCHEMA))
        self.assertEqual(model.client.chat.call_count, 1)
        self.assertNotIn("private provider detail", str(raised.exception))

    def test_builtin_quality_node_uses_structured_boundary_and_same_packet(self):
        observed = []
        class Recorded(FixtureModel):
            async def complete_json(self, system, question, schema):
                observed.append((json.loads(question), schema))
                return await super().complete_json(system, question, schema)
        model = Recorded([json.dumps(assessment())])
        graph = build_graph({"model": model, "checkpointer": None})
        result = asyncio.run(graph.ainvoke({"packet": packet()}))
        self.assertEqual(observed, [(packet(), ASSESSMENT_SCHEMA)])
        self.assertTrue(result["assessment"]["semantic_pass"])
        self.assertEqual(model.calls, 1)

    def test_two_json_objects_remain_invalid_not_silently_repaired(self):
        with self.assertRaises(QualityContractError) as raised:
            grade_response(packet(), '{"criteria":[],"claims":[]}, {"reference_facts":[]}')
        self.assertEqual(raised.exception.code, "json_parse")

    def test_structured_material_error_still_fails_semantically(self):
        value = assessment()
        value["claims"][0].update(verdict="unsupported", evidence=[])
        self.assertFalse(grade_response(packet(), json.dumps(value))["semantic_pass"])


if __name__ == "__main__":
    unittest.main()
