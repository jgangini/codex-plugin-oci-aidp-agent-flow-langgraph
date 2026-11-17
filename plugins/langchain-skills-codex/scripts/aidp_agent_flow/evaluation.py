"""Run selected experiments without refreshing a native deployment."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from . import __version__
from .campaign import finish_attempt, load_policy, reserve_attempt
from .cases import validate_case
from .packaging import inspect_package
from .project import FlowError, canonical_hash, load_project, private_json, python_path, redact
from .progress import load_progress_plan, local_criterion_bindings, try_report_progress
from .identity import execution_identity


def _worker_result(envelope, case_id):
    if not isinstance(envelope, dict):
        raise ValueError("Invalid worker envelope")
    result = envelope.get("result", {})
    if not isinstance(result, dict):
        raise ValueError("Invalid worker result")
    if envelope.get("ok") is True:
        if type(result.get("passed")) is not bool:
            raise ValueError("Missing worker verdict")
        return result
    return {**result, "case_id": case_id, "passed": False,
            "error_type": envelope.get("error_type"), "message": envelope.get("message")}


def _select_cases(cases, selected):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise FlowError("Use a reviewed JSON list containing 1 to 100 cases")
    identifiers = [case.get("id") for case in cases if isinstance(case, dict)]
    if (len(identifiers) != len(cases) or any(not isinstance(i, str) or not i for i in identifiers)
            or len(set(identifiers)) != len(cases)):
        raise FlowError("Each case needs a unique nonempty string id")
    if selected:
        cases = [case for case in cases if case["id"] in selected]
        if set(selected) != {case["id"] for case in cases}:
            raise FlowError("A selected case id was not found")
    for case in cases:
        validate_case(case)
    return cases


def run_cases(root, case_file, *, selected=None, real=False, timeout=120, max_steps=20,
              hypothesis=None, evidence=None, repeat_reason=None, require_campaign=False, plan=False, quality_mode=None, case_snapshot_sha256=None):
    root, config = load_project(root)
    progress_plan = load_progress_plan(root) if quality_mode is None and (root / "node-progress.json").exists() else None
    progress_hash = canonical_hash(progress_plan) if progress_plan is not None else None
    if not 1 <= timeout <= 600 or not 1 <= max_steps <= 200:
        raise FlowError("Choose bounded timeout and graph step limits")
    case_path = Path(case_file).expanduser()
    if not case_path.is_absolute():
        case_path = root / case_path
    cases = _select_cases(json.loads(case_path.read_text(encoding="utf-8")), selected)
    if case_snapshot_sha256 is not None and canonical_hash(cases) != case_snapshot_sha256:
        raise FlowError("Selected quality case snapshot changed before admission")
    if quality_mode is not None:
        from .quality import validate_quality_case
        for case in cases:
            validate_quality_case(root, case, quality_mode)
    call_ceiling = (1 if quality_mode else int(config.get("model", {}).get("max_calls", 3))) if real else 0
    if real and not selected:
        raise FlowError("Real-model tests require explicit --case selection")
    campaigning = (root / "test-campaign.json").exists()
    if (real or require_campaign) and not campaigning:
        raise FlowError("CLI and real-model experiments require an explicit campaign policy and hypothesis")
    if campaigning:
        load_policy(root)
    package = inspect_package(root)
    executable = python_path(root)
    executor = execution_identity(root, executable)
    if executor["environment_observed"] is not True:
        raise FlowError("Project runtime metadata is unavailable; repair observation before admission")
    def case_identity(case):
        value = {"case_sha256": canonical_hash(case), "config_sha256": canonical_hash(config),
                 "package_sha256": package["package_sha256"], "real": real,
                 "max_steps": max_steps, "timeout_seconds": timeout, "runner_version": __version__,
                 "evaluator_version": __version__, **executor}
        if quality_mode is not None:
            value["quality_mode"] = quality_mode
        if progress_hash is not None:
            value["progress_plan_sha256"] = progress_hash
            value["criterion_bindings"] = local_criterion_bindings(root, progress_plan, case_path, case, real)
        return value
    if plan:
        if not campaigning:
            raise FlowError("Capacity preview requires a configured campaign")
        from .capacity import preview_capacity
        return {**preview_capacity(root, [{"case_id": case["id"], "experiment_sha256": canonical_hash(case_identity(case))}
                                          for case in cases], real=real,
                    model_calls=call_ceiling,
                    repeat_reason=repeat_reason), **executor,
                "preparation_checked": ["case_contracts", "package", "python_environment", "campaign_capacity"],
                "not_checked": ["agent_factory", "provider_access", "semantic_quality", "native_parity"],
                "hypothesis_required_at_execution": True}
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    environment["PYTHONUTF8"] = "1"
    environment["LANGSMITH_TRACING"] = "false"
    environment["LANGCHAIN_TRACING_V2"] = "false"
    results, experiments, stopped = [], [], None
    artifact = root / (".aidp-local/quality-runs" if quality_mode is not None else ".aidp-local/runs") / (uuid4().hex + ".json")
    for case in cases:
        job = {"project": str(root), "case": case, "real": real, "max_steps": max_steps}
        if quality_mode is not None:
            job["quality_mode"] = quality_mode
        identity = case_identity(case)
        experiment_hash = canonical_hash(identity)
        attempt = None
        if campaigning:
            try:
                attempt = reserve_attempt(root, case_id=case["id"], experiment_sha256=experiment_hash,
                    kind="real" if real else "fixture", model_calls=call_ceiling,
                    hypothesis=hypothesis, evidence=evidence, repeat_reason=repeat_reason,
                    targets=[node["id"] + "/" + criterion["id"] for node in (progress_plan or {}).get("nodes", [])
                             for criterion in node["criteria"] if criterion["case_id"] == case["id"]])
            except FlowError as error:
                if not results:
                    raise
                stopped = str(error)
                break
        experiments.append({**identity, "experiment_sha256": experiment_hash,
                            "case": redact(case), "case_snapshot_redacted": True,
                            "requested_model_settings": {key: config.get("model", {})[key] for key in
                                ("model_id", "region", "max_tokens", "max_calls", "reasoning_effort", "read_timeout_seconds")
                                if key in config.get("model", {})}})
        if quality_mode is not None:
            experiments[-1]["requested_model_settings"]["max_calls"] = 1
        started = time.monotonic()
        try:
            process = subprocess.run([str(executable), "-m", "aidp_agent_flow.worker"],
                input=json.dumps(job), text=True, encoding="utf-8", capture_output=True,
                cwd=root, env=environment, timeout=timeout)
            envelope = json.loads(process.stdout)
            result = _worker_result(envelope, case["id"])
        except subprocess.TimeoutExpired:
            result = {"case_id": case["id"], "passed": False, "error_type": "Timeout",
                      "message": "Local worker stopped; any external operation must be reconciled before retry"}
        except (ValueError, KeyError):
            result = {"case_id": case["id"], "passed": False, "error_type": "WorkerProtocol",
                      "message": "Project environment or worker output is incompatible"}
        result.update(duration_seconds=round(time.monotonic() - started, 3),
                      recorded_at=datetime.now(timezone.utc).isoformat(),
                      mode="local_real_oci_model" if real else "local_fixture_model",
                      evaluator_version=__version__, **executor,
                      input_sha256=canonical_hash(case["input"]), **{key: identity[key] for key in
                      ("case_sha256", "config_sha256", "package_sha256")}, experiment_sha256=experiment_hash)
        if quality_mode is not None:
            result["quality_mode"] = quality_mode
        if progress_hash is not None:
            result["progress_plan_sha256"] = progress_hash
            result["criterion_bindings"] = identity["criterion_bindings"]
        if attempt is not None:
            result["campaign_attempt_id"] = attempt
        results.append(result)
        private_json(artifact, redact({"results": results, "experiments": experiments, "native_test_accepted": False}),
                     overwrite=len(results) > 1)
        if attempt is not None:
            try:
                finish_attempt(root, attempt, result, artifact.relative_to(root))
            except Exception:
                stopped = "Execution receipt saved, but campaign completion failed; reconcile before another experiment"
                break
    summary = [{key: value for key, value in result.items() if key != "output"} for result in results]
    result = {"passed": stopped is None and all(item["passed"] for item in results), "cases": summary,
              "artifact": str(artifact), "native_test_accepted": False}
    if stopped is not None:
        result.update(campaign_stopped=stopped, not_run=[case["id"] for case in cases[len(results):]])
    if progress_hash is not None:
        result["progress"] = try_report_progress(root)
    return result
