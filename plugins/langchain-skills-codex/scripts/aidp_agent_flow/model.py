"""Bounded local model adapters, separate from AIDP-managed authentication."""
from __future__ import annotations

from collections import deque
import re

from .project import FlowError
from .model_boundary import final_text, run_blocking
from .cases import validate_model_responses
from .diagnostics import FixtureContractError, ModelSetupError, ProviderInvocationError, network_failure_cause


class FixtureModel:
    def __init__(self, responses):
        validate_model_responses(responses)
        self.responses = deque(responses)
        self.calls = 0
        self.completed_responses = 0
        self._unrecorded_call = False

    async def complete(self, system, question):
        self.calls += 1
        if not self.responses:
            self._unrecorded_call = True
            raise FixtureContractError("Fixture model has no recorded response left")
        self.completed_responses += 1
        return self.responses.popleft()

    async def complete_json(self, system, question, schema):
        return await self.complete(system, question)

    def assert_recorded_calls(self):
        if self._unrecorded_call:
            raise FixtureContractError("Fixture model received an unrecorded call, even if the graph recovered")


class OCIModel:
    def __init__(self, config_file, profile, settings):
        self.config_file, self.profile, self.settings = str(config_file), profile, settings
        self.calls = 0
        self.completed_responses = 0
        self.client = None
        self.response_metadata = []
        self._completion_failed = False
        if not re.fullmatch(r"[a-z][a-z0-9-]+", settings.get("region", "")):
            raise FlowError("Select the model's OCI region")
        for key in ("model_id", "compartment_id"):
            if not settings.get(key):
                raise FlowError("Model and compartment must be selected before real-model testing")
        if not 1 <= int(settings.get("max_calls", 3)) <= 50 or not 1 <= int(settings.get("max_tokens", 512)) <= 16000:
            raise FlowError("Model call/token limits are invalid")
        self.read_timeout_seconds = settings.get("read_timeout_seconds", 60)
        if type(self.read_timeout_seconds) is not int or not 1 <= self.read_timeout_seconds <= 600:
            raise FlowError("read_timeout_seconds must be an integer between 1 and 600")
        self._reasoning_options = {}
        if "reasoning_effort" in settings:
            effort = settings["reasoning_effort"]
            try:
                from oci.generative_ai_inference.models import GenericChatRequest
                if not isinstance(effort, str) or not effort:
                    raise ValueError
                request = GenericChatRequest(reasoning_effort=effort)
                if getattr(request, "reasoning_effort", None) != effort:
                    raise ValueError
            except (ImportError, AttributeError, TypeError, ValueError):
                raise FlowError("Configured reasoning_effort is unsupported by the installed OCI SDK") from None
            self._reasoning_options["reasoning_effort"] = effort

    def _request(self, system, question, response_schema=None):
        import oci
        settings = self.settings
        if self.client is None:
            config = oci.config.from_file(self.config_file, self.profile)
            from .remote import signer_for
            signer = signer_for(config)
            self.client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                {**config, "region": settings["region"]}, signer=signer,
                retry_strategy=oci.retry.NoneRetryStrategy(), timeout=(5, self.read_timeout_seconds))
        models = oci.generative_ai_inference.models
        format_options = {}
        if response_schema is not None:
            format_options["response_format"] = models.JsonSchemaResponseFormat(
                json_schema=models.ResponseJsonSchema(name="aidp_quality", schema=response_schema, is_strict=True))
        request = models.GenericChatRequest(temperature=0, max_tokens=settings.get("max_tokens", 512),
            is_stream=False, messages=[models.SystemMessage(content=[models.TextContent(text=system)]),
                                      models.UserMessage(content=[models.TextContent(text=question)])],
            **self._reasoning_options, **format_options)
        if response_schema is not None:
            retained = getattr(getattr(request, "response_format", None), "json_schema", None)
            if retained is None or retained.schema != response_schema or retained.is_strict is not True:
                raise FlowError("Installed OCI SDK did not preserve the requested structured output schema")
        return models.ChatDetails(
            compartment_id=settings["compartment_id"],
            serving_mode=models.OnDemandServingMode(model_id=settings["model_id"]),
            chat_request=request)

    def _complete(self, system, question, response_schema=None):
        try:
            request = self._request(system, question, **({"response_schema": response_schema} if response_schema is not None else {}))
        except Exception:
            raise ModelSetupError("Local OCI model setup failed") from None
        try:
            result = self.client.chat(request)
        except Exception as error:
            raise ProviderInvocationError(getattr(error, "status", None), network_failure_cause(error)) from None
        response = getattr(getattr(result, "data", None), "chat_response", None)
        return self._final_text(response)

    def _final_text(self, response):
        choices = getattr(response, "choices", None)
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        reason = getattr(choice, "finish_reason", None)
        metadata = {"finish_reason": reason if reason in ("stop", "length", "content_filter", "tool_calls")
                    else "missing_or_unsupported", "complete": False}
        usage = getattr(choice, "usage", None)
        metadata["usage"] = {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                             if type(value := getattr(usage, key, None)) is int and 0 <= value <= 10**9}
        self.response_metadata.append(metadata)
        try:
            answer = final_text(response)
        except ValueError as error:
            self._completion_failed = True
            raise FlowError(str(error)) from None
        metadata["complete"] = True
        self.completed_responses += 1
        return answer

    def assert_complete(self):
        if self._completion_failed:
            raise FlowError("OCI model produced an incomplete or malformed response, even if the graph recovered")

    async def complete(self, system, question, *, response_schema=None):
        if self.calls >= int(self.settings.get("max_calls", 3)):
            raise FlowError("Local model call budget reached")
        self.calls += 1
        try:
            args = (system, question) if response_schema is None else (system, question, response_schema)
            return await run_blocking(self._complete, *args)
        except FlowError:
            raise
        except Exception:
            raise FlowError("Local model execution failed outside the provider boundary") from None

    async def complete_json(self, system, question, schema):
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise FlowError("Structured output requires an object JSON schema")
        return await self.complete(system, question, response_schema=schema)

    def close(self):
        if self.client is not None:
            self.client.base_client.session.close()
