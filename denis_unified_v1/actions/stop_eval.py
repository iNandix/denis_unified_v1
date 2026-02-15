from __future__ import annotations

from typing import Any, Dict
from denis_unified_v1.actions.models import StopCondition, StopOp


def eval_stop_condition(cond: StopCondition, facts: Dict[str, Any]) -> bool:
    key = cond.key
    op = cond.op
    val = cond.value

    exists = key in facts

    if op == StopOp.exists:
        return exists
    if op == StopOp.not_exists:
        return not exists

    if not exists:
        return False

    fv = facts.get(key)

    if op == StopOp.is_true:
        return bool(fv) is True
    if op == StopOp.is_false:
        return bool(fv) is False

    # numeric/string comparisons
    if op == StopOp.eq:
        return fv == val
    if op == StopOp.ne:
        return fv != val
    if op == StopOp.gt:
        return fv > val
    if op == StopOp.gte:
        return fv >= val
    if op == StopOp.lt:
        return fv < val
    if op == StopOp.lte:
        return fv <= val

    if op == StopOp.contains:
        try:
            return val in fv
        except TypeError:
            return False

    if op == StopOp.not_contains:
        try:
            return val not in fv
        except TypeError:
            return False

    return False
