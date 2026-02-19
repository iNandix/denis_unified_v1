"""Implicit Tasks — Hygiene tasks inferred from intent."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

IMPLICIT_TASKS_BY_INTENT = {
    "implement_feature": [
        "READ target files before writing",
        "VERIFY all imports resolve after creation",
        "RUN existing tests before commit",
        "CHECK DO_NOT_TOUCH list",
    ],
    "debug_repo": [
        "READ error + stack trace first",
        "CHECK git diff last 5 commits",
        "VERIFY fix does not break existing tests",
    ],
    "refactor_migration": [
        "SNAPSHOT current behavior via tests",
        "VERIFY identical behavior post-refactor",
        "CHECK no new imports needed",
    ],
    "run_tests_ci": [
        "VERIFY test environment active",
        "CHECK all services needed are running",
    ],
    "toolchain_task": [
        "VERIFY tool/command exists in PATH",
        "CHECK service dependencies are up",
    ],
    "design_architecture": [
        "ANALYZE existing system components",
        "VERIFY constraints and requirements",
        "CHECK existing patterns in codebase",
    ],
    "write_docs": [
        "READ existing documentation",
        "VERIFY examples are working",
        "CHECK documentation format consistency",
    ],
}


@dataclass
class EnrichedContext:
    """Enriched context from session graph."""

    implicit_tasks: List[str] = field(default_factory=list)
    do_not_touch_auto: List[str] = field(default_factory=list)
    context_prefilled: Dict[str, Any] = field(default_factory=dict)


class ImplicitTasks:
    """Manager for implicit hygiene tasks."""

    def __init__(self):
        self._neo4j_driver = None

    def get_implicit_tasks(self, intent: str) -> List[str]:
        """Get implicit tasks for an intent."""
        return IMPLICIT_TASKS_BY_INTENT.get(intent, [])

    def _get_neo4j_driver(self):
        """Get Neo4j driver if available."""
        if self._neo4j_driver is None:
            try:
                from neo4j import GraphDatabase

                self._neo4j_driver = GraphDatabase.driver(
                    "bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$")
                )
            except Exception as e:
                logger.warning(f"Neo4j not available: {e}")
        return self._neo4j_driver

    def enrich_with_session(self, intent: str, session_id: str = None) -> EnrichedContext:
        """Enrich implicit tasks with session graph data and RedundancyDetector."""
        try:
            from control_plane.repo_context import read_session_id

            session_id = read_session_id() or session_id or "default"
        except Exception:
            session_id = session_id or "default"

        context = EnrichedContext(implicit_tasks=self.get_implicit_tasks(intent))

        try:
            from kernel.ghostide.contextharvester import ContextHarvester

            harvester = ContextHarvester(session_id=session_id, watch_paths=[])
            session_ctx = harvester.get_session_context()

            context.do_not_touch_auto = session_ctx.get("do_not_touch_auto", [])
            context.context_prefilled = session_ctx.get("context_prefilled", {})

            auto_injected = self._get_auto_injected_tasks(session_id, intent)
            context.implicit_tasks = self._merge_tasks(context.implicit_tasks, auto_injected)

        except Exception as e:
            logger.warning(f"ContextHarvester failed: {e}, using static tasks only")

        return context

    def _get_auto_injected_tasks(self, session_id: str, intent: str) -> List[str]:
        """Get auto-injected tasks from learned patterns in graph."""
        try:
            from kernel.ghostide.symbolgraph import (
                get_auto_inject_tasks,
                get_session_symbols,
                link_symbol_to_intent,
            )

            learned_tasks = get_auto_inject_tasks(intent)
            if learned_tasks:
                return learned_tasks

            symbols = get_session_symbols(session_id)
            return [f"CONSULT symbol: {s['name']}" for s in symbols[:3]]
        except Exception as e:
            logger.debug(f"Auto-inject not available: {e}")
            return []

    def _record_execution(self, intent: str, tasks: List[str], session_id: str) -> None:
        """Record execution for learning."""
        try:
            from kernel.ghost_ide.symbol_graph import record_execution

            record_execution(intent, [], tasks, session_id)
        except Exception:
            pass

    def _merge_tasks(self, static_tasks: List[str], auto_tasks: List[str]) -> List[str]:
        """Merge static and auto tasks without duplicates, preserving order."""
        seen = set()
        result = []
        for task in auto_tasks + static_tasks:
            if task not in seen:
                seen.add(task)
                result.append(task)
        return result

    def build_prefilled_cp_additions(self, intent: str, session_id: str) -> Dict[str, Any]:
        """Build context additions for the system prompt."""
        context = self.enrich_with_session(intent, session_id)
        return {
            "implicit_tasks": context.implicit_tasks,
            "do_not_touch_auto": context.do_not_touch_auto,
            "context_prefilled": context.context_prefilled,
        }


_implicit_tasks: Optional[ImplicitTasks] = None


def get_implicit_tasks() -> ImplicitTasks:
    """Get singleton ImplicitTasks."""
    global _implicit_tasks
    if _implicit_tasks is None:
        _implicit_tasks = ImplicitTasks()
    return _implicit_tasks


__all__ = [
    "ImplicitTasks",
    "EnrichedContext",
    "IMPLICIT_TASKS_BY_INTENT",
    "get_implicit_tasks",
]
