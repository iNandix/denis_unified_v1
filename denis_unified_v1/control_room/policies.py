"""Control Room approval policies.

dangerous_ops_v1: deploy, rollback, canary require approval
safe_ops_v1: ops_query, gc, backfill, reindex, drill run without approval
"""

from __future__ import annotations


DANGEROUS_TASK_TYPES: set[str] = {"deploy", "rollback", "canary"}
SAFE_TASK_TYPES: set[str] = {"ops_query", "gc", "backfill", "reindex", "drill", "scrape"}


def requires_approval(task_type: str) -> bool:
    """Return True if the task type requires human approval before execution.

    Dangerous ops always require approval. Safe ops never do.
    Unknown types default to requiring approval (fail-closed for safety).
    """
    t = (task_type or "").strip().lower()
    if t in DANGEROUS_TASK_TYPES:
        return True
    if t in SAFE_TASK_TYPES:
        return False
    # Unknown types: fail-closed (require approval for safety)
    return True


def get_policy_id(task_type: str) -> str:
    """Return the policy ID governing this task type."""
    t = (task_type or "").strip().lower()
    if t in DANGEROUS_TASK_TYPES:
        return "dangerous_ops_v1"
    if t in SAFE_TASK_TYPES:
        return "safe_ops_v1"
    # Unknown types fall under dangerous policy
    return "dangerous_ops_v1"
