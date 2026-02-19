#!/usr/bin/env python3
"""
CPGenerator - Generates ContextPacks from agent results or manual input.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from control_plane.models import ContextPack
from control_plane.repo_context import RepoContext

logger = logging.getLogger(__name__)


class CPGenerator:
    """Generates ContextPacks for Denis Control Plane."""

    INTENT_NEXT_MAP = {
        "implement_feature": "run_tests_ci",
        "debug_repo": "explain_concept",
        "refactor_migration": "run_tests_ci",
        "run_tests_ci": "implement_feature",
        "explain_concept": "write_docs",
        "write_docs": "implement_feature",
        "design_architecture": "implement_feature",
        "toolchain_task": "run_tests_ci",
    }

    def __init__(self):
        self._quota_registry = None
        self._symbol_graph = None

    def _get_quota_registry(self):
        """Lazy load quota registry."""
        if self._quota_registry is None:
            try:
                from denis_unified_v1.inference.quota_registry import get_quota_registry

                self._quota_registry = get_quota_registry()
            except ImportError:
                pass
        return self._quota_registry

    def _get_symbol_graph(self):
        """Lazy load symbol graph."""
        if self._symbol_graph is None:
            try:
                from denis_unified_v1.kernel.ghost_ide.symbol_graph import (
                    get_symbol_graph,
                )

                self._symbol_graph = get_symbol_graph()
            except ImportError:
                pass
        return self._symbol_graph

    def _predict_next_intent(self, result: dict) -> str:
        """Infiere siguiente intent lógico."""
        current = result.get("intent", "unknown")
        return self.INTENT_NEXT_MAP.get(current, "implement_feature")

    def _get_related_files(self, files_touched: List[str], repo_id: str) -> List[str]:
        """Neo4j filtrado por repo_id."""
        graph = self._get_symbol_graph()
        if not graph:
            return files_touched[:3]

        try:
            recent = graph.get_repo_recent_symbols(repo_id, days=7)
            related = [r["path"] for r in recent if r.get("path")]
            return list(set(files_touched + related))[:10]
        except Exception as e:
            logger.warning(f"Could not get related files: {e}")
            return files_touched[:3]

    def _build_mission(self, result: dict, next_intent: str) -> str:
        """Síntesis legible."""
        intent = result.get("intent", "unknown")
        mission = result.get("mission", "Tarea completada")

        if next_intent:
            return f"{mission}\n\nSiguiente paso sugerido: {next_intent}"
        return mission

    def from_agent_result(self, result: dict) -> ContextPack:
        """
        Lee repo_id, intent, files_touched, constraints.
        Enriquece con grafo.
        """
        repo_ctx = RepoContext(cwd=result.get("cwd"))

        timestamp = datetime.now(timezone.utc).isoformat()
        cp_id = hashlib.sha256(f"{timestamp}_{repo_ctx.repo_id}".encode()).hexdigest()[:8]

        intent = result.get("intent", "unknown")
        constraints = result.get("constraints", [])
        files_touched = result.get("files_touched", [])
        related_files = self._get_related_files(files_touched, repo_ctx.repo_id)

        next_intent = self._predict_next_intent(result)
        mission = self._build_mission(result, next_intent)

        qr = self._get_quota_registry()
        model = qr.get_best_model_for(intent) if qr else "groq"

        risk_level = self._infer_risk_level(
            intent, files_touched, result.get("is_checkpoint", False)
        )

        return ContextPack(
            cp_id=cp_id,
            mission=mission,
            model=model,
            files_to_read=related_files,
            files_touched=files_touched,
            success=result.get("success", False),
            risk_level=risk_level,
            is_checkpoint=result.get("is_checkpoint", False),
            do_not_touch=["kernel/__init__.py", "public/"],
            implicit_tasks=result.get("implicit_tasks", []),
            acceptance_criteria=result.get("acceptance_criteria", []),
            intent=intent,
            constraints=constraints,
            repo_id=repo_ctx.repo_id,
            repo_name=repo_ctx.repo_name,
            branch=repo_ctx.branch,
        )

    def _infer_risk_level(self, intent: str, files_touched: List[str], is_checkpoint: bool) -> str:
        """Infer risk level based on intent and files touched."""
        if is_checkpoint:
            return "HIGH"
        if intent in ["add_test", "add_doc", "fix_typo", "refactor_readme"]:
            return "LOW"
        if any(f in str(files_touched) for f in ["inference/", "kernel/", "sandbox/"]):
            return "CRITICAL"
        if any(f in str(files_touched) for f in ["compiler/", "persona/", "graph/"]):
            return "HIGH"
        return "MEDIUM"

    def from_manual(self, mission: str, cwd: str = None) -> ContextPack:
        """Para CPs manuales — enriquece con RepoContext(cwd)."""
        repo_ctx = RepoContext(cwd=cwd)

        timestamp = datetime.now(timezone.utc).isoformat()
        cp_id = hashlib.sha256(f"{timestamp}_{repo_ctx.repo_id}_manual".encode()).hexdigest()[:8]

        return ContextPack(
            cp_id=cp_id,
            mission=mission,
            model="groq",
            repo_id=repo_ctx.repo_id,
            repo_name=repo_ctx.repo_name,
            branch=repo_ctx.branch,
            source="manual",
        )


__all__ = ["CPGenerator", "ContextPack"]
