"""Quota Registry — Track model quotas and availability."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

QUOTA_FILE = "/tmp/denis_quota_registry.json"

MODEL_CONFIG = {
    "claude": {
        "available_env": "ANTHROPIC_API_KEY",
        "best_for": ["architecture", "long_context", "complex_reasoning"],
        "max_tokens": 200000,
        "cost_tier": "HIGH",
        "weekly_reset": True,
    },
    "groq": {
        "available_env": "GROQ_API_KEY",
        "best_for": ["fast_code", "debug_repo", "run_tests_ci", "implement_feature"],
        "max_tokens": 32768,
        "cost_tier": "FREE",
        "rate_limit_rpm": 30,
    },
    "openrouter": {
        "available_env": "OPENROUTER_API_KEY",
        "best_for": ["reasoning", "explain_concept", "design_architecture"],
        "max_tokens": 128000,
        "cost_tier": "MEDIUM",
        "weekly_reset": False,
    },
    "llama_local": {
        "available_env": None,
        "best_for": ["repetitive", "private", "toolchain_task", "ops_health_check"],
        "max_tokens": 8192,
        "cost_tier": "ZERO",
        "endpoint": "http://localhost:8084/inference/local",
    },
}


class QuotaRegistry:
    """Registry for tracking model quotas and availability."""

    def __init__(self):
        self._quotas: Dict[str, Dict[str, Any]] = {}
        self._available_models: List[str] = []
        self._init_availability()
        self._load_from_disk()

    def _init_availability(self):
        """Auto-detect available models based on env vars."""
        self._available_models = []
        for model, config in MODEL_CONFIG.items():
            env_var = config.get("available_env")
            if env_var is None:
                self._available_models.append(model)
            elif os.getenv(env_var):
                self._available_models.append(model)
                logger.info(f"Model {model} detected via {env_var}")

        if "llama_local" not in self._available_models:
            self._available_models.append("llama_local")

    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        return list(self._available_models)

    def mark_quota_exhausted(self, model: str, reset_in_seconds: int):
        """Mark a model as quota-exhausted."""
        if model not in self._quotas:
            self._quotas[model] = {}
        self._quotas[model]["exhausted"] = True
        self._quotas[model]["reset_at"] = datetime.now(timezone.utc).timestamp() + reset_in_seconds
        if model in self._available_models:
            self._available_models.remove(model)
        self._save_to_disk()
        logger.warning(f"Model {model} quota exhausted, reset in {reset_in_seconds}s")

    def is_available(self, model: str) -> bool:
        """Check if a model is available."""
        if model not in self.get_available_models():
            return False

        quota = self._quotas.get(model, {})
        if quota.get("exhausted"):
            reset_at = quota.get("reset_at", 0)
            if datetime.now(timezone.utc).timestamp() > reset_at:
                self._quotas[model] = {}
                if model not in self._available_models:
                    self._available_models.append(model)
                return True
            return False

        return True

    def get_best_model_for(self, intent: str) -> str:
        """Get the best model for a given intent."""
        candidates = []
        for model in self._available_models:
            if not self.is_available(model):
                continue
            config = MODEL_CONFIG.get(model, {})
            best_for = config.get("best_for", [])
            if intent in best_for:
                candidates.append((model, 0))
            else:
                for keyword in best_for:
                    if keyword in intent:
                        candidates.append((model, 1))
                        break

        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]

        if self.is_available("llama_local"):
            return "llama_local"
        if self._available_models:
            return self._available_models[0]
        return "llama_local"

    def _load_from_disk(self):
        """Load quotas from disk."""
        try:
            if Path(QUOTA_FILE).exists():
                with open(QUOTA_FILE, "r") as f:
                    self._quotas = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load quota registry: {e}")

    def _save_to_disk(self):
        """Save quotas to disk."""
        try:
            with open(QUOTA_FILE, "w") as f:
                json.dump(self._quotas, f)
        except Exception as e:
            logger.warning(f"Failed to save quota registry: {e}")


_registry: Optional[QuotaRegistry] = None


def get_quota_registry() -> QuotaRegistry:
    """Get singleton QuotaRegistry."""
    global _registry
    if _registry is None:
        _registry = QuotaRegistry()
    return _registry


__all__ = ["QuotaRegistry", "get_quota_registry", "MODEL_CONFIG"]
