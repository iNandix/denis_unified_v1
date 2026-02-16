"""
Denis Code CLI Integration - Decision tracing for CLI agent sessions.

This module provides easy integration for Denis Code CLI to emit traces
during agentic coding sessions.

Usage:
    from denis_unified_v1.actions.cli_trace import cli_trace_engine, cli_trace_tool

    # At start of session
    cli_trace_session_start()

    # Before each LLM call
    engine = cli_trace_engine(intent="code_edit", task_heavy=True)

    # After each tool execution
    cli_trace_tool("write_file", approved=True)

    # At end of session
    cli_trace_session_end()
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from denis_unified_v1.actions.decision_trace import (
    emit_decision_trace,
    trace_engine_selection,
    trace_tool_approval,
    trace_plan_selection,
    trace_routing,
    trace_research,
)
from denis_unified_v1.actions.engine_registry import select_engine_for_intent

logger = logging.getLogger(__name__)

# CLI session context
_cli_session_id: Optional[str] = None
_cli_turn_count: int = 0


def cli_session_id() -> str:
    """Get or create CLI session ID."""
    global _cli_session_id
    if _cli_session_id is None:
        _cli_session_id = os.getenv("DENIS_SESSION_ID") or str(uuid.uuid4())
    return _cli_session_id


def cli_trace_session_start(session_id: Optional[str] = None) -> str:
    """
    Initialize a CLI session for tracing.

    Returns the session_id.
    """
    global _cli_session_id, _cli_turn_count

    if session_id:
        _cli_session_id = session_id
    else:
        _cli_session_id = os.getenv("DENIS_SESSION_ID") or str(uuid.uuid4())

    _cli_turn_count = 0

    logger.info(f"CLI session started: {_cli_session_id}")
    return _cli_session_id


def cli_trace_engine(
    intent: str,
    task_heavy: bool = False,
    force_booster: bool = False,
) -> Optional[str]:
    """
    Trace engine selection for CLI task.

    Returns engine name if selected, None otherwise.
    """
    global _cli_turn_count
    _cli_turn_count += 1

    try:
        engine = select_engine_for_intent(
            intent=intent,
            task_heavy=task_heavy,
            force_booster=force_booster,
        )

        if engine:
            logger.debug(f"CLI engine selected: {engine.name} for {intent}")
            return engine.name

        # Fallback trace if engine selection failed
        trace_engine_selection(
            intent=intent,
            engine="none",
            mode="FALLBACK",
            reason="engine_selection_failed",
            local_ok=False,
            session_id=cli_session_id(),
            turn_id=f"turn_{_cli_turn_count}",
        )
    except Exception as e:
        logger.warning(f"CLI engine trace failed: {e}")

    return None


def cli_trace_tool(
    tool_name: str,
    approved: bool,
    risk_level: Optional[str] = None,
    intent: Optional[str] = None,
) -> None:
    """
    Trace tool execution approval result.
    """
    global _cli_turn_count

    try:
        decision = "APPROVED" if approved else "REQUIRES_HUMAN"
        reason = f"cli_{'approved' if approved else 'blocked'}"

        trace_tool_approval(
            tool=tool_name,
            decision=decision,
            reason=reason,
            risk_level=risk_level,
            intent=intent,
            session_id=cli_session_id(),
            turn_id=f"turn_{_cli_turn_count}",
        )

        logger.debug(f"CLI tool traced: {tool_name} -> {decision}")
    except Exception as e:
        logger.warning(f"CLI tool trace failed: {e}")


def cli_trace_plan(
    intent: str,
    candidate_id: str,
    mode: str = "SELECTED",
) -> None:
    """
    Trace plan selection for CLI task.
    """
    global _cli_turn_count

    try:
        trace_plan_selection(
            intent=intent,
            candidate_id=candidate_id,
            mode=mode,
            reason="cli_session",
            session_id=cli_session_id(),
            turn_id=f"turn_{_cli_turn_count}",
        )

        logger.debug(f"CLI plan traced: {intent} -> {candidate_id}")
    except Exception as e:
        logger.warning(f"CLI plan trace failed: {e}")


def cli_trace_research(
    query: str,
    mode: str = "DEEP",
    sources_count: int = 0,
    citations: Optional[list[str]] = None,
) -> None:
    """
    Trace research activity during CLI session.
    """
    global _cli_turn_count

    try:
        trace_research(
            mode=mode,
            query=query,
            sources_count=sources_count,
            reason="cli_research",
            citations=citations,
            session_id=cli_session_id(),
            turn_id=f"turn_{_cli_turn_count}",
        )

        logger.debug(f"CLI research traced: {query} ({sources_count} sources)")
    except Exception as e:
        logger.warning(f"CLI research trace failed: {e}")


def cli_trace_routing(
    interface_kind: str,
    service_name: str,
    endpoint: str,
    intent: Optional[str] = None,
) -> None:
    """
    Trace network routing decision.
    """
    global _cli_turn_count

    try:
        trace_routing(
            interface_kind=interface_kind,
            service_name=service_name,
            endpoint=endpoint,
            reason="cli_routing",
            intent=intent,
            session_id=cli_session_id(),
            turn_id=f"turn_{_cli_turn_count}",
        )

        logger.debug(f"CLI routing traced: {interface_kind} -> {endpoint}")
    except Exception as e:
        logger.warning(f"CLI routing trace failed: {e}")


def cli_trace_session_end() -> dict:
    """
    End CLI session and return summary.

    Returns session summary dict.
    """
    global _cli_session_id, _cli_turn_count

    summary = {
        "session_id": _cli_session_id,
        "total_turns": _cli_turn_count,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"CLI session ended: {summary}")

    _cli_session_id = None
    _cli_turn_count = 0

    return summary


# Convenience function for quick CLI integration
def quick_trace(
    kind: str,
    **kwargs,
) -> Optional[str]:
    """
    Quick trace function for CLI integration.

    Automatically handles session context.
    """
    global _cli_session_id, _cli_turn_count

    if _cli_session_id is None:
        cli_trace_session_start()

    _cli_turn_count += 1

    try:
        if kind == "engine":
            return cli_trace_engine(
                intent=kwargs.get("intent", "cli_task"),
                task_heavy=kwargs.get("task_heavy", False),
                force_booster=kwargs.get("force_booster", False),
            )
        elif kind == "tool":
            cli_trace_tool(
                tool_name=kwargs.get("tool_name", "unknown"),
                approved=kwargs.get("approved", True),
                risk_level=kwargs.get("risk_level"),
                intent=kwargs.get("intent"),
            )
        elif kind == "plan":
            cli_trace_plan(
                intent=kwargs.get("intent", "cli_task"),
                candidate_id=kwargs.get("candidate_id", "unknown"),
            )
        elif kind == "research":
            cli_trace_research(
                query=kwargs.get("query", ""),
                mode=kwargs.get("mode", "DEEP"),
                sources_count=kwargs.get("sources_count", 0),
            )
    except Exception as e:
        logger.warning(f"Quick trace failed: {e}")

    return None
