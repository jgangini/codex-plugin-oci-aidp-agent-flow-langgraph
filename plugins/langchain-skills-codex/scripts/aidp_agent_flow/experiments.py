"""Read saved experiment evidence; never invoke an agent or infer semantic success."""
import hashlib

from .progress import _path, _read
from .project import FlowError, load_project, redact


_IDENTITY = ("case_sha256", "config_sha256", "package_sha256", "evaluator_version", "mode", "execution_controls", "engine_sha256", "environment_sha256", "environment_observed")


def _controls(value, row):
    experiments = value.get("experiments", [])
    if not isinstance(experiments, list):
        raise FlowError("Experiment metadata must be a list")
    matches = [item for item in experiments if isinstance(item, dict) and row.get("experiment_sha256")
               and item.get("experiment_sha256") == row["experiment_sha256"]]
    if len(matches) != 1:
        return None
    item = matches[0]
    fields = ("max_steps", "timeout_seconds", "requested_model_settings")
    if any(key not in item for key in fields):
        return None
    if (type(item["max_steps"]) is not int or not 1 <= item["max_steps"] <= 200
            or type(item["timeout_seconds"]) is not int or not 1 <= item["timeout_seconds"] <= 600
            or not isinstance(item["requested_model_settings"], dict)):
        raise FlowError("Experiment execution controls are malformed")
    if set(item["requested_model_settings"]) - {"model_id", "region", "max_tokens", "max_calls", "reasoning_effort"}:
        raise FlowError("Experiment model settings contain unsupported fields")
    return {key: item[key] for key in fields}


def _valid_identity(row):
    if "environment_observed" in row and type(row["environment_observed"]) is not bool:
        raise FlowError("Environment observation status must be a boolean")
    for key in ("case_sha256", "config_sha256", "package_sha256", "engine_sha256", "environment_sha256"):
        if key in row and (not isinstance(row[key], str) or len(row[key]) != 64
                           or any(c not in "0123456789abcdef" for c in row[key])):
            raise FlowError("Experiment identity must contain SHA-256 digests")
    if "mode" in row and row["mode"] not in ("local_fixture_model", "local_real_oci_model"):
        raise FlowError("Experiment receipt has an unsupported mode")
    if "evaluator_version" in row and (not isinstance(row["evaluator_version"], str) or not 1 <= len(row["evaluator_version"]) <= 64):
        raise FlowError("Experiment evaluator identity is invalid")


def _valid_observation(row):
    assertions, nodes = row.get("assertions", []), row.get("visited_nodes", [])
    if not isinstance(assertions, list) or len(assertions) > 500:
        raise FlowError("Experiment assertions must be a bounded list")
    for item in assertions:
        if (not isinstance(item, dict) or type(item.get("passed")) is not bool
                or not isinstance(item.get("path"), str) or not 1 <= len(item["path"]) <= 500):
            raise FlowError("Experiment assertion verdicts are malformed")
    if row["passed"] and any(not item["passed"] for item in assertions):
        raise FlowError("A passing experiment cannot contain failed assertions")
    if (not isinstance(nodes, list) or len(nodes) > 10000
            or any(not isinstance(node, str) or not 1 <= len(node) <= 128 for node in nodes)):
        raise FlowError("Experiment observed nodes must be a bounded name list")


