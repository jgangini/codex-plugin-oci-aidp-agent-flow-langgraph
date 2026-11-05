"""Inspect and record an evaluator adoption without rewriting campaign evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from uuid import uuid4

from . import __version__
from .campaign import _lock, _path, _records, _totals, load_policy
from .identity import engine_identity
from .project import FlowError, canonical_hash, load_project, private_json


def _snapshot(root, rows, policy):
    folder = _path(root, ".aidp-local/campaign/attempts")
    attempts = {row["id"]: hashlib.sha256((folder / (row["id"] + ".json")).read_bytes()).hexdigest() for row in rows}
    return {"policy_sha256": canonical_hash(policy), "attempts": attempts,
            "ledger_sha256": canonical_hash(attempts)}


def _receipt_versions(root):
    from .progress import _receipts
    sources = {"local_runs": (".aidp-local/runs", "results"),
               "native_invocations": (".aidp-local/invocations", None),
               "TEST_reviews": (".aidp-local/progress/reviews", None)}
    result = {}
    for name, (folder, key) in sources.items():
        receipts = _receipts(root, folder, key)
        result[name] = dict(sorted(Counter(_version_label(row["value"]) for row in receipts).items()))
    return result


def _version_label(receipt):
    version = receipt.get("evaluator_version")
    if version is None:
        return "unrecorded"
    if isinstance(version, str) and len(version) <= 64 and re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?", version):
        return version
    return "invalid_metadata"


def _preview(root, rows, policy):
    totals = _totals(rows)
    active = [row["id"] for row in rows if row["state"] == "SUBMITTED"]
    return {"engine": engine_identity(), "snapshot": _snapshot(root, rows, policy),
            "historical_receipt_versions": _receipt_versions(root), **totals,
            "active_attempts": active, "adoption_blocked": bool(active),
            "unresolved_usage_preserved": True, "billing_verified": False,
            "policy_changed": False, "historical_acceptance_transferred": False,
            "admission_rechecked_per_attempt": True, "native_test_accepted": False,
            "project_supplements_verified": False,
            "next_checks": ["Review any project-specific launcher or supplement against this engine",
                            "Run a zero-call reproduction and positive control through the project harness",
                            "Revalidate affected criteria; old receipts remain historical evidence"]}


def upgrade_campaign(root, *, apply=False, expected_snapshot=None):
    root, _ = load_project(root)
    with _lock(root):
        policy, rows = load_policy(root), _records(root)
        result = _preview(root, rows, policy)
        identity = canonical_hash({"engine": result["engine"], "snapshot": result["snapshot"]})
        result.update(adoption_sha256=identity, applied=False)
        if not apply:
            return result
        if result["adoption_blocked"]:
            raise FlowError("An experiment is still submitted; reach a safe boundary before adopting an engine")
        if expected_snapshot != identity:
            raise FlowError("Engine or campaign changed; inspect campaign upgrade again before applying")
        folder = _path(root, ".aidp-local/campaign/upgrades")
        if folder.exists() and len(list(folder.glob("*.json"))) >= 100:
            raise FlowError("Campaign upgrade history limit reached; preserve and review it")
        record = {**result, "recorded_at": datetime.now(timezone.utc).isoformat(), "applied": True}
        target = folder / (uuid4().hex + ".json")
        private_json(target, record)
        return {**record, "artifact": str(target)}
