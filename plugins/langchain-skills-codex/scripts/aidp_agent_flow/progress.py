"""Evidence-derived validation coverage for an explicit inventory of graph nodes."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from . import __version__
from .cases import validate_case
from .identity import execution_identity
from .packaging import inspect_package
from .project import FlowError, canonical_hash, contained, load_project, private_json, redact
from .progress_scope import known_fields, scope_decision, validate_scope, validate_transition
from .remote import WorkbenchClient


_MAX_JSON = 8 * 1024 * 1024
_MAX_RECEIPTS = 2000
_MAX_HISTORY_BYTES = 64 * 1024 * 1024
_MAX_HISTORY_ROWS = 10000


def _unlinked(path):
    for item in (path, *path.parents):
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise FlowError("Progress paths cannot use symlinks or junctions")


def _path(root, relative):
    if not isinstance(relative, (str, Path)):
        raise FlowError("Progress references must be relative project paths")
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise FlowError("Progress references must be relative paths inside the project")
    _unlinked(root / value)
    return contained(root, value)


def _project(root):
    root = Path(root).absolute()
    _unlinked(root)
    _unlinked(root / "aidp-agent.toml")
    return load_project(root)


def _read_hashed(path):
    _unlinked(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(_MAX_JSON + 1)
        if len(data) > _MAX_JSON:
            raise ValueError
        return json.loads(data), hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise FlowError("Progress JSON is unreadable, malformed or exceeds its size limit") from None


def _read(path):
    return _read_hashed(path)[0]


def _text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise FlowError("Progress " + name + " must be a bounded nonempty string")
    return value


def _validate_plan(root, plan):
    if not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] not in (1, 2):
        raise FlowError("Progress plan requires version 1 or 2")
    fields = {"version", "requirements_ref", "nodes", "acceptance"}
    known_fields(plan, fields | ({"revision", "scope_decisions", "publication_policy", "publication_policy_reason"}
                                if plan["version"] == 2 else set()), "progress plan")
    policy = plan.get("publication_policy", "strict_node_layers_v1")
    if not isinstance(policy, str) or policy not in {"strict_node_layers_v1", "declared_requirements_v1"}:
        raise FlowError("Unknown publication policy")
    if policy == "declared_requirements_v1" or "publication_policy_reason" in plan:
        _text(plan.get("publication_policy_reason"), "publication policy reason", 2000)
    # This is an annotation, not a path the reporter opens or executes.
    _text(plan.get("requirements_ref"), "requirements_ref")
    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 500:
        raise FlowError("Progress plan requires 1 to 500 explicitly inventoried nodes")
    seen = set()
    total_criteria = 0
    for node in nodes:
        if not isinstance(node, dict):
            raise FlowError("Each progress node must be an object")
        known_fields(node, ("id", "implementation", "blocker", "criteria"), "progress node")
        node_id = _text(node.get("id"), "node id", 128)
        if node_id == "__agent__" or node_id in seen:
            raise FlowError("Progress node ids must be unique")
        seen.add(node_id)
        if node.get("implementation", "pending") not in ("pending", "declared"):
            raise FlowError("Implementation is a declaration: pending or declared")
        if "blocker" in node:
            _text(node["blocker"], "blocker", 2000)
        criteria = node.get("criteria")
        if not isinstance(criteria, list) or len(criteria) > 500:
            raise FlowError("Each progress node requires a criteria list")
        total_criteria += len(criteria)
        if total_criteria > 2000:
            raise FlowError("Progress plan exceeds 2000 required criteria")
        _validate_criteria(root, criteria)
    acceptance = plan.get("acceptance", [])
    if not isinstance(acceptance, list) or len(acceptance) > 500 or total_criteria + len(acceptance) > 2000:
        raise FlowError("Agent acceptance must be a bounded criteria list")
    _validate_criteria(root, acceptance)
    if any(criterion["layer"] != "TEST" for criterion in acceptance):
        raise FlowError("Agent integration acceptance requires native TEST criteria")
    validate_scope(plan, _text)
    return plan


def _validate_criteria(root, criteria):
    seen = set()
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise FlowError("Each progress criterion must be an object")
        known_fields(criterion, ("id", "description", "case_id", "gate", "group", "weight", "layer",
                                 "scope", "cases_file", "mode"), "progress criterion")
        key = _text(criterion.get("id"), "criterion id", 128)
        if key in seen:
            raise FlowError("Criterion ids must be unique within a node")
        seen.add(key)
        _text(criterion.get("description"), "criterion description", 2000)
        _text(criterion.get("case_id"), "case id", 128)
        for label in ("gate", "group"):
            if label in criterion:
                _text(criterion[label], label, 128)
        weight = criterion.get("weight", 1)
        if type(weight) is not int or not 1 <= weight <= 100:
            raise FlowError("Progress weights must be integers between 1 and 100")
        if criterion.get("layer") not in ("local", "TEST"):
            raise FlowError("Progress criterion layer must be local or TEST")
        if "scope" in criterion and criterion["scope"] not in ("node", "integration"):
            raise FlowError("Progress criterion scope must be node or integration")
        if criterion["layer"] == "TEST" and "cases_file" in criterion:
            raise FlowError("TEST criteria use their native case_id, not a local cases_file")
        if criterion["layer"] == "local":
            _path(root, _text(criterion.get("cases_file"), "cases_file"))
            if criterion.get("mode", "fixture") not in ("fixture", "real"):
                raise FlowError("Local criterion mode must be fixture or real")


def _case(root, criterion):
    case_file = _text(criterion.get("cases_file"), "cases_file")
    cases = _read(_path(root, case_file))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise FlowError("Progress cases_file must contain a bounded case list")
    matches = [case for case in cases if isinstance(case, dict) and case.get("id") == criterion["case_id"]]
    if len(matches) != 1:
        raise FlowError("Progress criterion must match exactly one reviewed local case")
    validate_case(matches[0])
    return matches[0]


def load_progress_plan(root):
    root, _ = _project(root)
    return _validate_plan(root, _read(_path(root, "node-progress.json")))


def initialize_progress(root, definition_file):
    root, _ = _project(root)
    plan = _validate_plan(root, _read(_path(root, definition_file)))
    target = _path(root, "node-progress.json")
    if target.exists():
        raise FlowError("Existing node-progress.json was preserved; use progress report")
    private_json(target, plan)
    return report_progress(root)


def _stamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


def _receipts(root, relative, key=None):
    folder = _path(root, relative)
    if not folder.exists():
        return []
    paths = list(folder.glob("*.json"))
    if len(paths) > _MAX_RECEIPTS:
        raise FlowError("Progress receipt limit reached; archive reviewed historical runs before reporting")
    rows, total_bytes = [], 0
    fields = {"case_id", "case_sha256", "config_sha256", "package_sha256", "progress_plan_sha256", "mode",
              "recorded_at", "passed", "visited_nodes", "model_calls", "failure_stage", "node_id", "criterion_id",
              "verdict", "receipt", "receipt_sha256", "evaluator_version", "model_response_metadata",
              "engine_sha256", "environment_sha256", "environment_observed", "criterion_bindings"}
    for path in paths:
        _unlinked(path)
        total_bytes += path.stat().st_size
        if total_bytes > _MAX_HISTORY_BYTES:
            raise FlowError("Progress history exceeds 64 MiB; archive reviewed historical receipts before reporting")
        value = _read(path)
        if not isinstance(value, dict):
            raise FlowError("Progress receipts must contain JSON objects")
        items = value.get(key, []) if key else [value]
        if not isinstance(items, list):
            raise FlowError("Progress receipt results must be a list")
        for item in items:
            if not isinstance(item, dict):
                raise FlowError("Progress receipt entries must be objects")
            stamp = _stamp(item.get("recorded_at", value.get("recorded_at")))
            if len(rows) >= _MAX_HISTORY_ROWS:
                raise FlowError("Progress history exceeds 10000 entries; archive reviewed historical receipts")
            rows.append({"value": {name: item[name] for name in fields if name in item}, "path": path.relative_to(root).as_posix(),
                         "stamp": stamp, "mtime": path.stat().st_mtime_ns})
    return rows


def _same_revision(value, identity):
    return all(value.get(key) == expected for key, expected in identity.items())


def _latest(rows):
    dated = [row for row in rows if row["stamp"] is not None]
    return max(dated, key=lambda row: (row["stamp"], row["mtime"])) if dated else None


def _stale_reasons(rows, wanted):
    latest = _latest(rows)
    if latest is None:
        return ["missing_or_invalid_recorded_at"] if rows else []
    value = latest["value"]
    return [("missing_" if value.get(key) is None else "changed_") + key
            for key, expected in wanted.items() if value.get(key) != expected]


def _historical_pass(rows, selected, predicate):
    previous = _latest([row for row in rows if row is not selected and predicate(row["value"])])
    if previous is None:
        return None
    value = previous["value"]
    metadata = {key: value[key] for key in ("evaluator_version", "package_sha256", "config_sha256",
                "progress_plan_sha256", "case_sha256", "mode", "engine_sha256", "environment_sha256")
                if isinstance(value.get(key), str) and len(value[key]) <= 128}
    if type(value.get("environment_observed")) is bool:
        metadata["environment_observed"] = value["environment_observed"]
    return {"evidence": previous["path"], "recorded_at": previous["stamp"].isoformat(),
            "basis": "recorded_pass_not_current_acceptance", **metadata}


def _visited_nodes(value):
    nodes = value.get("visited_nodes")
    return nodes if isinstance(nodes, list) and all(isinstance(node, str) for node in nodes) else []


def _local_failures(result, node_id, mode):
    reasons = []
    if result.get("passed") is not True:
        reasons.append("runner_did_not_pass")
    if node_id not in _visited_nodes(result):
        reasons.append("mapped_node_not_completed")
    if mode == "real":
        if type(result.get("model_calls")) is not int or result["model_calls"] <= 0:
            reasons.append("real_model_call_missing")
        metadata = result.get("model_response_metadata")
        if not (isinstance(metadata, list) and any(isinstance(item, dict) and item.get("complete") is True
                                                for item in metadata)):
            reasons.append("complete_model_response_missing")
    return reasons


def _local_result(root, node_id, criterion, rows, identity, fingerprint=None):
    relevant = [row for row in rows if row["value"].get("case_id") == criterion["case_id"]]
    mode = "local_real_oci_model" if criterion.get("mode") == "real" else "local_fixture_model"
    historical = lambda selected: _historical_pass(relevant, selected, lambda value:
        value.get("passed") is True and value.get("mode") == mode and node_id in _visited_nodes(value))
    try:
        case = _case(root, criterion)
    except FlowError:
        return {"state": "pending", "evidence": None, "configuration": "reviewed_case_unavailable",
                "configuration_reason": "The declared case is missing, duplicated, malformed or unreadable; repair cases_file/case_id.",
                "historical_pass": historical(None)}
    scope = criterion.get("scope", "node" if criterion.get("mode") == "real" else "integration")
    if scope == "node" and case.get("node") != node_id:
        return {"state": "pending", "evidence": None, "configuration": "direct_node_case_required",
                "configuration_reason": "The case node selector must name this node for scope=node.",
                "historical_pass": historical(None)}
    wanted = {**identity, "case_sha256": canonical_hash(case), "mode": mode}
    current = [row for row in relevant if _matches_criterion(row["value"], wanted, node_id, criterion["id"], fingerprint)
               and identity.get("environment_observed") is True and row["value"].get("environment_observed") is True]
    selected = _latest(current)
    if selected is None:
        reasons = _criterion_stale_reasons(relevant, wanted, node_id, criterion["id"], fingerprint)
        if identity.get("environment_observed") is not True:
            reasons.append("environment_observation_unavailable")
        return {"state": "stale" if relevant else "pending", "evidence": None,
                "stale_reasons": reasons, "historical_pass": historical(None)}
    result = selected["value"]
    failures = _local_failures(result, node_id, criterion.get("mode"))
    return {"state": "failed" if failures else "passed", "evidence": selected["path"],
            "recorded_at": result.get("recorded_at"), "failure_stage": result.get("failure_stage"),
            "failure_reasons": failures, "historical_pass": historical(selected), **_reuse_details(selected, identity)}


def criterion_fingerprint(plan, node_id, criterion):
    node = next((item for item in plan["nodes"] if item["id"] == node_id), None)
    if node is None:
        raise FlowError("Criterion fingerprints require an inventoried node")
    return canonical_hash({
        "schema": "criterion-evidence-v1",
        "node": {key: value for key, value in node.items() if key != "criteria"},
        "criterion": criterion,
        "requirements_ref": plan["requirements_ref"],
        "publication_policy": plan.get("publication_policy", "strict_node_layers_v1"),
        "publication_policy_reason": plan.get("publication_policy_reason"),
        "scope_decisions": [item for item in plan.get("scope_decisions", [])
                            if item["node_id"] == node_id and item["criterion_id"] == criterion["id"]],
    })


def local_criterion_bindings(root, plan, case_file, case, real):
    bindings = {}
    for node in plan["nodes"]:
        for criterion in node["criteria"]:
            if (criterion["layer"] == "local" and criterion["case_id"] == case["id"]
                    and (criterion.get("mode", "fixture") == "real") == real
                    and _path(root, criterion["cases_file"]).resolve() == Path(case_file).resolve()):
                bindings.setdefault(node["id"], {})[criterion["id"]] = criterion_fingerprint(plan, node["id"], criterion)
    return bindings


def _criterion_revision(value, identity, node_id, criterion_id, fingerprint):
    if (fingerprint is None or "criterion_bindings" not in value
            or not isinstance(value.get("progress_plan_sha256"), str)
            or re.fullmatch(r"[a-f0-9]{64}", value["progress_plan_sha256"]) is None):
        return value, identity
    bindings = value["criterion_bindings"]
    node = bindings.get(node_id) if isinstance(bindings, dict) else None
    recorded = node.get(criterion_id) if isinstance(node, dict) else None
    return ({**value, "criterion_sha256": recorded},
            {**{key: item for key, item in identity.items() if key != "progress_plan_sha256"},
             "criterion_sha256": fingerprint})


def _matches_criterion(value, identity, node_id, criterion_id, fingerprint):
    value, wanted = _criterion_revision(value, identity, node_id, criterion_id, fingerprint)
    return _same_revision(value, wanted)


def _criterion_stale_reasons(rows, identity, node_id, criterion_id, fingerprint):
    latest = _latest(rows)
    if latest is None:
        return _stale_reasons(rows, identity)
    value, wanted = _criterion_revision(latest["value"], identity, node_id, criterion_id, fingerprint)
    return _stale_reasons([{**latest, "value": value}], wanted)


def _reuse_details(selected, identity):
    previous = selected["value"].get("progress_plan_sha256")
    if previous == identity["progress_plan_sha256"]:
        return {}
    return {"evidence_reused": True, "evidence_plan_sha256": previous,
            "reuse_basis": "unchanged_criterion_same_candidate"}


def _native_identity(root, config):
    client = WorkbenchClient(root, config)
    native = config.get("native", {})
    workspace, agent = native.get("workspace_key"), native.get("agent_key")
    if not agent:
        context = canonical_hash({"target": client.base, "workspace": workspace, "remote_root": native.get("remote_root")})
        saved = _read(_path(root, ".aidp-local/native/" + context[:16] + "/state.json"))
        if not isinstance(saved, dict) or saved.get("target_context") != context:
            raise FlowError("Native progress review has no verified target binding")
        agent = saved.get("agent_key")
    if not workspace or not agent:
        raise FlowError("Native progress review needs the selected workspace and agent identity")
    return {"target": client.base, "workspace": workspace, "agent_key": agent}


def _native_receipt(root, config, criterion, receipt_file, package_hash, accepted, expected_snapshot=None):
    path = _path(root, receipt_file)
    if not path.is_relative_to(root / ".aidp-local/invocations"):
        raise FlowError("TEST reviews require the native invocation receipt inside .aidp-local/invocations")
    value = _read(path)
    expected = {**_native_identity(root, config), "surface": "TEST", "case_id": criterion["case_id"],
                "package_sha256": package_hash, "evaluator_version": __version__, **execution_identity(root)}
    if not isinstance(value, dict) or not _same_revision(value, expected):
        raise FlowError("TEST receipt does not match the selected case, package and native target")
    if not value.get("deployment_key") or not value.get("question_sha256"):
        raise FlowError("TEST receipt lacks deployment or frozen-question identity")
    snapshot = value.get("deployment_snapshot")
    if (value.get("package_binding_verified") is not True or not isinstance(snapshot, list) or not snapshot
            or not any(isinstance(row, dict) and row.get("key") == value["deployment_key"]
                       and row.get("deploymentVersion") == value.get("deployment_version") for row in snapshot)):
        raise FlowError("TEST receipt lacks a verified package/deployment snapshot binding")
    if expected_snapshot is not None and snapshot != expected_snapshot:
        raise FlowError("Accepted TEST evidence belongs to a different deployment snapshot")
    if accepted and (value.get("state") != "RESPONDED" or value.get("stream_complete") is not True
                     or value.get("passed") is not True or value.get("failure") is not None
                     or type(value.get("error_count")) is not int or value["error_count"] != 0):
        raise FlowError("Incomplete or failed native invocations cannot be accepted")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _test_result(root, config, node_id, criterion, rows, identity, fingerprint=None):
    relevant = [row for row in rows if row["value"].get("node_id") == node_id
                and row["value"].get("criterion_id") == criterion["id"]]
    current = [row for row in relevant if _matches_criterion(row["value"], identity, node_id, criterion["id"], fingerprint)]
    selected = _latest(current)
    historical = _historical_pass(relevant, selected, lambda value: value.get("verdict") == "accepted")
    if selected is None:
        return {"state": "stale" if relevant else "pending", "evidence": None,
                "stale_reasons": _criterion_stale_reasons(relevant, identity, node_id, criterion["id"], fingerprint), "historical_pass": historical}
    review = selected["value"]
    try:
        digest = _native_receipt(root, config, criterion, review["receipt"], identity["package_sha256"],
                                 review.get("verdict") == "accepted")
        valid = digest == review.get("receipt_sha256") and review.get("verdict") in ("accepted", "rejected")
    except (FlowError, KeyError):
        valid = False
    return {"state": ("passed" if review["verdict"] == "accepted" else "failed") if valid else "stale",
            "evidence": selected["path"], "recorded_at": review.get("recorded_at"),
            "stale_reasons": [] if valid else ["native_receipt_or_review_binding_invalid"],
            "historical_pass": historical, **(_reuse_details(selected, identity) if valid else {})}


def _coverage(criteria):
    active = [item for item in criteria if item["state"] != "excluded"]
    excluded = [item for item in criteria if item["state"] == "excluded"]
    required = sum(item["weight"] for item in active)
    approved = sum(item["weight"] for item in criteria if item["state"] == "passed")
    percent = round(100 * approved / required, 1) if required else None
    if required and approved < required:
        percent = min(percent, 99.9)
    return {"approved": approved, "required": required,
            "approved_count": sum(item["state"] == "passed" for item in criteria), "required_count": len(active),
            "excluded": sum(item["weight"] for item in excluded), "excluded_count": len(excluded),
            "inventoried": sum(item["weight"] for item in criteria), "inventoried_count": len(criteria),
            "percent": percent}


def _criterion_details(node_id, criterion):
    native = criterion["layer"] == "TEST"
    return {"node_id": node_id, "id": criterion["id"], "description": criterion["description"],
            "layer": criterion["layer"], "weight": criterion.get("weight", 1),
            "mode": "native" if native else criterion.get("mode", "fixture"),
            "scope": "integration" if node_id == "__agent__" else criterion.get("scope",
                "node" if criterion.get("mode") == "real" else "integration"),
            "case_id": criterion["case_id"], "cases_file": criterion.get("cases_file"),
            **{label: criterion[label] for label in ("gate", "group") if label in criterion}}


def _apply_scope(result, decision, identity):
    if decision is None:
        return result
    if decision["state"] != "excluded":
        return {**result, "scope_decision": decision}
    # Keep a previously selected pass as history, never as excluded/current credit.
    history = result.get("historical_pass")
    if result["state"] == "passed":
        history = {"evidence": result["evidence"], "recorded_at": result["recorded_at"],
                   "basis": "recorded_pass_not_current_acceptance", **identity}
    return {"state": "excluded", "evidence": None, "scope_decision": decision, "historical_pass": history}


def _node(root, config, node, local, reviews, identity, plan):
    criteria = []
    for criterion in node["criteria"]:
        fingerprint = criterion_fingerprint(plan, node["id"], criterion)
        result = (_local_result(root, node["id"], criterion, local, identity, fingerprint) if criterion["layer"] == "local"
                  else _test_result(root, config, node["id"], criterion, reviews, identity, fingerprint))
        result = _apply_scope(result, scope_decision(plan, node["id"], criterion["id"]), identity)
        criteria.append({**_criterion_details(node["id"], criterion), **result})
    states = {item["state"] for item in criteria if item["state"] != "excluded"}
    local_coverage = _coverage([item for item in criteria if item["layer"] == "local"])
    test_coverage = _coverage([item for item in criteria if item["layer"] == "TEST"])
    if not criteria:
        state = "unplanned"
    elif node.get("blocker"):
        state = "blocked"
    elif not states:
        state = "excluded"
    elif "failed" in states:
        state = "failed"
    elif "stale" in states:
        state = "stale"
    elif states == {"passed"} and test_coverage["required"]:
        state = "accepted"
    else:
        state = ("local_validated" if local_coverage["required"]
                 and local_coverage["approved"] == local_coverage["required"] else "pending")
    return {"id": node["id"], "implementation": node.get("implementation", "pending"), "state": state,
            "blocker": node.get("blocker"), "local": local_coverage, "TEST": test_coverage,
            "validation": _coverage(criteria), "criteria": criteria,
            "next_criterion": next((item["id"] for item in criteria if item["state"] not in ("passed", "excluded")), None)}


def _cell(value):
    value = html.escape(str(value if value is not None else "—"), quote=True)
    for token in ("\\", "`", "[", "]"):
        value = value.replace(token, "\\" + token)
    return value.replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def _fraction(value):
    ratio = ("no active criteria" if value["percent"] is None else
             f'{value["approved_count"]}/{value["required_count"]} active criteria · {value["percent"]}% '
             f'(weight {value["approved"]}/{value["required"]})')
    return ratio + f' · {value["excluded_count"]} excluded (weight {value["excluded"]}); {value["inventoried_count"]} inventoried'


def _criterion_table(criteria):
    lines = ["| Node / criterion | Description | Gate / group | Layer / mode / scope | Case / reference | Current state / reason | Current evidence | Latest historical pass (not current acceptance) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for item in criteria:
        history = item.get("historical_pass")
        history_text = (history["evidence"] + " · " + history["recorded_at"] + " · evaluator "
                        + history.get("evaluator_version", "unknown")) if history else None
        reasons = item.get("stale_reasons", []) + item.get("failure_reasons", [])
        if item.get("configuration"):
            reasons.append(item["configuration"] + ": " + item["configuration_reason"])
        if item.get("scope_decision"):
            decision = item["scope_decision"]
            reasons.append(f'scope revision {decision["revision"]}: {decision["reason"]}; authorization: {decision["authorization_ref"]}')
        values = (item["node_id"] + "/" + item["id"], item["description"],
                  " / ".join(item[key] for key in ("gate", "group") if key in item) or None,
                  " / ".join(item[key] for key in ("layer", "mode", "scope")),
                  (item["cases_file"] + "#" if item.get("cases_file") else "native case: ") + item["case_id"],
                  item["state"] + (": " + "; ".join(reasons) if reasons else ""), item.get("evidence"), history_text)
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return lines


def _group_coverage(criteria):
    groups = {}
    for item in criteria:
        for dimension in ("gate", "group"):
            if dimension in item:
                groups.setdefault((dimension, item[dimension]), []).append(item)
    return [{"dimension": dimension, "label": label,
             "nodes": sorted({item["node_id"] for item in items if item["node_id"] != "__agent__"}),
             "node_criteria": _coverage([item for item in items if item["node_id"] != "__agent__"]),
             "agent_acceptance": _coverage([item for item in items if item["node_id"] == "__agent__"])}
            for (dimension, label), items in sorted(groups.items())]


def _diagnostics(criteria):
    issues = [{key: item[key] for key in ("node_id", "id", "case_id", "cases_file", "configuration", "configuration_reason")}
              for item in criteria if item.get("configuration")]
    stale = {}
    for item in criteria:
        for reason in item.get("stale_reasons", []):
            stale[reason] = stale.get(reason, 0) + 1
    return {"configuration_issues": issues, "configuration_valid": not issues,
            "stale_reasons": stale,
            "historical_pass_basis": "Recorded runner passes or accepted reviews; never counted as current acceptance."}


def _write_table(path, report):
    _unlinked(path)
    lines = ["# Node validation coverage", "", "Percentages measure the declared validation criteria, not project effort or publication readiness.",
             "", "| Node | Implementation declared | State | Local | TEST accepted | Validation | Next criterion / blocker |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for node in report["nodes"]:
        values = (node["id"], node["implementation"], node["state"], _fraction(node["local"]),
                  _fraction(node["TEST"]), _fraction(node["validation"]), node["blocker"] or node["next_criterion"])
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    lines.extend(["", "Requirements reference: " + _cell(report["requirements_ref"]),
                  "Current plan SHA-256: " + _cell(report["progress_plan_sha256"]),
                  "Plan schema / scope revision: " + _cell(str(report["plan_version"]) + " / " + str(report["scope_revision"])),
                  "Preserved plan snapshot: " + _cell(report["plan_snapshot"]),
                  "Evaluator: " + _cell(report["evaluator_version"]),
                  "Engine SHA-256: " + _cell(report["engine_sha256"]),
                  "Environment SHA-256: " + _cell(report["environment_sha256"]), "",
                  "Local environment observed: " + _cell(report.get("environment_observed")), "",
                  "Configuration issues: " + str(len(report["diagnostics"]["configuration_issues"])),
                  "Missing or invalid local case mappings stay pending and block that criterion; they do not block unrelated focused experiments.",
                  "", "## Node criterion matrix", "",
                  "Every declared criterion remains inventoried. Active and excluded counts are separate; excluded criteria never earn credit and block publication. Historical passes do not accept this revision.", ""])
    lines.extend(_criterion_table([item for node in report["nodes"] for item in node["criteria"]]))
    lines.extend(["", "## Agent integration acceptance", "",
                  "This denominator is separate from node coverage: " + _cell(_fraction(report["agent_acceptance"]["coverage"])), ""])
    lines.extend(_criterion_table(report["agent_acceptance"]["criteria"]))
    if report["groups"]:
        lines.extend(["", "## Gate and group coverage", "",
                      "Labels annotate the existing criteria. These overlapping views must not be added together.", "",
                      "| Dimension / label | Nodes | Node criteria | Agent integration criteria |",
                      "| --- | --- | --- | --- |"])
        for group in report["groups"]:
            values = (group["dimension"] + "/" + group["label"], ", ".join(group["nodes"]),
                      _fraction(group["node_criteria"]), _fraction(group["agent_acceptance"]))
            lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    lines.extend(["", "Inventory: explicitly declared nodes plus observed nodes; the complete compiled graph was not inspected.",
                  "", "Unplanned observed nodes: " + _cell(", ".join(report["unplanned_observed_nodes"]) or "none"), "",
                  "Agent integration acceptance: " + _cell(_fraction(report["agent_acceptance"]["coverage"])),
                  "Publication policy: " + report["publication_policy"],
                  "Publication ready: " + ("yes" if report["publication_ready"] else "no"), "",
                  "Evidence is local and reviewable; no cloud state or semantic verdict is inferred from execution alone."])
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def report_progress(root):
    root, config = _project(root)
    plan = load_progress_plan(root)
    identity = {"config_sha256": canonical_hash(config), "package_sha256": inspect_package(root)["package_sha256"],
                "progress_plan_sha256": canonical_hash(plan), "evaluator_version": __version__, **execution_identity(root)}
    local = _receipts(root, ".aidp-local/runs", "results")
    reviews = _receipts(root, ".aidp-local/progress/reviews")
    nodes = [_node(root, config, node, local, reviews, identity, plan) for node in plan["nodes"]]
    known = {node["id"] for node in nodes}
    candidate_identity = {key: value for key, value in identity.items() if key != "progress_plan_sha256"}
    observed = {node for row in local if _same_revision(row["value"], candidate_identity)
                for node in _visited_nodes(row["value"])}
    unplanned = sorted(observed - known)
    acceptance = _agent_acceptance(root, config, plan, reviews, identity)
    criteria = [item for node in nodes for item in node["criteria"]] + acceptance["criteria"]
    excluded = [item for item in criteria if item["state"] == "excluded"]
    policy = plan.get("publication_policy", "strict_node_layers_v1")
    if policy == "declared_requirements_v1":
        nodes_ready = all(not node["blocker"]
                          and all(item["state"] == "passed" for item in node["criteria"]) for node in nodes)
    else:
        nodes_ready = all(node["state"] == "accepted" and node["local"]["required"]
                          and node["TEST"]["required"] for node in nodes)
    ready = not excluded and not unplanned and nodes_ready and acceptance["state"] == "accepted"
    report = {"version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(), **identity,
              "requirements_ref": plan["requirements_ref"], "nodes": nodes,
              "agent_acceptance": acceptance, "publication_ready": bool(ready),
              "publication_policy": policy,
              "plan_version": plan["version"], "scope_revision": plan.get("revision"),
              "scope_decisions": plan.get("scope_decisions", []),
              "publication_scope_blocked": bool(excluded),
              "diagnostics": _diagnostics(criteria), "groups": _group_coverage(criteria),
              "overall_validation": _coverage([item for node in nodes for item in node["criteria"]]),
              "unplanned_observed_nodes": unplanned,
              "scope_complete": not unplanned and all(node["criteria"] for node in nodes),
              "inventory_basis": "declared_plus_observed", "graph_inventory_verified": False,
              "native_test_accepted": False,
              "acceptance_basis": "explicit_reviewed_node_criteria_not_overall_agent_acceptance"}
    folder = _path(root, ".aidp-local/progress")
    report["plan_snapshot"] = _snapshot_plan(root, plan)
    private_json(folder / "report.json", redact(report), overwrite=True)
    _write_table(folder / "table.md", redact(report))
    return redact({**report, "artifact": str(folder / "report.json"), "table": str(folder / "table.md")})


def _read_plan_history(root, folder):
    paths = list(folder.glob("*.json")) if folder.exists() else []
    if len(paths) > _MAX_RECEIPTS:
        raise FlowError("Progress plan snapshot limit reached; archive reviewed project history")
    total, snapshots = 0, []
    for path in paths:
        _unlinked(path)
        total += path.stat().st_size
        if total > _MAX_HISTORY_BYTES:
            raise FlowError("Progress plan snapshots exceed 64 MiB")
        snapshot = _read(path)
        if (not isinstance(snapshot, dict) or not isinstance(snapshot.get("plan"), dict)
                or canonical_hash(snapshot["plan"]) != path.stem
                or snapshot.get("progress_plan_sha256") != path.stem):
            raise FlowError("Progress plan snapshot identity is invalid; preserve and investigate the history")
        _validate_plan(root, snapshot["plan"])
        snapshots.append(snapshot)
    return paths, total, snapshots


def _migration_baseline(root, legacy):
    # Migration retains the last reported v1 inventory, not every past sample.
    prior_report = _path(root, ".aidp-local/progress/report.json")
    if prior_report.exists():
        recorded = _read(prior_report)
        if not isinstance(recorded, dict):
            raise FlowError("Prior progress report must be an object")
        previous = next((item for item in legacy if item["progress_plan_sha256"] == recorded.get("progress_plan_sha256")), None)
        if previous is None:
            raise FlowError("Prior progress report does not identify a preserved plan snapshot")
        return previous["plan"]
    if any(_stamp(item.get("recorded_at")) is None for item in legacy):
        raise FlowError("Progress plan snapshot lacks a valid history timestamp")
    return max(legacy, key=lambda item: _stamp(item["recorded_at"]))["plan"]


def _validate_plan_history(root, plan, snapshots):
    legacy, versioned = [], False
    for snapshot in snapshots:
        previous = snapshot["plan"]
        if previous["version"] == 2:
            versioned = True
            validate_transition(plan, previous)
        else:
            legacy.append(snapshot)
    if plan["version"] == 2 and not versioned and legacy:
        validate_transition(plan, _migration_baseline(root, legacy))


def _snapshot_plan(root, plan):
    folder = _path(root, ".aidp-local/progress/plans")
    paths, total, snapshots = _read_plan_history(root, folder)
    _validate_plan_history(root, plan, snapshots)
    digest = canonical_hash(plan)
    target = folder / (digest + ".json")
    if not target.exists():
        snapshot = {"plan": plan, "progress_plan_sha256": digest,
                    "recorded_at": datetime.now(timezone.utc).isoformat()}
        size = len(json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8"))
        if len(paths) >= _MAX_RECEIPTS or size > _MAX_JSON or total + size > _MAX_HISTORY_BYTES:
            raise FlowError("Progress plan snapshot limit reached; archive reviewed project history")
        private_json(target, snapshot)
    return target.relative_to(root).as_posix()


def try_report_progress(root):
    try:
        return {"updated": True, **report_progress(root)}
    except Exception:
        return {"updated": False,
                "error": "Progress table refresh failed; run progress report. Existing execution receipts were preserved."}


def record_test_review(root, node_id, criterion_id, receipt_file, verdict, note):
    root, config = _project(root)
    plan = load_progress_plan(root)
    if verdict not in ("accepted", "rejected"):
        raise FlowError("TEST review verdict must be accepted or rejected")
    _text(note, "semantic review note", 4000)
    matches = [criterion for criterion in _review_criteria(plan, node_id)
               if criterion["id"] == criterion_id and criterion["layer"] == "TEST"]
    if len(matches) != 1:
        raise FlowError("TEST review must select one declared TEST criterion")
    decision = scope_decision(plan, node_id, criterion_id)
    if decision and decision["state"] == "excluded":
        raise FlowError("Excluded criteria cannot be accepted or rejected; record an authorized active scope decision first")
    _snapshot_plan(root, plan)
    package_hash = inspect_package(root)["package_sha256"]
    digest = _native_receipt(root, config, matches[0], receipt_file, package_hash, verdict == "accepted")
    record = {"node_id": node_id, "criterion_id": criterion_id, "verdict": verdict, "note": redact(note),
              "receipt": _path(root, receipt_file).relative_to(root).as_posix(), "receipt_sha256": digest,
              "config_sha256": canonical_hash(config), "package_sha256": package_hash,
              "progress_plan_sha256": canonical_hash(plan), "evaluator_version": __version__, **execution_identity(root),
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    if node_id != "__agent__":
        record["criterion_bindings"] = {node_id: {criterion_id: criterion_fingerprint(plan, node_id, matches[0])}}
    private_json(_path(root, ".aidp-local/progress/reviews/" + uuid4().hex + ".json"), record)
    return report_progress(root)


def _review_criteria(plan, node_id):
    if node_id == "__agent__":
        return plan.get("acceptance", [])
    return next((node["criteria"] for node in plan["nodes"] if node["id"] == node_id), [])


def _agent_acceptance(root, config, plan, reviews, identity):
    criteria = [{**_criterion_details("__agent__", criterion),
                 **_apply_scope(_test_result(root, config, "__agent__", criterion, reviews, identity),
                                scope_decision(plan, "__agent__", criterion["id"]), identity)}
                for criterion in plan.get("acceptance", [])]
    states = {criterion["state"] for criterion in criteria if criterion["state"] != "excluded"}
    state = ("accepted" if states == {"passed"} else "failed" if "failed" in states
             else "stale" if "stale" in states else "pending" if states else "excluded" if criteria else "unplanned")
    return {"state": state, "criteria": criteria, "coverage": _coverage(criteria)}


def require_publication_acceptance(root, deployment_snapshot):
    root, config = _project(root)
    if (root / "test-campaign.json").exists():
        from .campaign import require_campaign_clear
        require_campaign_clear(root)
    plan = load_progress_plan(root)
    report = report_progress(root)
    if not report["publication_ready"]:
        raise FlowError("Publication requires current local/node TEST criteria, agent integration acceptance and no blockers or exclusions")
    package_hash = inspect_package(root)["package_sha256"]
    targets = [(node["id"], node["criteria"]) for node in report["nodes"]]
    targets.append(("__agent__", report["agent_acceptance"]["criteria"]))
    for node_id, criteria in targets:
        for criterion in criteria:
            declared = next(item for item in _review_criteria(plan, node_id) if item["id"] == criterion["id"])
            if declared["layer"] != "TEST":
                continue
            review = _read(_path(root, criterion["evidence"]))
            _native_receipt(root, config, declared, review["receipt"], package_hash, True,
                            expected_snapshot=deployment_snapshot)
    return {"publication_ready": True, "evaluator_version": __version__, "package_sha256": package_hash}
