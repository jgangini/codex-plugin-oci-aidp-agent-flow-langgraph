"""Post-hoc quality and finite-set calibration using the existing campaign runner."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .experiments import _receipt
from .identity import execution_identity
from .progress import _path, _read, _read_hashed
from .project import FlowError, canonical_hash, load_project, private_json, redact
from .quality_grader import validate_packet


def _at(value, segments):
    if not isinstance(segments, list) or not 1 <= len(segments) <= 30:
        raise FlowError("Quality bindings need a bounded JSON path list")
    try:
        for segment in segments:
            if isinstance(value, dict) and isinstance(segment, str):
                value = value[segment]
            elif isinstance(value, list) and type(segment) is int and 0 <= segment < len(value):
                value = value[segment]
            else:
                raise KeyError
        return value
    except (KeyError, IndexError):
        raise FlowError("Quality binding JSON path does not exist") from None


def _bound(root, binding, depth=0):
    if isinstance(binding, dict) and set(binding) == {"parts"}:
        parts = binding["parts"]
        if (depth >= 3 or not isinstance(parts, dict) or not 1 <= len(parts) <= 20
                or any(not isinstance(key, str) or not 1 <= len(key) <= 80 for key in parts)):
            raise FlowError("Composite quality bindings exceed their bounded scope")
        return {key: _bound(root, value, depth + 1) for key, value in parts.items()}
    if not isinstance(binding, dict) or set(binding) != {"file", "sha256", "path"}:
        raise FlowError("Quality bindings need file, sha256 and path")
    path = _path(root, binding["file"])
    value, digest = _read_hashed(path)
    if digest != binding["sha256"]:
        raise FlowError("Quality source changed; preserve the old packet and review a new revision")
    return _at(value, binding["path"])


def validate_quality_case(root, case, mode):
    if mode not in {"calibrate", "assess"}:
        raise FlowError("Unknown quality working mode")
    if (set(case["input"]) != {"packet", "source"} or any(key in case for key in
            ("node", "start_after", "stop_before", "service_records", "trace_boundaries"))):
        raise FlowError("Quality cases use only packet/source input and cannot run tools or partial application paths")
    packet, source = case["input"]["packet"], case["input"]["source"]
    validate_packet(packet)
    if (not isinstance(source, dict) or set(source) != {"kind", "bindings"}
            or source["kind"] not in {"curated", "agent_receipt"}
            or not isinstance(source["bindings"], dict) or set(source["bindings"]) != set(packet)):
        raise FlowError("Every packet field needs a reviewed file/hash/JSON-path binding")
    for key, binding in source["bindings"].items():
        if canonical_hash(_bound(root, binding)) != canonical_hash(packet[key]):
            raise FlowError("Quality input differs from its bound source")
    if source["kind"] == "agent_receipt":
        _validate_agent_source(root, source, packet)
    if mode == "assess" and source["kind"] != "agent_receipt":
        raise FlowError("Assessment needs an original agent receipt, not a curated answer")
    _validate_quality_labels(case, packet, mode)


def _validate_quality_labels(case, packet, mode):
    labels = [item for item in case.get("assertions", []) if item["path"] == "assessment.semantic_pass"]
    if len(labels) != 1 or type(labels[0].get("equals")) is not bool:
        raise FlowError("Quality cases require one external boolean semantic_pass expectation")
    if mode == "calibrate":
        expected_criteria = {"assessment.criteria." + row["id"] for row in packet["criteria"]}
        actual = {item["path"]: item for item in case["assertions"] if item["path"] != "assessment.semantic_pass"}
        if (set(actual) != expected_criteria or len(actual) != len(case["assertions"]) - 1
                or any(item.get("equals") not in {"pass", "fail", "unknown"} for item in actual.values())):
            raise FlowError("Calibration needs explicit external verdict labels for every rubric criterion")
    if mode == "assess" and labels[0]["equals"] is not True:
        raise FlowError("Assessment cannot redefine a rejected answer as an accepted outcome")


def _validate_agent_source(root, source, packet):
    binding = source["bindings"]["answer"]
    segments = binding["path"]
    if (len(segments) < 4 or segments[0] != "results" or type(segments[1]) is not int
            or segments[2] != "output"):
        raise FlowError("Agent answer must bind to output in an original local-run receipt")
    rows, receipt = _receipt(root, binding["file"])
    saved, digest = _read_hashed(_path(root, binding["file"]))
    if receipt["sha256"] != binding["sha256"] or digest != binding["sha256"]:
        raise FlowError("Original receipt changed during quality validation")
    original = saved["results"][segments[1]]
    _validate_original_question(source, binding, saved, original)
    if (original.get("passed") is not True or not original.get("experiment_sha256") or original["case_id"] not in rows
            or "quality_mode" in original or "quality_assessment" in original
            or rows[original["case_id"]]["execution_controls"] is None):
        raise FlowError("Quality requires a closed, identified source run; technical failures remain separate")
    identity = packet.get("context", {}).get("generation_identity")
    if identity is not None:
        observed = {key: original.get(key) for key in
                    ("config_sha256", "package_sha256", "engine_sha256", "environment_sha256", "mode")}
        observed["model_settings"] = rows[original["case_id"]]["execution_controls"]["requested_model_settings"]
        if canonical_hash(identity) != canonical_hash(observed):
            raise FlowError("Generation identity must match the original agent receipt and model controls")


def _validate_original_question(source, binding, saved, original):
    question = source["bindings"]["question"]
    if (not isinstance(question, dict) or set(question) != {"file", "sha256", "path"}
            or question["file"] != binding["file"] or question["sha256"] != binding["sha256"]):
        raise FlowError("The assessed question must bind to the same original agent receipt")
    parts = question["path"]
    same_input = (len(parts) >= 5 and parts[0] == "experiments" and type(parts[1]) is int
                  and 0 <= parts[1] < len(saved.get("experiments", [])) and parts[2:4] == ["case", "input"]
                  and saved["experiments"][parts[1]].get("experiment_sha256") == original.get("experiment_sha256"))
    if not same_input:
        raise FlowError("Assessed question must come from this source run's original input")


def _signature(root, config, cases, real):
    rubrics = {canonical_hash(case["input"]["packet"]["criteria"]) for case in cases}
    if len(rubrics) != 1:
        raise FlowError("One quality run requires one reviewed rubric")
    return canonical_hash({"rubric_sha256": next(iter(rubrics)), "real": real,
                           "model": config.get("model", {}), **execution_identity(root)})


def _calibration(root, reference, signature):
    value, report_digest = _read_hashed(_path(root, reference))
    if (not isinstance(value, dict) or value.get("kind") != "quality_calibration"
            or value.get("calibration_signature") != signature or value.get("calibration_ready") is not True):
        raise FlowError("Quality calibration is missing, failed, fixture-only or stale for this rubric/model/executor")
    rows, receipt = _receipt(root, value["run_receipt"]["path"])
    if receipt != value["run_receipt"] or not rows or not all(row["passed"] for row in rows.values()):
        raise FlowError("Calibration execution receipt changed or contains failed checks")
    saved, digest = _read_hashed(_path(root, receipt["path"]))
    if digest != receipt["sha256"]:
        raise FlowError("Calibration receipt changed during validation")
    cases = [item.get("case") for item in saved.get("experiments", [])]
    _, config = load_project(root)
    real = {row.get("mode") == "local_real_oci_model" for row in rows.values()}
    if (len(real) != 1 or len(cases) != len(rows) or any(not isinstance(case, dict) for case in cases)
            or _signature(root, config, cases, next(iter(real))) != signature):
        raise FlowError("Calibration does not match its frozen cases and model identity")
    from .campaign import campaign_status
    attempts = {item["id"]: item for item in campaign_status(root)["attempts"]}
    labels = set()
    current_identity = execution_identity(root)
    for case in cases:
        row = rows.get(case["id"], {})
        validate_quality_case(root, case, "calibrate")
        labels.add(_validate_calibration_case(case, row, attempts, receipt, current_identity, config))
    if labels != {True, False}:
        raise FlowError("Calibration requires reviewed positive and negative examples")
    return {"path": str(reference), "sha256": report_digest}


def _validate_calibration_case(case, row, attempts, receipt, current_identity, config):
    attempt = attempts.get(row.get("campaign_attempt_id"), {})
    if (attempt.get("state") != "COMPLETED" or attempt.get("passed") is not True
            or attempt.get("experiment_sha256") != row.get("experiment_sha256")
            or attempt.get("result_artifact") != receipt["path"]):
        raise FlowError("Calibration campaign attempt is not closed and bound to this execution")
    expected = next(item["equals"] for item in case["assertions"] if item["path"] == "assessment.semantic_pass")
    if (row.get("quality_mode") != "calibrate" or row.get("quality_assessment", {}).get("semantic_pass") is not expected
            or any(row.get(key) != current_identity[key] for key in current_identity)
            or row.get("config_sha256") != canonical_hash(config)):
        raise FlowError("Calibration lacks matching judged labels or current evaluator identity")
    return expected


def run_quality(root, case_file, *, mode, selected=None, real=False, timeout=120,
                hypothesis=None, evidence=None, repeat_reason=None, plan=False, calibration=None):
    from .evaluation import _select_cases, run_cases

    root, config = load_project(root)
    path = Path(case_file)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root)
        except ValueError:
            raise FlowError("Quality case files must remain inside the project") from None
    cases = _select_cases(_read(_path(root, path)), selected)
    for case in cases:
        validate_quality_case(root, case, mode)
    signature = _signature(root, config, cases, real)
    calibration_ref = None
    if mode == "assess":
        if not calibration:
            raise FlowError("Calibrate the judge on reviewed positive and negative examples before assessment")
        calibration_ref = _calibration(root, calibration, signature)
    result = run_cases(root, str(path), selected=selected, real=real, timeout=timeout, max_steps=5,
                       hypothesis=hypothesis, evidence=evidence, repeat_reason=repeat_reason,
                       require_campaign=True, plan=plan, quality_mode=mode, case_snapshot_sha256=canonical_hash(cases))
    if plan:
        return {**result, "quality_mode": mode, "calibration_signature": signature, "calibration": calibration_ref}
    rows, receipt = _receipt(root, Path(result["artifact"]).relative_to(root).as_posix())
    expected = {case["id"]: next(a["equals"] for a in case["assertions"]
                                if a["path"] == "assessment.semantic_pass") for case in cases}
    summary = []
    for case in cases:
        row = rows.get(case["id"], {})
        assessment = row.get("quality_assessment")
        valid = isinstance(assessment, dict) and type(assessment.get("semantic_pass")) is bool
        summary.append({"case_id": case["id"], "execution_ok": valid,
                        "expected_semantic_pass": expected[case["id"]] if mode == "calibrate" else None,
                        "semantic_pass": assessment["semantic_pass"] if valid else None,
                        "checks_passed": row.get("passed", False), "assessment": assessment,
                        "duration_seconds": row.get("duration_seconds"), "model_calls": row.get("model_calls"),
                        **{key: row.get(key) for key in ("failure_code", "quality_validation_code", "quality_debug_artifact", "provider_cause", "next_action")}})
    valid_set = result["passed"] and not result.get("campaign_stopped") and len(rows) == len(cases) and all(row["execution_ok"] and row["checks_passed"] for row in summary)
    false_accepts = sum(not row["expected_semantic_pass"] and row["semantic_pass"] is True for row in summary) if mode == "calibrate" else None
    false_rejects = sum(row["expected_semantic_pass"] and row["semantic_pass"] is False for row in summary) if mode == "calibrate" else None
    ready = mode == "calibrate" and valid_set and set(expected.values()) == {True, False}
    artifact = root / ".aidp-local/quality" / (uuid4().hex + ".json")
    report = {"schema_version": 1, "kind": "quality_calibration" if mode == "calibrate" else "quality_assessment",
              "passed": valid_set and (ready if mode == "calibrate" else all(row["semantic_pass"] for row in summary)),
              "calibration_ready": ready, "calibration_signature": signature, "calibration": calibration_ref,
              "run_receipt": receipt, "cases": summary, "false_accepts": false_accepts, "false_rejects": false_rejects,
              "campaign_stopped": result.get("campaign_stopped"), "not_run": result.get("not_run", []),
              "native_test_accepted": False,
              "limitations": ["Calibration agreement applies only to this finite reviewed set, not population accuracy",
                              "Labels need independent domain review; Codex curation is not human validation",
                              "No automatic prompt edits, publication, representativeness claim or universal percentage"]}
    if mode == "assess":
        from .quality_stability import reference_stability
        report["reference_stability"] = reference_stability(cases, summary)
    private_json(artifact, redact(report))
    return {**report, "artifact": str(artifact)}
