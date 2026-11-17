"""Explicit, append-only scope decisions for version 2 progress plans."""
from .project import FlowError


def known_fields(value, fields, label):
    if set(value) - set(fields):
        raise FlowError("Unsupported " + label + " fields; exclusions require a version 2 scope decision")


def validate_scope(plan, text):
    if plan["version"] == 1:
        return
    revision = plan.get("revision")
    if type(revision) is not int or revision < 1:
        raise FlowError("Version 2 progress plans require a positive integer revision")
    decisions = plan.get("scope_decisions")
    if not isinstance(decisions, list) or len(decisions) > 2000:
        raise FlowError("Version 2 scope_decisions must be a list of at most 2000 decisions")
    targets = _inventory(plan)
    seen, previous = set(), 0
    for decision in decisions:
        current, node, criterion = _validate_decision(decision, text)
        if not previous <= current <= revision:
            raise FlowError("Scope decisions require ordered positive revisions no later than the plan revision")
        previous = current
        key = (current, node, criterion)
        if (node, criterion) not in targets or key in seen:
            raise FlowError("Scope decisions must name an existing criterion once per revision")
        seen.add(key)


def _validate_decision(decision, text):
    if not isinstance(decision, dict):
        raise FlowError("Scope decisions must be objects")
    known_fields(decision, ("revision", "node_id", "criterion_id", "state", "reason", "authorization_ref"), "scope decision")
    revision = decision.get("revision")
    if type(revision) is not int or revision < 1:
        raise FlowError("Scope decisions require positive integer revisions")
    if decision.get("state") not in ("active", "excluded"):
        raise FlowError("Scope decision state must be active or excluded")
    text(decision.get("reason"), "scope decision reason", 2000)
    text(decision.get("authorization_ref"), "scope authorization_ref", 500)
    return (revision, text(decision.get("node_id"), "scope node id", 128),
            text(decision.get("criterion_id"), "scope criterion id", 128))


def scope_decision(plan, node_id, criterion_id):
    return next((item for item in reversed(plan.get("scope_decisions", []))
                 if item["node_id"] == node_id and item["criterion_id"] == criterion_id), None)


def _inventory(plan):
    return ({(node["id"], item["id"]) for node in plan["nodes"] for item in node["criteria"]}
            | {("__agent__", item["id"]) for item in plan.get("acceptance", [])})


def validate_transition(plan, previous):
    """Never rewrite or erase an already reported version 2 decision history."""
    if plan["version"] == 2 and not _inventory(previous).issubset(_inventory(plan)):
        raise FlowError("Version 2 inventory must retain prior criterion IDs; exclusions require an authorized scope decision")
    if previous["version"] != 2 or plan == previous:
        return
    if plan["version"] != 2 or plan["revision"] <= previous["revision"]:
        raise FlowError("Changed version 2 plans require a greater revision; prior scope history is preserved")
    history = previous["scope_decisions"]
    if plan["scope_decisions"][:len(history)] != history:
        raise FlowError("Prior scope decisions are immutable; append a new authorized decision")
    if any(item["revision"] <= previous["revision"] for item in plan["scope_decisions"][len(history):]):
        raise FlowError("New scope decisions require a revision after the previous reported plan")
