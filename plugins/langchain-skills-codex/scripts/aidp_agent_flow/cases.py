"""The reviewed case contract shared by execution and progress diagnostics."""
from .project import FlowError
from .diagnostics import FixtureContractError
from .services import RecordedServices
from datetime import datetime


def validate_model_responses(responses):
    if (type(responses) is not list or len(responses) > 1000
            or any(type(item) is not str for item in responses)):
        raise FixtureContractError("Recorded model responses must be a list of at most 1000 strings")
    if sum(len(item.encode("utf-8")) for item in responses) > 8 * 1024 * 1024:
        raise FixtureContractError("Recorded model responses exceed 8 MiB")


def _validate_assertion(assertion):
    if not isinstance(assertion, dict) or not isinstance(assertion.get("path"), str) or not assertion["path"]:
        raise FlowError("Each assertion needs a nonempty dotted path")
    operators = set(assertion) - {"path"}
    if len(operators) != 1 or not operators <= {"equals", "contains", "not_empty"}:
        raise FlowError("Each assertion needs exactly one of equals, contains or not_empty")
    if "not_empty" in assertion and type(assertion["not_empty"]) is not bool:
        raise FlowError("The not_empty assertion requires a boolean")


def _validate_selection(case):
    for name in ("node", "start_after", "stop_before"):
        if name in case and (not isinstance(case[name], str) or not case[name]):
            raise FlowError("Node and partial-path selectors must be nonempty strings")
    if case.get("node") and (case.get("start_after") or case.get("stop_before")):
        raise FlowError("A node test cannot also select a partial graph")
    expected = case.get("expected_nodes")
    if expected is not None and (not isinstance(expected, list)
            or any(not isinstance(name, str) or not name for name in expected)):
        raise FlowError("expected_nodes must be a list of node names")


def validate_case(case):
    if (not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]
            or not isinstance(case.get("input"), dict)):
        raise FlowError("Each case needs a nonempty string id and JSON object input")
    _validate_selection(case)
    validate_model_responses(case.get("model_responses", ["Recorded fixture response"]))
    RecordedServices(case.get("service_records", []))
    _validate_observation_options(case)
    assertions = case.get("assertions", [])
    if not isinstance(assertions, list):
        raise FlowError("Case assertions must be a list")
    for assertion in assertions:
        _validate_assertion(assertion)
    if "require_model_call" in case and type(case["require_model_call"]) is not bool:
        raise FlowError("require_model_call must be a boolean")
    if not assertions and case.get("expected_nodes") is None and not case.get("require_model_call"):
        raise FlowError("Case needs at least one explicit assertion or expected path")


def _validate_observation_options(case):
    if "trace_boundaries" in case and type(case["trace_boundaries"]) is not bool:
        raise FlowError("trace_boundaries must be a boolean")
    if "clock_at" in case:
        try:
            if not isinstance(case["clock_at"], str) or len(case["clock_at"]) > 80:
                raise ValueError
            instant = datetime.fromisoformat(case["clock_at"].replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError
        except ValueError:
            raise FlowError("clock_at must be an ISO timestamp with a timezone") from None
