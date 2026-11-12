"""OCI request settings validated with the installed SDK and no network calls."""
import asyncio
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import oci

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aidp_agent_flow.model import OCIModel
from aidp_agent_flow.project import FlowError


class ModelSettingsTests(unittest.TestCase):
    def settings(self, **changes):
        return {"region": "us-chicago-1", "model_id": "synthetic-model",
                "compartment_id": "synthetic-compartment", "max_tokens": 31,
                "max_calls": 1, **changes}

    def client(self):
        client = Mock()
        client.chat.return_value.data.chat_response.choices = [
            oci.generative_ai_inference.models.ChatChoice(finish_reason="stop",
                message=oci.generative_ai_inference.models.AssistantMessage(content=[
                    oci.generative_ai_inference.models.TextContent(text="Recorded answer")]))]
        return client

    def test_absent_effort_preserves_sdk_default_without_sending_a_value(self):
        request_type = oci.generative_ai_inference.models.GenericChatRequest
        with patch("oci.generative_ai_inference.models.GenericChatRequest", wraps=request_type) as request:
            model = OCIModel("unused-config", "SELECTED", self.settings())
            self.assertEqual(request.call_count, 0)
            model.client = self.client()
            self.assertEqual(asyncio.run(model.complete("System", "Question")), "Recorded answer")
        self.assertNotIn("reasoning_effort", request.call_args.kwargs)
        self.assertIsNone(model.client.chat.call_args.args[0].chat_request.reasoning_effort)

    def test_supported_effort_reaches_real_sdk_request_and_preserves_limits(self):
        model = OCIModel("unused-config", "SELECTED", self.settings(reasoning_effort="HIGH"))
        model.client = self.client()
        self.assertEqual(asyncio.run(model.complete("System", "Question")), "Recorded answer")
        details = model.client.chat.call_args.args[0]
        self.assertEqual(details.chat_request.reasoning_effort, "HIGH")
        self.assertEqual(details.chat_request.max_tokens, 31)
        self.assertEqual(details.chat_request.temperature, 0)
        self.assertFalse(details.chat_request.is_stream)
        self.assertEqual(details.serving_mode.model_id, "synthetic-model")
        self.assertEqual(details.compartment_id, "synthetic-compartment")
        self.assertEqual(details.chat_request.messages[0].content[0].text, "System")
        self.assertEqual(details.chat_request.messages[1].content[0].text, "Question")
        with self.assertRaisesRegex(FlowError, "budget"):
            asyncio.run(model.complete("System", "Another question"))
        self.assertEqual(model.calls, 1)
        self.assertEqual(model.client.chat.call_count, 1)

    def test_invalid_effort_fails_before_authentication_or_call_count(self):
        for value in ("XHIGH", "high", "", None, 17, True, ["HIGH"]):
            with self.subTest(value=value):
                model = OCIModel.__new__(OCIModel)
                with patch("oci.config.from_file") as config, \
                        patch("aidp_agent_flow.remote.signer_for") as signer, \
                        patch("oci.generative_ai_inference.GenerativeAiInferenceClient") as client:
                    with self.assertRaisesRegex(FlowError, "reasoning_effort"):
                        model.__init__("unused-config", "SELECTED", self.settings(reasoning_effort=value))
                self.assertEqual(model.calls, 0)
                self.assertIsNone(model.client)
                config.assert_not_called()
                signer.assert_not_called()
                client.assert_not_called()

    def test_sdk_error_does_not_disclose_rejected_value_or_exception_details(self):
        sensitive = "synthetic-private-setting"
        with patch("oci.generative_ai_inference.models.GenericChatRequest",
                   side_effect=ValueError("SDK rejected " + sensitive)):
            with self.assertRaises(FlowError) as raised:
                OCIModel("unused-config", "SELECTED", self.settings(reasoning_effort=sensitive))
        self.assertNotIn(sensitive, str(raised.exception))
        self.assertNotIn("SDK rejected", str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    def test_sdk_that_drops_effort_is_rejected_instead_of_silently_ignoring_it(self):
        for request in (SimpleNamespace(), SimpleNamespace(reasoning_effort=None)):
            with self.subTest(request=request):
                with patch("oci.generative_ai_inference.models.GenericChatRequest", return_value=request):
                    with self.assertRaisesRegex(FlowError, "reasoning_effort"):
                        OCIModel("unused-config", "SELECTED", self.settings(reasoning_effort="HIGH"))

    def test_selected_config_profile_and_signer_are_preserved(self):
        config = {"region": "us-phoenix-1", "user": "synthetic-user"}
        client, signer = self.client(), object()
        with patch("oci.config.from_file", return_value=config) as read_config, \
                patch("aidp_agent_flow.remote.signer_for", return_value=signer) as choose_signer, \
                patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=client) as factory:
            model = OCIModel("selected-config", "SELECTED", self.settings(reasoning_effort="HIGH"))
            read_config.assert_not_called()
            choose_signer.assert_not_called()
            factory.assert_not_called()
            self.assertEqual(asyncio.run(model.complete("System", "Question")), "Recorded answer")
        read_config.assert_called_once_with("selected-config", "SELECTED")
        choose_signer.assert_called_once_with(config)
        self.assertEqual(factory.call_args.args[0], {**config, "region": "us-chicago-1"})
        self.assertIs(factory.call_args.kwargs["signer"], signer)
        self.assertIsInstance(factory.call_args.kwargs["retry_strategy"], oci.retry.NoneRetryStrategy)
        self.assertEqual(factory.call_args.kwargs["timeout"], (5, 60))
        self.assertEqual(config["region"], "us-phoenix-1")



    def test_read_timeout_is_bounded_and_reaches_sdk_without_enabling_retry(self):
        for seconds in (1, 120, 600):
            with self.subTest(seconds=seconds), \
                    patch("oci.config.from_file", return_value={"region":"us-chicago-1"}), \
                    patch("aidp_agent_flow.remote.signer_for", return_value=object()), \
                    patch("oci.generative_ai_inference.GenerativeAiInferenceClient", return_value=self.client()) as factory:
                model=OCIModel("unused-config","SELECTED",self.settings(read_timeout_seconds=seconds))
                model._request("System","Question")
                self.assertEqual(factory.call_args.kwargs["timeout"],(5,seconds))
                self.assertIsInstance(factory.call_args.kwargs["retry_strategy"],oci.retry.NoneRetryStrategy)
                self.assertEqual(model.calls,0)

    def test_invalid_read_timeout_fails_before_authentication(self):
        for value in (True, False, None, 0, -1, 601, 1.5, "120"):
            with self.subTest(value=value), patch("oci.config.from_file") as config:
                with self.assertRaisesRegex(FlowError,"read_timeout_seconds"):
                    OCIModel("unused-config","SELECTED",self.settings(read_timeout_seconds=value))
                config.assert_not_called()

if __name__ == "__main__":
    unittest.main()
