"""
InferenceGateway - Shadow mode for model selection with WindowManager integration.

This module provides shadow routing that compares:
- Legacy: Current router decision
- Shadow: Graph-driven decision from Gateway with quota control

In production, only shadow decisions are logged (not used yet).
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

SHADOW_MODE = os.getenv("DENIS_INFERENCE_SHADOW", "1") == "1"

# Lazy import for WindowManager
_window_manager = None


def _get_window_manager():
    """Lazy load WindowManager."""
    global _window_manager
    if _window_manager is None:
        try:
            from denis_unified_v1.inference.window_manager import WindowManager

            _window_manager = WindowManager()
        except ImportError:
            logger.warning("WindowManager not available - using fail-open")
            _window_manager = None
    return _window_manager


@dataclass
class ShadowDecision:
    """Result of shadow model selection with full DecisionTrace signals."""

    provider: str
    model: str
    strategy: str
    reason: str
    task_profile_id: str
    latency_ms: int
    quota_available: bool = True
    result: str = "ok"
    routing_reason: str = ""
    shadow_diverged: bool = False
    legacy_provider: str = ""
    legacy_model: str = ""


# Alternative providers for fallback
_PROVIDER_FALLBACKS = {
    "llamacpp": ["groq", "openrouter"],
    "groq": ["openrouter"],
    "openrouter": ["openai"],
    "openai": ["anthropic"],
    "anthropic": ["groq"],
}

# Provider -> Default model mapping
_PROVIDER_DEFAULT_MODEL = {
    "llamacpp": "qwen2.5-3b",
    "groq": "llama-3.1-70b-versatile",
    "openrouter": "qwen3-8b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku",
}

# TaskProfile → Provider mapping
_TASK_PROFILE_PROVIDERS = {
    "intent_detection_fast": {"provider": "llamacpp", "model": "qwen2.5-0.5b"},
    "pro_search_prepare_fast": {"provider": "llamacpp", "model": "qwen2.5-3b"},
    "tool_runner_read_only": {"provider": "llamacpp", "model": "qwen2.5-3b"},
    "summarize_artifact": {"provider": "llamacpp", "model": "qwen2.5-3b"},
    "codecraft_generate": {"provider": "llamacpp", "model": "qwen2.5-coder-7b"},
    "deep_audit": {"provider": "groq", "model": "llama-3.1-70b-versatile"},
    "premium_search": {"provider": "llamacpp", "model": "qwen2.5-7b"},
    "incident_response": {"provider": "llamacpp", "model": "qwen2.5-0.5b"},
    "incident_triage": {"provider": "llamacpp", "model": "qwen2.5-3b"},
}


def _get_alternative_provider(provider: str) -> Optional[tuple[str, str]]:
    """Get alternative provider/model if available."""
    alternatives = _PROVIDER_FALLBACKS.get(provider, [])
    for alt in alternatives:
        if alt in _PROVIDER_DEFAULT_MODEL:
            return alt, _PROVIDER_DEFAULT_MODEL[alt]
    return None


def shadow_select(
    task_profile_id: str, intent: Optional[str] = None, phase: Optional[str] = None
) -> Optional[ShadowDecision]:
    """
    Select provider/model using graph-driven rules with WindowManager quota control.

    This does NOT affect actual routing - only logs decisions.
    Timeout: <=50ms. If fails, returns None for fail-open.
    """
    if not SHADOW_MODE:
        return None

    import time

    start = time.time()

    try:
        # Get provider config for task_profile
        config = _TASK_PROFILE_PROVIDERS.get(task_profile_id)

        if not config:
            # Fallback: use local small model
            config = {
                "provider": "llamacpp",
                "model": "qwen2.5-0.5b",
                "strategy": "single",
                "reason": f"unknown task_profile={task_profile_id}, using fallback",
            }

        provider = config["provider"]
        model = config["model"]

        # Check quota with WindowManager
        wm = _get_window_manager()
        quota_available = True
        reason = config.get("reason", "policy-match")
        strategy = config.get("strategy", "single")

        if wm is not None:
            quota_available = wm.can_use(provider, model)

            if not quota_available:
                # Try alternative provider
                alt = _get_alternative_provider(provider)
                if alt:
                    alt_provider, alt_model = alt
                    # Check if alternative is available
                    if wm.can_use(alt_provider, alt_model):
                        provider = alt_provider
                        model = alt_model
                        reason = f"quota-exceeded-primary, fallback-to-{alt_provider}"
                    else:
                        reason = "quota-exhausted-all-providers"
                else:
                    reason = "quota-exceeded-no-fallback"
            else:
                reason = config.get("reason", "policy-match")

            strategy = config.get("strategy", "single")

        latency_ms = int((time.time() - start) * 1000)

        # Determine routing_reason (for DecisionTrace)
        routing_reason = (
            f"task_profile={task_profile_id}, provider={provider}, reason={reason}"
        )

        # Fail-open: ensure we always return a decision
        decision = ShadowDecision(
            provider=provider,
            model=model,
            strategy=strategy,
            reason=reason,
            task_profile_id=task_profile_id,
            latency_ms=latency_ms,
            quota_available=quota_available,
            result="ok",
            routing_reason=routing_reason,
            shadow_diverged=False,
        )

        # Log shadow decision
        logger.info(
            f"[SHADOW_ROUTE] task={task_profile_id} intent={intent} phase={phase} → provider={decision.provider} model={decision.model} reason={decision.reason} quota={quota_available}"
        )

        return decision

    except Exception as e:
        # Fail-open: if anything fails, log and return error decision
        logger.warning(f"Shadow selection failed (fail-open): {e}")
        return ShadowDecision(
            provider="unknown",
            model="unknown",
            strategy="unknown",
            reason=f"error: {str(e)[:100]}",
            task_profile_id=task_profile_id or "unknown",
            latency_ms=0,
            quota_available=True,
            result="error",
            routing_reason="shadow_select_exception",
            shadow_diverged=False,
        )


def log_shadow_comparison(
    request_id: str,
    task_profile_id: str,
    legacy_provider: str,
    legacy_model: str,
    shadow_decision: Optional[ShadowDecision],
) -> dict[str, Any]:
    """
    Log comparison between legacy and shadow routing.

    Returns metrics dict for DecisionTrace.
    """
    if not SHADOW_MODE or shadow_decision is None:
        return {"shadow_used": False}

    same_choice = (
        legacy_provider == shadow_decision.provider
        and legacy_model == shadow_decision.model
    )

    metrics = {
        "shadow_used": True,
        "same_choice": same_choice,
        "legacy_provider": legacy_provider,
        "legacy_model": legacy_model,
        "shadow_provider": shadow_decision.provider,
        "shadow_model": shadow_decision.model,
        "shadow_strategy": shadow_decision.strategy,
        "shadow_reason": shadow_decision.reason,
        "task_profile_id": task_profile_id,
        "shadow_latency_ms": shadow_decision.latency_ms,
    }

    # Log to decision trace
    logger.info(
        f"[SHADOW_COMPARE] request={request_id} same={same_choice} legacy={legacy_provider}/{legacy_model} vs shadow={shadow_decision.provider}/{shadow_decision.model}"
    )

    return metrics


# Quick lookup for router integration
def get_shadow_provider_for_task(task_profile_id: str) -> tuple[str, str]:
    """Get (provider, model) tuple for task - for quick router integration."""
    config = _TASK_PROFILE_PROVIDERS.get(
        task_profile_id, _TASK_PROFILE_PROVIDERS["incident_response"]
    )
    return config["provider"], config["model"]
