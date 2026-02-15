"""P1.3 Settings - Timeouts and budgets from environment.

Centralized settings for cognition, retrieval, and execution timeouts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CognitionSettings:
    """Cognition/retrieval budgets (ms)."""

    total_ms: int = 650
    retrieval_parallel_budget_ms: int = 260
    neo4j_query_ms: int = 140
    human_memory_query_ms: int = 180
    metagraph_route_ms: int = 220
    redis_context_ms: int = 60
    fs_probe_ms: int = 120


@dataclass
class DirectLocalSettings:
    """direct_local realization budgets (ms)."""

    total_ms: int = 2200
    local_llm_total_ms: int = 1700
    local_llm_fallback_ms: int = 900
    local_llm_max_tokens: int = 280


@dataclass
class ActionSettings:
    """Actions/multi-plan execution settings."""

    tool_step_soft_timeout_ms: int = 5000
    tool_step_hard_timeout_ms: int = 20000
    plan_max_steps: int = 6


@dataclass
class RouterSettings:
    """Router defaults."""

    default_timeout_sec: float = 4.5
    max_attempts: int = 3


class Settings:
    """Centralized settings loader."""

    def __init__(self):
        # Cognition
        self.cognition = CognitionSettings(
            total_ms=int(os.getenv("DENIS_COGNITION_TOTAL_MS", "650")),
            retrieval_parallel_budget_ms=int(
                os.getenv("DENIS_RETRIEVAL_PARALLEL_BUDGET_MS", "260")
            ),
            neo4j_query_ms=int(os.getenv("DENIS_NEO4J_QUERY_TIMEOUT_MS", "140")),
            human_memory_query_ms=int(
                os.getenv("DENIS_HUMAN_MEMORY_TIMEOUT_MS", "180")
            ),
            metagraph_route_ms=int(os.getenv("DENIS_METAGRAPH_TIMEOUT_MS", "220")),
            redis_context_ms=int(os.getenv("DENIS_REDIS_CONTEXT_TIMEOUT_MS", "60")),
            fs_probe_ms=int(os.getenv("DENIS_FS_PROBE_TIMEOUT_MS", "120")),
        )

        # Direct local
        self.direct_local = DirectLocalSettings(
            total_ms=int(os.getenv("DENIS_DIRECT_LOCAL_TOTAL_MS", "2200")),
            local_llm_total_ms=int(os.getenv("DENIS_LOCAL_LLM_TOTAL_MS", "1700")),
            local_llm_fallback_ms=int(os.getenv("DENIS_LOCAL_LLM_FALLBACK_MS", "900")),
            local_llm_max_tokens=int(os.getenv("DENIS_LOCAL_LLM_MAX_TOKENS", "280")),
        )

        # Actions
        self.actions = ActionSettings(
            tool_step_soft_timeout_ms=int(
                os.getenv("DENIS_TOOL_STEP_SOFT_TIMEOUT_MS", "5000")
            ),
            tool_step_hard_timeout_ms=int(
                os.getenv("DENIS_TOOL_STEP_HARD_TIMEOUT_MS", "20000")
            ),
            plan_max_steps=int(os.getenv("DENIS_PLAN_MAX_STEPS", "6")),
        )

        # Router
        self.router = RouterSettings(
            default_timeout_sec=float(
                os.getenv("DENIS_ROUTER_DEFAULT_TIMEOUT_SEC", "4.5")
            ),
            max_attempts=int(os.getenv("DENIS_ROUTER_MAX_ATTEMPTS", "3")),
        )

    def remaining_ms(self, start_ms: int, budget_total_ms: int) -> int:
        """Calculate remaining budget. Budget remaining = max(0, total - elapsed)."""
        from datetime import datetime, timezone

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return max(0, budget_total_ms - (now_ms - start_ms))

    def is_budget_exhausted(self, start_ms: int, budget_total_ms: int) -> bool:
        """Check if budget is exhausted."""
        return self.remaining_ms(start_ms, budget_total_ms) == 0


# Global singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
