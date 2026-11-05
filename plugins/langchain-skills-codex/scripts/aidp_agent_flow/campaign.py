"""Bounded experiment admission and reconciliation; never an automatic retry loop."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from .project import FlowError, canonical_hash, contained, load_project, private_json, redact
from .diagnostics import next_action

_STATES = {"SUBMITTED", "UNCERTAIN", "TERMINAL_USAGE_UNKNOWN", "COMPLETED"}
_UNRESOLVED = _STATES - {"COMPLETED"}


def _validate_record(row, expected_id=None):
    identifier = row.get("id")
    if (not isinstance(identifier, str) or len(identifier) != 32
            or any(c not in "0123456789abcdef" for c in identifier)
            or expected_id is not None and identifier != expected_id):
        raise FlowError("Campaign record identity is invalid; preserve and reconcile the ledger")
    if row.get("state") not in _STATES or row.get("kind") not in ("fixture", "real", "native"):
        raise FlowError("Unknown campaign state or kind; no experiment can be admitted")
    _validate_accounting(row)
    if not isinstance(row.get("history"), list) or len(row["history"]) > 20:
        raise FlowError("Campaign reconciliation history is invalid")
    return row


def _validate_accounting(row):
    reserved, actual = row.get("reserved_model_calls"), row.get("model_calls")
    if type(reserved) is not int or reserved < 0 or actual is not None and (type(actual) is not int or actual < 0):
        raise FlowError("Campaign call accounting is invalid; do not discard reservations")
    if row["kind"] == "fixture" and (reserved != 0 or actual not in (None, 0)):
        raise FlowError("Fixture ledger entries cannot conceal paid call consumption")
    for key in ("cost_usd", "reserved_cost_usd"):
        if key not in row:
            raise FlowError("Campaign cost accounting fields must be explicit")
        _money(row[key], key)


def _path(root, relative):
    if not isinstance(relative, (str, Path)):
        raise FlowError("Campaign references must be project-relative paths")
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise FlowError("Campaign evidence must stay inside the selected project")
    path = root / value
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise FlowError("Campaign paths cannot use linked ancestors")
    return contained(root, value)


def _read(path):
    try:
        with path.open("rb") as stream:
            data = stream.read(1_048_577)
        if len(data) > 1_048_576:
            raise ValueError
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise FlowError("Campaign JSON is invalid or exceeds its size limit") from None


def _money(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise FlowError("Campaign " + name + " must be a nonnegative decimal or null")
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal("1000000000"):
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise FlowError("Campaign " + name + " must be a finite nonnegative amount") from None


def load_policy(root):
    policy = _read(_path(root, "test-campaign.json"))
    _validate_policy_value(policy)
    return policy


@contextmanager
def _lock(root):
    path = _path(root, ".aidp-local/campaign/lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise FlowError("Campaign is locked; reconcile the active owner before another attempt") from None
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink()


def _records(root):
    folder = _path(root, ".aidp-local/campaign/attempts")
    paths = list(folder.glob("*.json")) if folder.exists() else []
    if len(paths) > 10000:
        raise FlowError("Campaign history exceeds its admission limit")
    checked = [_path(root, path.relative_to(root)) for path in paths]
    if sum(path.stat().st_size for path in checked) > 64 * 1024 * 1024:
        raise FlowError("Campaign history exceeds 64 MiB")
    return sorted((_validate_record(_read(path), path.stem) for path in checked),
                  key=lambda row: str(row.get("recorded_at", "")))


def _totals(records):
    used, charge, unknown, unpriced = 0, Decimal(0), 0, 0
    for row in records:
        _validate_record(row)
        calls = row.get("model_calls")
        used += (max(calls or 0, row["reserved_model_calls"]) if row["state"] in _UNRESOLVED
                 else calls if calls is not None else row["reserved_model_calls"])
        actual = _money(row.get("cost_usd"), "recorded cost")
        reserved = _money(row.get("reserved_cost_usd"), "reserved cost")
        if actual is None:
            unknown += row.get("kind") != "fixture"
            unpriced += row.get("kind") != "fixture" and reserved is None
        charge += (max(actual or Decimal(0), reserved or Decimal(0)) if row["state"] in _UNRESOLVED
                   else actual if actual is not None else reserved or Decimal(0))
    return {"attempts": len(records), "model_calls_used_or_reserved": used,
            "cost_used_or_reserved_usd": str(charge), "unknown_cost_attempts": unknown,
            "unpriced_attempts": unpriced,
            "unresolved_attempts": [row["id"] for row in records if row["state"] in _UNRESOLVED]}


def campaign_status(root):
    root, _ = load_project(root)
    policy = load_policy(root)
    with _lock(root):
        records = _records(root)
        totals = _totals(records)
    return {"policy": policy, **totals, "billing_verified": False,
            "attempts": [{key: row.get(key) for key in ("id", "case_id", "kind", "state", "hypothesis", "targets",
                "experiment_sha256", "result_artifact", "passed", "decision", "model_calls", "cost_usd",
                "reserved_model_calls", "reserved_cost_usd", "recorded_at")} for row in records]}


def initialize_campaign(root, definition):
    root, _ = load_project(root)
    target = _path(root, "test-campaign.json")
    if target.exists():
        raise FlowError("Existing campaign policy was preserved")
    policy = _read(_path(root, definition))
    _validate_policy_value(policy)
    private_json(target, policy)
    return campaign_status(root)


def require_campaign_clear(root):
    root, _ = load_project(root)
    if not _path(root, "test-campaign.json").exists():
        return {"configured": False}
    status = campaign_status(root)
    if status["unresolved_attempts"]:
        raise FlowError("Unresolved campaign experiments block publication; reconcile them first")
    if status["model_calls_used_or_reserved"] > status["policy"]["max_model_calls"]:
        raise FlowError("Campaign model-call consumption exceeds the configured limit")
    budget = _money(status["policy"]["budget_usd"], "budget")
    if budget is not None and (status["unpriced_attempts"]
            or Decimal(status["cost_used_or_reserved_usd"]) > budget):
        raise FlowError("Campaign costs are unpriced or exceed the finite budget")
    return {"configured": True, "unresolved_attempts": [], "billing_verified": False}


def _validate_policy_value(policy):
    expected = {"version", "max_attempts", "max_model_calls", "max_identical_trials", "native_call_ceiling",
                "budget_usd", "real_cost_ceiling_usd", "native_cost_ceiling_usd"}
    if set(policy) != expected:
        raise FlowError("Campaign policy must contain only its explicit limits and cost fields")
    for name, upper in (("max_attempts", 10000), ("max_model_calls", 100000),
                        ("max_identical_trials", 100), ("native_call_ceiling", 1000)):
        if type(policy.get(name)) is not int or not 0 <= policy[name] <= upper:
            raise FlowError("Campaign integer limit is missing or invalid: " + name)
    if type(policy.get("version")) is not int or policy["version"] != 1 or not policy["max_attempts"] or not policy["max_identical_trials"]:
        raise FlowError("Campaign policy version or attempt limits are invalid")
    for name in ("budget_usd", "real_cost_ceiling_usd", "native_cost_ceiling_usd"):
        if name not in policy:
            raise FlowError("Campaign cost fields must be explicit")
        _money(policy[name], name)


def _evidence(root, paths):
    if not isinstance(paths, list) or len(paths) > 20:
        raise FlowError("Use at most twenty project evidence references")
    result = []
    for relative in paths:
        path = _path(root, relative)
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise FlowError("Campaign evidence must be a bounded existing project file")
        result.append({"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def _check_admission(policy, rows, kind, model_calls, ceiling, budget, experiment_sha256, repeat_reason):
    totals = _totals(rows)
    if any(row["state"] == "SUBMITTED" for row in rows):
        raise FlowError("An experiment is active; reconcile its owner before another attempt")
    identical = [row for row in rows if row["experiment_sha256"] == experiment_sha256]
    if identical and (not isinstance(repeat_reason, str) or not repeat_reason.strip() or len(repeat_reason) > 2000):
        raise FlowError("An identical experiment needs an explicit repeat rationale; change the hypothesis or inputs first")
    if len(identical) >= policy["max_identical_trials"] or len(rows) >= policy["max_attempts"]:
        raise FlowError("Campaign trial limit reached; do not repeat without revising the authorized plan")
    if kind != "fixture":
        _check_paid_capacity(policy, totals, model_calls, ceiling, budget)


def _check_paid_capacity(policy, totals, model_calls, ceiling, budget):
    if totals["unresolved_attempts"]:
        raise FlowError("An experiment is unresolved; reconcile it before another attempt")
    if budget is not None and totals["unpriced_attempts"]:
        raise FlowError("Unpriced historical attempts must be reconciled before enforcing a finite budget")
    if totals["model_calls_used_or_reserved"] + model_calls > policy["max_model_calls"]:
        raise FlowError("Campaign model-call budget would be exceeded")
    if budget is not None and Decimal(totals["cost_used_or_reserved_usd"]) + (ceiling or 0) > budget:
        raise FlowError("Campaign cost reservations would exceed the configured budget")


def validate_reservation_identity(case_id, experiment_sha256, kind, model_calls):
    if kind not in ("fixture", "real", "native") or type(model_calls) is not int or model_calls < 0:
        raise FlowError("Invalid campaign invocation reservation")
    if kind == "fixture" and model_calls != 0:
        raise FlowError("Fixture experiments cannot reserve paid model calls")
    if not isinstance(case_id, str) or not case_id or len(case_id) > 128:
        raise FlowError("Campaign case id must be a bounded nonempty string")
    if (not isinstance(experiment_sha256, str) or len(experiment_sha256) != 64
            or any(char not in "0123456789abcdef" for char in experiment_sha256)):
        raise FlowError("Campaign experiment identity must be a SHA-256 digest")


def reserve_attempt(root, *, case_id, experiment_sha256, kind, model_calls, hypothesis, evidence=None,
                    repeat_reason=None, targets=None):
    root, _ = load_project(root)
    validate_reservation_identity(case_id, experiment_sha256, kind, model_calls)
    if not isinstance(hypothesis, str) or not hypothesis.strip() or len(hypothesis) > 2000:
        raise FlowError("A configured campaign requires a bounded hypothesis before execution")
    policy = load_policy(root)
    refs = _evidence(root, evidence or [])
    ceiling = Decimal(0) if kind == "fixture" else _money(policy[kind + "_cost_ceiling_usd"], "cost ceiling")
    budget = _money(policy["budget_usd"], "budget")
    if kind != "fixture" and (not model_calls or budget is not None and ceiling is None):
        raise FlowError("Paid experiments need a call ceiling and a cost reservation for a finite budget")
    with _lock(root):
        rows = _records(root)
        _check_admission(policy, rows, kind, model_calls, ceiling, budget, experiment_sha256, repeat_reason)
        row = {"id": uuid4().hex, "case_id": case_id, "experiment_sha256": experiment_sha256,
               "policy_sha256": canonical_hash(policy), "kind": kind, "state": "SUBMITTED",
               "hypothesis": redact(hypothesis), "evidence": refs, "repeat_reason": redact(repeat_reason),
               "targets": targets or [], "reserved_model_calls": model_calls, "model_calls": None,
               "reserved_cost_usd": str(ceiling) if ceiling is not None else None, "cost_usd": "0" if kind == "fixture" else None,
               "recorded_at": datetime.now(timezone.utc).isoformat(), "history": []}
        private_json(_path(root, ".aidp-local/campaign/attempts/" + row["id"] + ".json"), row)
        return row["id"]


def finish_attempt(root, attempt, result, artifact):
    root, _ = load_project(root)
    if not isinstance(attempt, str) or len(attempt) != 32 or any(c not in "0123456789abcdef" for c in attempt):
        raise FlowError("Invalid campaign attempt identifier")
    with _lock(root):
        path = _path(root, ".aidp-local/campaign/attempts/" + attempt + ".json")
        row = _validate_record(_read(path), attempt)
        if row["state"] != "SUBMITTED":
            raise FlowError("Campaign attempt was already completed or reconciled")
        uncertain = result.get("error_type") in ("Timeout", "WorkerProtocol") or bool(result.get("failure"))
        calls = result.get("model_calls")
        row.update(state="UNCERTAIN" if uncertain else "COMPLETED", passed=result.get("passed") is True,
                   model_calls=0 if row["kind"] == "fixture" else calls if type(calls) is int and calls >= 0 else None,
                   adapter_model_calls=calls if type(calls) is int and calls >= 0 else None,
                   result_artifact=_path(root, artifact).relative_to(root).as_posix(),
                    decision="reconcile" if uncertain else next_action(result),
                   finished_at=datetime.now(timezone.utc).isoformat())
        if row["model_calls"] == 0 and not uncertain:
            row["cost_usd"] = "0"
        private_json(path, row, overwrite=True)


def reconcile_attempt(root, attempt, *, model_calls, cost_usd, evidence, note):
    root, _ = load_project(root)
    if not isinstance(attempt, str) or len(attempt) != 32 or any(c not in "0123456789abcdef" for c in attempt):
        raise FlowError("Invalid campaign attempt identifier")
    if type(model_calls) is not int or model_calls < 0 or not isinstance(note, str) or not note.strip() or len(note) > 2000:
        raise FlowError("Reconciliation needs actual call count and a bounded nonsecret explanation")
    amount = _money(cost_usd, "actual cost")
    refs = _evidence(root, [evidence])
    with _lock(root):
        path = _path(root, ".aidp-local/campaign/attempts/" + attempt + ".json")
        row = _validate_record(_read(path), attempt)
        if len(row["history"]) >= 20:
            raise FlowError("Campaign reconciliation history limit reached")
        row["history"].append({"prior_state": row["state"], "prior_model_calls": row["model_calls"],
                               "prior_cost_usd": row["cost_usd"], "note": redact(note), "evidence": refs,
                               "recorded_at": datetime.now(timezone.utc).isoformat()})
        row.update(state="COMPLETED", model_calls=model_calls, cost_usd=str(amount) if amount is not None else None,
                   decision="reconciled_by_operator")
        _validate_record(row, attempt)
        private_json(path, row, overwrite=True)
    return campaign_status(root)
