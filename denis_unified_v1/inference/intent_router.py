"""Intent Router — Universal router that consumes MakinaOutput and routes to models."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from denis_unified_v1.inference.implicit_tasks import get_implicit_tasks
from denis_unified_v1.inference.makina_filter import (
    MakinaOutput,
    filter_input_safe,
    pre_execute_hook,
)
from denis_unified_v1.inference.quota_registry import MODEL_CONFIG, get_quota_registry

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.55

FALLBACK_CHAIN = {
    "claude": ["openrouter", "groq", "llama_local"],
    "groq": ["llama_local"],
    "openrouter": ["groq", "llama_local"],
    "llama_local": ["llama_local"],
}


@dataclass
class RoutedRequest:
    """A request that has been routed to a specific model."""

    model: str
    intent: str
    prompt: str
    implicit_tasks: List[str] = field(default_factory=list)
    context_prefilled: Dict[str, Any] = field(default_factory=dict)
    do_not_touch_auto: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    routing_trace: Dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False
    blocked: bool = False
    block_reason: Optional[str] = None
    repo_id: str = ""
    repo_name: str = ""
    branch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "intent": self.intent,
            "prompt": self.prompt,
            "implicit_tasks": self.implicit_tasks,
            "context_prefilled": self.context_prefilled,
            "do_not_touch_auto": self.do_not_touch_auto,
            "constraints": self.constraints,
            "acceptance_criteria": self.acceptance_criteria,
            "routing_trace": self.routing_trace,
            "fallback_used": self.fallback_used,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
        }


class IntentRouter:
    """Universal router that consumes MakinaOutput and routes to models."""

    def __init__(self):
        self._quota_registry = get_quota_registry()
        self._implicit_tasks = get_implicit_tasks()

    def route(
        self,
        makina_output: MakinaOutput,
        prompt: str,
        session_id: str = "default",
    ) -> RoutedRequest:
        """Route a MakinaOutput to a model."""
        intent = makina_output.intent.get("pick", "unknown")
        confidence = makina_output.intent.get("confidence", 0.0)

        should_proceed, output, block_reason = pre_execute_hook(prompt, makina_output.context_refs)
        if not should_proceed:
            return RoutedRequest(
                model="llama_local",
                intent=intent,
                prompt=prompt,
                implicit_tasks=[],
                routing_trace={"reason": "blocked", "block_reason": block_reason},
                blocked=True,
                block_reason=block_reason,
            )

        if makina_output.missing_inputs:
            return RoutedRequest(
                model="llama_local",
                intent=intent,
                prompt=prompt,
                implicit_tasks=[],
                routing_trace={"reason": "missing_inputs", "missing": makina_output.missing_inputs},
                blocked=True,
                block_reason=f"Missing inputs: {makina_output.missing_inputs}",
            )

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            return self._build_routed_request(
                intent=intent,
                prompt=prompt,
                model="llama_local",
                confidence=confidence,
                reason="low_confidence",
                makina_output=makina_output,
                session_id=session_id,
            )

        model = self._select_model(intent, confidence, makina_output)

        return self._build_routed_request(
            intent=intent,
            prompt=prompt,
            model=model,
            confidence=confidence,
            reason="routed",
            makina_output=makina_output,
            session_id=session_id,
        )

    def _select_model(
        self,
        intent: str,
        confidence: float,
        makina_output: MakinaOutput,
    ) -> str:
        """Select the best model for an intent."""
        best_model = self._quota_registry.get_best_model_for(intent)

        if self._quota_registry.is_available(best_model):
            return best_model

        fallback_chain = FALLBACK_CHAIN.get(best_model, ["llama_local"])
        for fallback_model in fallback_chain:
            if self._quota_registry.is_available(fallback_model):
                return fallback_model

        return "llama_local"

    def _build_routed_request(
        self,
        intent: str,
        prompt: str,
        model: str,
        confidence: float,
        reason: str,
        makina_output: MakinaOutput,
        session_id: str,
    ) -> RoutedRequest:
        """Build a RoutedRequest with all enrichments."""
        implicit_context = self._implicit_tasks.enrich_with_session(intent, session_id)

        repo_id = ""
        repo_name = ""
        branch = ""
        try:
            from control_plane.repo_context import RepoContext

            repo_ctx = RepoContext()
            repo_id = repo_ctx.repo_id
            repo_name = repo_ctx.repo_name
            branch = repo_ctx.branch
        except Exception:
            pass

        return RoutedRequest(
            model=model,
            intent=intent,
            prompt=prompt,
            implicit_tasks=implicit_context.implicit_tasks,
            context_prefilled=implicit_context.context_prefilled,
            do_not_touch_auto=implicit_context.do_not_touch_auto,
            constraints=makina_output.constraints,
            acceptance_criteria=makina_output.acceptance_criteria,
            routing_trace=self._build_routing_trace(intent, model, reason),
            fallback_used=reason == "fallback",
            repo_id=repo_id,
            repo_name=repo_name,
            branch=branch,
        )

    def _build_routing_trace(self, intent: str, model: str, reason: str) -> Dict[str, Any]:
        """Build routing trace for debugging."""
        return {
            "intent": intent,
            "selected_model": model,
            "reason": reason,
            "available_models": self._quota_registry.get_available_models(),
        }

    def route_safe(
        self,
        makina_output: MakinaOutput,
        prompt: str,
        session_id: str = "default",
    ) -> RoutedRequest:
        """Safe wrapper with fail-open."""
        try:
            return self.route(makina_output, prompt, session_id)
        except Exception as e:
            logger.error(f"Router error: {e}, failing open to llama_local")
            return RoutedRequest(
                model="llama_local",
                intent=makina_output.intent.get("pick", "unknown"),
                prompt=prompt,
                routing_trace={"reason": "error", "error": str(e)},
            )


def route_input(
    prompt: str, session_id: str = "default", context_refs: List[str] = None
) -> RoutedRequest:
    """
    Unified entry point that combines filter + router in one call.

    This is the function all Denis modules should use.
    One call, complete result.
    """
    if context_refs is None:
        context_refs = []

    should_proceed, makina_output, block_reason = pre_execute_hook(prompt, context_refs)
    if not should_proceed:
        return RoutedRequest(
            model="llama_local",
            intent=makina_output.intent.get("pick", "unknown"),
            prompt=prompt,
            implicit_tasks=[],
            routing_trace={"reason": "blocked_by_hook", "block_reason": block_reason},
            blocked=True,
            block_reason=block_reason,
        )

    filter_result = filter_input_safe({"prompt": prompt, "context_refs": context_refs})

    if filter_result.missing_inputs:
        return RoutedRequest(
            model="llama_local",
            intent=filter_result.intent.get("pick", "unknown"),
            prompt=prompt,
            implicit_tasks=[],
            routing_trace={"reason": "missing_inputs", "missing": filter_result.missing_inputs},
            blocked=True,
            block_reason=f"Missing inputs: {filter_result.missing_inputs}",
        )

    router = IntentRouter()
    return router.route_safe(filter_result, prompt, session_id)


__all__ = ["IntentRouter", "RoutedRequest", "route_input"]
