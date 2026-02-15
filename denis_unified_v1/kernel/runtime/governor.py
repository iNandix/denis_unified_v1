"""
Denis Kernel - Governor
========================
The authority node that arbitrates all signals and makes routing decisions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import logging

from denis_unified_v1.kernel.bus.event_bus import (
    EventBus,
    Event,
    CommitLevel,
    get_event_bus,
)

logger = logging.getLogger(__name__)


class RouteType(Enum):
    FAST_TALK = "fast_talk"
    STANDARD = "standard"
    TOOL = "tool"
    PROJECT = "project"
    DELIBERATE = "deliberate"
    TOOLCHAIN = "toolchain"
    SAFE = "safe"


class ReasoningMode(Enum):
    DIRECT = "direct"
    STRUCTURED = "structured"
    DELIBERATE = "deliberate"
    VERIFY = "verify"


class IdeMode(Enum):
    """IDE interaction modes."""

    FOCUS = "ide_focus"  # Voz off, texto only, max throughput
    ASSIST = "ide_assist"  # Voz lite, texto on, narra progreso
    REVIEW = "ide_review"  # Voz lite, texto on, explicacion + validacion


@dataclass
class RouteDecision:
    """A routing decision made by the Governor."""

    route_id: RouteType
    reason: str
    confidence: float
    requires_confirmation: bool = False
    reasoning_mode: ReasoningMode = ReasoningMode.DIRECT
    max_budget_tokens: int = 512
    cancel_keys_to_cancel: List[str] = field(default_factory=list)


class Governor:
    """
    The central authority node in Denis Kernel.

    Responsibilities:
    - Listen to all signal events (NLU, Rasa, ParlAI, Loops, Memory)
    - Make routing decisions (route.commit)
    - Handle cancellation
    - Manage backpressure
    - Enforce confirmation for risky actions

    Key principle: All plugins propose, Governor decides.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        fast_talk_confidence_threshold: float = 0.9,
        confirmation_required_tools: Optional[Set[str]] = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.fast_talk_confidence_threshold = fast_talk_confidence_threshold
        self.confirmation_required_tools = confirmation_required_tools or {
            "deployment_exec",
            "contract_changes",
            "identity_verification",
            "file_delete",
            "file_modify_sensitive",
        }

        # HASS Scope/Risk Matrix
        # Format: scope -> risk_level (autonomy | sandbox | always_approve)
        self.hass_scope_risk = {
            "hass_lights": "autonomy",
            "hass_media": "autonomy",
            "hass_climate": "sandbox",
            "hass_automations": "sandbox",
            "hass_integrations": "always_approve",
            "hass_hacs": "always_approve",
            "hass_locks": "always_approve",
            "hass_alarm": "always_approve",
            "hass_garage": "always_approve",
            "hass_cameras_privacy": "always_approve",
            "hass_network": "always_approve",
        }


        self._running = False
        self._governor_task: Optional[asyncio.Task] = None

        self._pending_proposals: Dict[str, Dict[str, Any]] = {}
        self._confirmed_routes: Dict[str, RouteDecision] = {}
        self._decision_timestamps: Dict[str, float] = {}

        self._signal_buffers: Dict[str, List[Event]] = {}
        self._decision_deadline_ms: int = 250

        logger.info("Governor initialized")

    async def start(self):
        """Start the Governor."""
        if self._running:
            return
        self._running = True

        self.event_bus.subscribe("nlu.*", self._on_nlu_event)
        self.event_bus.subscribe("dialogue.signal", self._on_dialogue_event)
        self.event_bus.subscribe("policy.route.proposed", self._on_route_proposed)
        self.event_bus.subscribe("policy.risk.assessment", self._on_risk_assessment)
        self.event_bus.subscribe("loop.signal", self._on_loop_signal)
        self.event_bus.subscribe("input.interrupt", self._on_interrupt)
        self.event_bus.subscribe("scheduler.cancel", self._on_cancel_request)

        self._governor_task = asyncio.create_task(self._governor_loop())
        logger.info("Governor started")

    async def stop(self):
        """Stop the Governor."""
        self._running = False
        if self._governor_task:
            self._governor_task.cancel()
            try:
                await self._governor_task
            except asyncio.CancelledError:
                pass
        logger.info("Governor stopped")

    async def _on_nlu_event(self, event: Event):
        """Handle NLU events."""
        self._buffer_signal(event.trace_id, event)
        await self._maybe_make_decision(event.trace_id)

    async def _on_dialogue_event(self, event: Event):
        """Handle dialogue signals from ParlAI."""
        self._buffer_signal(event.trace_id, event)
        await self._maybe_make_decision(event.trace_id)

    async def _on_route_proposed(self, event: Event):
        """Handle route proposals from RouteProposer."""
        trace_id = event.trace_id
        self._pending_proposals[trace_id] = event.payload
        await self._maybe_make_decision(trace_id)

    async def _on_risk_assessment(self, event: Event):
        """Handle risk assessments from NeuroLayers/Loops."""
        self._buffer_signal(event.trace_id, event)
        await self._maybe_make_decision(event.trace_id)

    async def _on_loop_signal(self, event: Event):
        """Handle loop signals."""
        self._buffer_signal(event.trace_id, event)
        await self._maybe_make_decision(event.trace_id)

    async def _on_interrupt(self, event: Event):
        """Handle user interruptions."""
        logger.info(f"Interrupt received: {event.payload}")
        cancel_key = event.payload.get("cancel_key", "")

        if cancel_key:
            await self.event_bus.cancel(cancel_key)

            decision = RouteDecision(
                route_id=RouteType.STANDARD,
                reason="User interruption",
                confidence=1.0,
                reasoning_mode=ReasoningMode.DIRECT,
            )
            self._confirmed_routes[event.trace_id] = decision
            await self._emit_route_commit(event.trace_id, decision)

    async def _on_cancel_request(self, event: Event):
        """Handle external cancel requests."""
        cancel_key = event.payload.get("cancel_key", "")
        if cancel_key:
            await self.event_bus.cancel(cancel_key)
            logger.info(f"Cancel requested: {cancel_key}")

    def _buffer_signal(self, trace_id: str, event: Event):
        """Buffer a signal for decision making."""
        if trace_id not in self._signal_buffers:
            self._signal_buffers[trace_id] = []
        self._signal_buffers[trace_id].append(event)

    async def _maybe_make_decision(self, trace_id: str):
        """Make a routing decision if enough signals or deadline reached."""
        signals = self._signal_buffers.get(trace_id, [])

        if not signals:
            return

        time_since_first = time.time() - self._decision_timestamps.get(
            trace_id, time.time()
        )
        time_since_first_ms = int(time_since_first * 1000)

        has_proposal = trace_id in self._pending_proposals

        should_decide = (
            has_proposal or time_since_first_ms >= self._decision_deadline_ms
        )

        if should_decide:
            await self._make_decision(trace_id, signals)

    async def _make_decision(self, trace_id: str, signals: List[Event]):
        """Make a routing decision based on accumulated signals."""

        proposal = self._pending_proposals.get(trace_id, {})

        nlu_signals = [s for s in signals if s.type.startswith("nlu.")]
        loop_signals = [s for s in signals if s.type == "loop.signal"]
        risk_signals = [s for s in signals if s.type == "policy.risk.assessment"]

        intent = None
        confidence = 0.5
        tool_required = proposal.get("tool_required", False)

        for signal in nlu_signals:
            if signal.type == "nlu.intent.hypothesis":
                intent = signal.payload.get("intent")
                confidence = signal.payload.get("confidence", 0.5)

        risk_level = "low"
        for signal in risk_signals:
            level = signal.payload.get("level", "low")
            if level == "high":
                risk_level = "high"
                break

        route_id, reasoning_mode, requires_confirmation = self._decide_route(
            intent=intent,
            confidence=confidence,
            tool_required=tool_required,
            risk_level=risk_level,
        )

        decision = RouteDecision(
            route_id=route_id,
            reason=self._build_reason(intent, confidence, tool_required, risk_level),
            confidence=confidence,
            requires_confirmation=requires_confirmation,
            reasoning_mode=reasoning_mode,
        )

        self._confirmed_routes[trace_id] = decision
        self._decision_timestamps[trace_id] = time.time()

        if decision.cancel_keys_to_cancel:
            for ck in decision.cancel_keys_to_cancel:
                await self.event_bus.cancel(ck)

        await self._emit_route_commit(trace_id, decision, proposal)

        if requires_confirmation:
            await self._emit_confirm_request(trace_id, decision, proposal)

        if trace_id in self._signal_buffers:
            del self._signal_buffers[trace_id]
        if trace_id in self._pending_proposals:
            del self._pending_proposals[trace_id]

    def _decide_route(
        self,
        intent: Optional[str],
        confidence: float,
        tool_required: bool,
        risk_level: str,
    ) -> tuple[RouteType, ReasoningMode, bool]:
        """Decide the route based on signals."""

        fast_intents = {"greet", "thanks", "bye", "hello", "goodbye"}

        if (
            intent
            and intent.lower() in fast_intents
            and confidence >= self.fast_talk_confidence_threshold
        ):
            return RouteType.FAST_TALK, ReasoningMode.DIRECT, False

        if confidence >= self.fast_talk_confidence_threshold and not tool_required:
            return RouteType.STANDARD, ReasoningMode.DIRECT, False

        # IDE-specific routes
        if intent == "refactor":
            return RouteType.PROJECT, ReasoningMode.STRUCTURED, False

        if tool_required:
            requires_confirmation = risk_level == "high"
            if risk_level == "high":
                return RouteType.DELIBERATE, ReasoningMode.VERIFY, True
            return RouteType.TOOL, ReasoningMode.STRUCTURED, requires_confirmation

        if risk_level == "high":
            return RouteType.DELIBERATE, ReasoningMode.VERIFY, True

        return RouteType.STANDARD, ReasoningMode.STRUCTURED, False

    def _build_reason(
        self,
        intent: Optional[str],
        confidence: float,
        tool_required: bool,
        risk_level: str,
    ) -> str:
        """Build human-readable reason for decision."""
        parts = []
        if intent:
            parts.append(f"intent={intent}")
        parts.append(f"conf={confidence:.2f}")
        if tool_required:
            parts.append("tool=true")
        parts.append(f"risk={risk_level}")
        return ", ".join(parts)

    async def _emit_route_commit(
        self,
        trace_id: str,
        decision: RouteDecision,
        proposal: Optional[Dict[str, Any]] = None,
    ):
        """Emit policy.route.commit event."""
        payload = {
            "route_id": decision.route_id.value,
            "reason": decision.reason,
            "reasoning_mode": decision.reasoning_mode.value,
            "max_budget_tokens": decision.max_budget_tokens,
        }

        if proposal:
            if tool_name := proposal.get("tool_name"):
                payload["tool_name"] = tool_name
            if args := proposal.get("args"):
                payload["args"] = args

        event = Event(
            trace_id=trace_id,
            source="governor",
            type="policy.route.commit",
            priority=-1,
            commit_level=CommitLevel.FINAL,
            payload=payload,
        )
        await self.event_bus.emit(event)
        logger.info(
            f"Governor committed route: {decision.route_id.value} for {trace_id}"
        )

    async def _emit_confirm_request(
        self,
        trace_id: str,
        decision: RouteDecision,
        proposal: Dict[str, Any],
    ):
        """Emit confirmation request for risky actions."""
        event = Event(
            trace_id=trace_id,
            source="governor",
            type="policy.confirm.request",
            priority=-2,
            commit_level=CommitLevel.FINAL,
            payload={
                "tool_name": proposal.get("tool_name", "unknown"),
                "reason": f"High risk: {decision.reason}",
                "route": decision.route_id.value,
            },
        )
        await self.event_bus.emit(event)
        logger.info(f"Governor requested confirmation for {trace_id}")

    async def _governor_loop(self):
        """Main governor loop for periodic tasks."""
        while self._running:
            try:
                await asyncio.sleep(1.0)

                now = time.time()
                expired_traces = [
                    trace_id
                    for trace_id, ts in self._decision_timestamps.items()
                    if now - ts > 300
                ]
                for trace_id in expired_traces:
                    self._confirmed_routes.pop(trace_id, None)
                    self._signal_buffers.pop(trace_id, None)
                    self._pending_proposals.pop(trace_id, None)
                    self._decision_timestamps.pop(trace_id, None)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in governor loop: {e}")

    def check_ui_gate(self, user_role: str, requested_access: str) -> bool:
        """
        Check if UI access is allowed based on user role.

        Returns True if allowed.
        """
        allowed = self.ui_permissions.get(user_role, [])
        return requested_access in allowed

    def set_ide_mode(self, mode: IdeMode):
        """Set IDE mode explicitly."""
        self.ide_mode = mode
        logger.info(f"IDE mode set to: {mode.value}")

    def auto_switch_ide_mode(
        self,
        route_type: Optional[RouteType] = None,
        has_heavy_job: bool = False,
        user_requested_focus: bool = False,
        awaiting_approval: bool = False,
    ) -> IdeMode:
        """
        Auto-switch IDE mode based on context.

        Rules:
        - ide_focus: user requests focus mode OR heavy job running
        - ide_review: awaiting user approval for changeset
        - ide_assist: default, everything else
        """
        # Priority 1: user explicitly wants focus
        if user_requested_focus:
            self.ide_mode = IdeMode.FOCUS
        # Priority 2: heavy job running
        elif has_heavy_job and self.ide_mode != IdeMode.FOCUS:
            self.ide_mode = IdeMode.FOCUS
        # Priority 3: waiting for approval/review
        elif awaiting_approval:
            self.ide_mode = IdeMode.REVIEW
        # Default: assist mode
        else:
            self.ide_mode = IdeMode.ASSIST

        logger.debug(f"Auto-switched IDE mode to: {self.ide_mode.value}")
        return self.ide_mode

    def get_ide_config(self) -> Dict[str, Any]:
        """Get current IDE configuration for delivery."""
        return {
            "mode": self.ide_mode.value,
            "voice_enabled": self.ide_mode != IdeMode.FOCUS,
            "text_enabled": True,
            "narrare_progress": self.ide_mode == IdeMode.ASSIST,
            "capability": self.ide_capability,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get Governor statistics."""
        return {
            "pending_proposals": len(self._pending_proposals),
            "confirmed_routes": len(self._confirmed_routes),
            "signal_buffers": len(self._signal_buffers),
            "confirmation_required_tools": list(self.confirmation_required_tools),
            "hass_scope_risk": self.hass_scope_risk,
            "ide_mode": self.ide_mode.value,
            "ide_capability": self.ide_capability,
        }


# Global governor instance
_governor: Optional[Governor] = None


def get_governor() -> Governor:
    """Get the global Governor instance."""
    global _governor
    if _governor is None:
        _governor = Governor()
    return _governor


async def initialize_kernel() -> tuple[EventBus, Governor]:
    """Initialize the kernel (EventBus + Governor)."""
    event_bus = get_event_bus()
    governor = get_governor()

    await event_bus.start()
    await governor.start()

    logger.info("Denis Kernel initialized")
    return event_bus, governor


async def shutdown_kernel():
    """Shutdown the kernel."""
    event_bus = get_event_bus()
    governor = get_governor()

    await governor.stop()
    await event_bus.stop()

    logger.info("Denis Kernel shutdown")
