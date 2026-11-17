"""Advisory admission forecast; never reserve calls or execute agent code."""
from decimal import Decimal

from .campaign import _check_admission, _money, _records, _totals, load_policy, validate_reservation_identity
from .project import FlowError


def preview_capacity(root, candidates, *, real=False, model_calls=0, repeat_reason=None):
    policy = load_policy(root)
    rows = _records(root)
    initial = _totals(rows)
    kind = "real" if real else "fixture"
    ceiling = _money(policy[kind + "_cost_ceiling_usd"], "cost ceiling") if real else Decimal(0)
    budget = _money(policy["budget_usd"], "budget")
    planned, blocked = [], None
    for candidate in candidates:
        try:
            validate_reservation_identity(candidate["case_id"], candidate["experiment_sha256"], kind, model_calls)
            if real and (not model_calls or budget is not None and ceiling is None):
                raise FlowError("Paid experiments need call and cost ceilings for a finite budget")
            _check_admission(policy, rows, kind, model_calls, ceiling, budget,
                             candidate["experiment_sha256"], repeat_reason)
        except FlowError as error:
            blocked = str(error)
            break
        planned.append(candidate["case_id"])
        # Assume each preceding case finishes at its full reserved ceiling. This
        # forecasts capacity, not success or the result of future reconciliation.
        rows.append({"id": f"{len(rows) + 1:032x}", **candidate, "kind": kind,
                     "state": "COMPLETED", "reserved_model_calls": model_calls,
                     "model_calls": model_calls, "reserved_cost_usd": str(ceiling) if ceiling is not None else None,
                     "cost_usd": str(ceiling) if ceiling is not None else None, "history": []})
    return {"advisory": True, "reservation_created": False, "agent_invoked": False,
            "billing_verified": False, "current": initial,
            "fits_at_reserved_ceilings": planned, "blocked_reason": blocked,
            "not_planned": [item["case_id"] for item in candidates[len(planned):]],
            "assumption": "Preceding cases finish; admission is rechecked under lock at execution"}
