"""Task planner: maps task type to a list of Step definitions.

Each task type has a known plan of steps. Unknown types get a single generic step.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepDef:
    """Definition of a single step in a task execution plan."""

    name: str
    tool: str | None = None
    requires_approval: bool = False
    order: int = 1


# Pre-defined plans per task type.
_PLANS: dict[str, list[StepDef]] = {
    "ops_query": [
        StepDef(name="query_graph", tool="neo4j.read", order=1),
    ],
    "reindex": [
        StepDef(name="clear_stale", tool="qdrant.delete", order=1),
        StepDef(name="reindex_all", tool="indexing.upsert", order=2),
    ],
    "deploy": [
        StepDef(name="validate", tool="preflight.check", order=1),
        StepDef(name="deploy_artifact", tool="deploy.push", requires_approval=True, order=2),
    ],
    "rollback": [
        StepDef(name="validate_rollback", tool="preflight.check", order=1),
        StepDef(name="rollback_artifact", tool="deploy.rollback", requires_approval=True, order=2),
    ],
    "canary": [
        StepDef(name="validate_canary", tool="preflight.check", order=1),
        StepDef(name="deploy_canary", tool="deploy.canary", requires_approval=True, order=2),
        StepDef(name="monitor_canary", tool="monitor.canary", order=3),
    ],
    "gc": [
        StepDef(name="identify_stale", tool="neo4j.read", order=1),
        StepDef(name="delete_stale", tool="neo4j.write", order=2),
    ],
    "backfill": [
        StepDef(name="scan_missing", tool="neo4j.read", order=1),
        StepDef(name="backfill_data", tool="indexing.upsert", order=2),
    ],
    "drill": [
        StepDef(name="run_drill", tool="drill.execute", order=1),
    ],
    "scrape": [
        StepDef(name="fetch_content", tool="scraper.fetch", order=1),
        StepDef(name="index_content", tool="indexing.upsert", order=2),
    ],
}


def plan_steps(task_type: str) -> list[StepDef]:
    """Return the step definitions for the given task type.

    Unknown types get a single generic 'execute' step.
    """
    t = (task_type or "").strip().lower()
    if t in _PLANS:
        return list(_PLANS[t])  # shallow copy to avoid mutation
    # Default for unknown types
    return [StepDef(name="execute", tool=None, order=1)]