def _receipt(root, reference):
    path = _path(root, reference)
    value = _read(path)
    if not isinstance(value, dict) or not isinstance(value.get("results"), list) or not 1 <= len(value["results"]) <= 100:
        raise FlowError("Experiment comparison requires a saved local-run receipt with 1 to 100 results")
    rows = {}
    for row in value["results"]:
        if (not isinstance(row, dict) or not isinstance(row.get("case_id"), str)
                or not row["case_id"] or len(row["case_id"]) > 128
                or row["case_id"] in rows or type(row.get("passed")) is not bool):
            raise FlowError("Experiment receipt case identities and verdicts must be unambiguous")
        _valid_identity(row)
        _valid_observation(row)
        rows[row["case_id"]] = {**row, "execution_controls": _controls(value, row)}
    return rows, {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _failure(row):
    failed = [item.get("path") for item in row.get("assertions", [])
              if isinstance(item, dict) and item.get("passed") is False]
    return {"passed": row["passed"], "failure_stage": row.get("failure_stage"),
            "error_type": row.get("error_type"), "failed_assertions": failed,
            "visited_nodes": row.get("visited_nodes", []), "model_calls": row.get("model_calls"),
            "duration_seconds": row.get("duration_seconds"),
            **{key: row.get(key) for key in ("failure_code", "failure_category", "next_action",
                "provider_http_status", "provider_cause", "completed_model_responses", "stop_reason", "frontier")}}


def _layer(row):
    stage = row.get("failure_stage")
    if row.get("failure_code") and not row["passed"]:
        from .diagnostics import next_action
        return next_action(row)
    if row["passed"]:
        return "review_semantic_outcome_before_acceptance"
    if row.get("error_type") in ("Timeout", "WorkerProtocol"):
        return "reconcile_execution_before_retry"
    if stage in ("load_project", "model_setup", "factory"):
        return "environment_or_factory_contract"
    if stage == "model_contract":
        return "model_response_or_recorded_fixture_contract"
    if stage in ("services_setup", "service_contract"):
        return "tool_or_retrieval_contract"
    return "inspect_assertions_and_earliest_divergence_not_automatically_a_prompt_defect"


def _criterion_refs(root, case_id):
    from .progress import load_progress_plan
    if not (root / "node-progress.json").exists():
        return []
    plan = load_progress_plan(root)
    owners = [(node["id"], node["criteria"]) for node in plan["nodes"]]
    owners.append(("__agent__", plan.get("acceptance", [])))
    return [{"node": node, "criterion": item["id"], "description": item["description"],
             "layer": item["layer"]} for node, criteria in owners for item in criteria if item["case_id"] == case_id]


def diagnose_experiment(root, reference, *, case_id=None):
    root, _ = load_project(root)
    rows, receipt = _receipt(root, reference)
    if case_id is not None:
        if case_id not in rows:
            raise FlowError("Selected case is absent from the saved experiment")
        rows = {case_id: rows[case_id]}
    return redact({"receipt": receipt, "cases": [
        {"case_id": key, **_failure(row), "first_check": _layer(row),
         "criteria": _criterion_refs(root, key),
         "identity": {name: row.get(name) for name in _IDENTITY}}
        for key, row in rows.items()], "agent_invoked": False, "semantic_acceptance": False})


def _comparison(before, after):
    if before is None or after is None:
        return {"comparison": "missing_baseline" if before is None else "missing_candidate", "comparable": False}
    missing = [key for key in _IDENTITY if not before.get(key) or not after.get(key)]
    changed = [key for key in _IDENTITY if before.get(key) != after.get(key)]
    # A changed candidate package is the intended intervention. Changed test,
    # model/config or grader also changes the experiment and needs separate analysis.
    comparable = not missing and not (set(changed) - {"package_sha256"})
    transition = ("assertion_gain" if not before["passed"] and after["passed"] else
                  "regression" if before["passed"] and not after["passed"] else "unchanged")
    return {"comparison": transition if comparable else "not_comparable", "comparable": comparable,
            "changed_identity_fields": changed, "missing_identity_fields": missing,
            "baseline": _failure(before), "candidate": _failure(after)}


def compare_experiments(root, baseline, candidate):
    root, _ = load_project(root)
    before, before_ref = _receipt(root, baseline)
    after, after_ref = _receipt(root, candidate)
    cases = [{"case_id": key, **_comparison(before.get(key), after.get(key))} for key in sorted(before.keys() | after.keys())]
    return redact({"baseline": before_ref, "candidate": after_ref, "cases": cases,
                   "comparable_cases": sum(row["comparable"] for row in cases),
                   "assertion_gains": sum(row["comparison"] == "assertion_gain" for row in cases),
                   "regressions": sum(row["comparison"] == "regression" for row in cases),
                   "semantic_acceptance": False, "native_test_accepted": False,
                   "note": "Saved assertion outcomes only; a gain is not proof of factual quality or generalization"})
