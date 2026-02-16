"""
Decision Trace Analytics - Dashboard queries and aggregation functions.

Provides:
- Summary stats by kind/mode
- Engine usage breakdown
- Tool approval stats
- Policy hit rates
- Time-series trends
"""

from typing import Any, Optional
import logging

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


def get_summary_stats() -> dict[str, Any]:
    """Get overall decision trace summary."""
    driver = _get_neo4j_driver()
    if not driver:
        return {}

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace)
                RETURN 
                    count(d) as total,
                    count(DISTINCT d.session_id) as sessions,
                    min(d.ts) as first_ts,
                    max(d.ts) as last_ts
            """)
            rec = result.single()
            if rec:
                return {
                    "total_decisions": rec["total"],
                    "unique_sessions": rec["sessions"],
                    "first_decision": rec["first_ts"],
                    "last_decision": rec["last_ts"],
                }
    except Exception as e:
        logger.warning(f"Failed to get summary stats: {e}")
    return {}


def get_engine_usage_breakdown() -> list[dict[str, Any]]:
    """Get engine selection breakdown by engine name."""
    driver = _get_neo4j_driver()
    if not driver:
        return []

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'engine_selection'})
                RETURN 
                    d.engine as engine,
                    d.mode as mode,
                    count(*) as count
                ORDER BY count DESC
            """)
            return [
                {
                    "engine": r["engine"],
                    "mode": r["mode"],
                    "count": r["count"],
                }
                for r in result
            ]
    except Exception as e:
        logger.warning(f"Failed to get engine breakdown: {e}")
    return []


def get_tool_approval_stats() -> dict[str, Any]:
    """Get tool approval decision breakdown."""
    driver = _get_neo4j_driver()
    if not driver:
        return {}

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'tool_approval'})
                RETURN 
                    d.mode as decision,
                    count(*) as count
                ORDER BY count DESC
            """)
            decisions = {r["decision"]: r["count"] for r in result}

            # Get most blocked tools
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'tool_approval', mode: 'REQUIRES_HUMAN'})
                RETURN d.tool as tool, count(*) as count
                ORDER BY count DESC
                LIMIT 5
            """)
            blocked_tools = [{"tool": r["tool"], "count": r["count"]} for r in result]

            return {
                "decisions": decisions,
                "most_blocked_tools": blocked_tools,
            }
    except Exception as e:
        logger.warning(f"Failed to get tool approval stats: {e}")
    return {}


def get_routing_breakdown() -> list[dict[str, Any]]:
    """Get network routing breakdown by interface kind."""
    driver = _get_neo4j_driver()
    if not driver:
        return []

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'routing'})
                RETURN 
                    d.mode as interface_kind,
                    count(*) as count
                ORDER BY count DESC
            """)
            return [
                {
                    "interface": r["interface_kind"],
                    "count": r["count"],
                }
                for r in result
            ]
    except Exception as e:
        logger.warning(f"Failed to get routing breakdown: {e}")
    return []


def get_policy_eval_stats() -> dict[str, Any]:
    """Get policy evaluation stats."""
    driver = _get_neo4j_driver()
    if not driver:
        return {}

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'policy_eval'})
                RETURN 
                    d.mode as decision,
                    count(*) as count
                ORDER BY count DESC
            """)
            decisions = {r["decision"]: r["count"] for r in result}

            # Get most hit policies
            result = session.run("""
                MATCH (d:DecisionTrace {kind: 'policy_eval'})
                UNWIND d.policies as policy
                RETURN policy, count(*) as count
                ORDER BY count DESC
                LIMIT 10
            """)
            policy_hits = [{"policy": r["policy"], "count": r["count"]} for r in result]

            return {
                "decisions": decisions,
                "top_policy_hits": policy_hits,
            }
    except Exception as e:
        logger.warning(f"Failed to get policy stats: {e}")
    return {}


def get_session_trace(session_id: str) -> list[dict[str, Any]]:
    """Get all traces for a specific session."""
    driver = _get_neo4j_driver()
    if not driver:
        return []

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (d:DecisionTrace {session_id: $session_id})
                RETURN d
                ORDER BY d.ts ASC
            """,
                session_id=session_id,
            )
            return [dict(r["d"]) for r in result]
    except Exception as e:
        logger.warning(f"Failed to get session trace: {e}")
    return []


def get_intent_decision_summary() -> list[dict[str, Any]]:
    """Get decision summary grouped by intent."""
    driver = _get_neo4j_driver()
    if not driver:
        return []

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (d:DecisionTrace)
                WHERE d.intent IS NOT NULL
                RETURN 
                    d.intent as intent,
                    count(*) as total_decisions,
                    count(DISTINCT d.kind) as decision_types,
                    collect(DISTINCT d.kind) as kinds
                ORDER BY total_decisions DESC
            """)
            return [
                {
                    "intent": r["intent"],
                    "total_decisions": r["total_decisions"],
                    "decision_types": r["decision_types"],
                    "kinds": r["kinds"],
                }
                for r in result
            ]
    except Exception as e:
        logger.warning(f"Failed to get intent summary: {e}")
    return []


def print_dashboard():
    """Print a formatted dashboard to console."""
    print("\n" + "=" * 60)
    print("DENIS DECISION TRACE DASHBOARD")
    print("=" * 60)

    # Summary
    summary = get_summary_stats()
    print(f"\n📊 Summary:")
    print(f"   Total decisions: {summary.get('total_decisions', 0)}")
    print(f"   Unique sessions: {summary.get('unique_sessions', 0)}")

    # Engine usage
    print(f"\n🔧 Engine Selection:")
    engine_usage = get_engine_usage_breakdown()
    for e in engine_usage[:5]:
        print(f"   {e['engine']} ({e['mode']}): {e['count']} times")

    # Tool approval
    print(f"\n🛡️ Tool Approval:")
    approval = get_tool_approval_stats()
    for decision, count in approval.get("decisions", {}).items():
        print(f"   {decision}: {count}")
    print("   Most blocked:")
    for t in approval.get("most_blocked_tools", [])[:3]:
        print(f"      - {t['tool']}: {t['count']}")

    # Routing
    print(f"\n🌐 Network Routing:")
    routing = get_routing_breakdown()
    for r in routing[:5]:
        print(f"   {r['interface']}: {r['count']} times")

    # Policy eval
    print(f"\n📋 Policy Evaluation:")
    policy = get_policy_eval_stats()
    for decision, count in policy.get("decisions", {}).items():
        print(f"   {decision}: {count}")
    print("   Top policy hits:")
    for p in policy.get("top_policy_hits", [])[:5]:
        print(f"      - {p['policy']}: {p['count']}")

    # Intent summary
    print(f"\n🎯 Intent Breakdown:")
    intents = get_intent_decision_summary()
    for i in intents[:5]:
        print(
            f"   {i['intent']}: {i['total_decisions']} decisions ({', '.join(i['kinds'])})"
        )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    print_dashboard()
