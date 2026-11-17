"""Safe failure codes shared by experiments and campaign decisions."""
import re

from .project import FlowError


class FixtureContractError(FlowError):
    """Recorded model data cannot satisfy the test contract."""


class ModelSetupError(FlowError):
    """Local OCI credentials, SDK initialization or request construction failed."""


class ProviderInvocationError(FlowError):
    def __init__(self, status=None, cause="unverified"):
        self.cause = cause if cause in {"read_timeout", "connect_timeout", "timeout", "tls_failure", "connection_error"} else "unverified"
        self.status = status if type(status) is int and 400 <= status <= 599 else None
        super().__init__("OCI model invocation failed; inspect provider availability, access and model configuration")


class QualityContractError(FlowError):
    def __init__(self, code):
        self.code = code if code in {"json_parse", "assessment_shape", "criterion_set", "criterion_verdict", "claim_shape",
                                     "answer_excerpt", "evidence_excerpt", "missing_support", "coverage_excerpt"} else "validation_shape"
        self.debug_artifact = None
        super().__init__("Quality judge output did not satisfy the evidence contract")


def network_failure_cause(error):
    known = {"ReadTimeout": "read_timeout", "ConnectTimeout": "connect_timeout",
             "Timeout": "timeout", "TimeoutError": "timeout", "SSLError": "tls_failure",
             "ConnectionError": "connection_error"}
    visited, pending = set(), [error]
    while pending and len(visited) < 10:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        cause = known.get(type(current).__name__)
        if cause:
            return cause
        pending.extend(item for item in (getattr(current, "__cause__", None), getattr(current, "__context__", None))
                       if isinstance(item, BaseException))
        pending.extend(item for item in getattr(current, "args", ()) if isinstance(item, BaseException))
    return "unverified"


def _quality_debug_reference(value):
    if (isinstance(value, dict) and set(value) == {"path", "sha256"}
            and isinstance(value["path"], str) and re.fullmatch(r"\.aidp-local/quality-debug/[0-9a-f]{32}\.json", value["path"])
            and isinstance(value["sha256"], str) and re.fullmatch("[0-9a-f]{64}", value["sha256"])):
        return value
    return None


def failure_details(error, stage, real=False):
    if isinstance(error, QualityContractError):
        return {"failure_code": "quality_contract", "failure_category": "evaluator_contract",
                "quality_validation_code": error.code, "quality_debug_artifact": _quality_debug_reference(error.debug_artifact),
                "next_action": "inspect_private_judge_output_before_revising_the_evaluator"}
    if isinstance(error, ModelSetupError):
        return {"failure_code": "preparation", "failure_category": "preparation",
                "next_action": "repair_test_environment_or_contract"}
    if isinstance(error, FixtureContractError):
        return {"failure_code": "fixture_contract", "failure_category": "preparation",
                "next_action": "repair_fixture_and_repeat_offline"}
    if isinstance(error, ProviderInvocationError):
        return {"failure_code": "provider_invocation", "failure_category": "provider",
                "provider_http_status": error.status, "provider_cause": error.cause,
                "next_action": "inspect_provider_evidence_before_retry"}
    if stage in ("validate_case", "load_project", "model_setup", "services_setup", "factory"):
        category, action = "preparation", "repair_test_environment_or_contract"
    elif stage in ("model_contract", "service_contract"):
        category, action = "contract", "inspect_model_or_tool_contract"
    elif stage == "assertions":
        category, action = "assertion", "inspect_earliest_behavior_divergence"
    else:
        category, action = "execution", "inspect_failed_execution_boundary"
    return {"failure_code": category, "failure_category": category, "next_action": action}


def next_action(result):
    if result.get("error_type") in ("Timeout", "WorkerProtocol") or result.get("failure"):
        return "reconcile"
    if result.get("passed") is True:
        return "criterion_passed"
    actions = {"quality_contract": "inspect_private_judge_output_before_revising_the_evaluator",
               "fixture_contract": "repair_fixture_and_repeat_offline",
               "provider_invocation": "inspect_provider_evidence_before_retry",
               "preparation": "repair_test_environment_or_contract",
               "contract": "inspect_model_or_tool_contract",
               "execution": "inspect_failed_execution_boundary",
               "assertion": "inspect_earliest_behavior_divergence"}
    return actions.get(result.get("failure_code"), "revise_hypothesis")
