"""Safe failure codes shared by experiments and campaign decisions."""
from .project import FlowError


class FixtureContractError(FlowError):
    """Recorded model data cannot satisfy the test contract."""


class ModelSetupError(FlowError):
    """Local OCI credentials, SDK initialization or request construction failed."""


class ProviderInvocationError(FlowError):
    def __init__(self, status=None):
        self.status = status if type(status) is int and 400 <= status <= 599 else None
        super().__init__("OCI model invocation failed; inspect provider availability, access and model configuration")


def failure_details(error, stage, real=False):
    if isinstance(error, ModelSetupError):
        return {"failure_code": "preparation", "failure_category": "preparation",
                "next_action": "repair_test_environment_or_contract"}
    if isinstance(error, FixtureContractError):
        return {"failure_code": "fixture_contract", "failure_category": "preparation",
                "next_action": "repair_fixture_and_repeat_offline"}
    if isinstance(error, ProviderInvocationError):
        return {"failure_code": "provider_invocation", "failure_category": "provider",
                "provider_http_status": error.status, "provider_cause": "unverified",
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
    actions = {"fixture_contract": "repair_fixture_and_repeat_offline",
               "provider_invocation": "inspect_provider_evidence_before_retry",
               "preparation": "repair_test_environment_or_contract",
               "contract": "inspect_model_or_tool_contract",
               "execution": "inspect_failed_execution_boundary",
               "assertion": "inspect_earliest_behavior_divergence"}
    return actions.get(result.get("failure_code"), "revise_hypothesis")
