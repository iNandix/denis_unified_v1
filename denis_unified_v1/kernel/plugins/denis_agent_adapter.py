"""
Denis Kernel - Denis Agent Adapter
=================================
Adapter that wraps Denis Agent (legacy) as a planner worker.

Role: Converts Denis Agent from "brain that executes" to "planner that proposes".
Only active when Governor commits route_id in {project, deliberate, toolchain}.

Key principle:
- DenisAgent proposes (tool.proposal, plan.delta)
- Governor decides
- ToolRuntime executes
- Delivery renders
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

from denis_unified_v1.kernel.bus.event_bus import Event, get_event_bus

logger = logging.getLogger(__name__)


class PlanStatus(Enum):
    """Status of a plan step."""

    THINKING = "thinking"
    PROPOSING = "proposing"
    WAITING_TOOL = "waiting_tool"
    EXECUTING = "executing"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class AgentPlanStep:
    """A single step in the agent's plan."""

    step_id: str
    action: str  # tool_proposal | ask_user | finish
    tool_name: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    confidence: float = 0.5
    requires_confirmation: bool = False
    rationale: str = ""
    depends_on: Optional[str] = None


@dataclass
class AgentPlan:
    """A plan produced by Denis Agent."""

    plan_id: str
    status: PlanStatus
    steps: List[AgentPlanStep]
    current_step_index: int = 0
    context: Dict[str, Any] = None


class DenisAgentAdapter:
    """
    Adapter that wraps Denis Agent as a planner worker.

    Consumes:
    - policy.route.commit (when route_id in {project, deliberate, toolchain})

    Emits:
    - status.phase (thinking, proposing, etc.)
    - tool.proposal (next step to execute)
    - plan.delta (plan updates)
    - plan.complete (when done)

    Does NOT:
    - Execute tools directly
    - Commit routes
    - Render final output
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus or get_event_bus()

        self._active_plans: Dict[str, AgentPlan] = {}
        self._waiting_for_tool: Dict[str, str] = {}  # trace_id -> plan_id

        self._subscribe()
        logger.info("DenisAgentAdapter initialized")

    def _subscribe(self):
        """Subscribe to events."""
        self.event_bus.subscribe("policy.route.commit", self._on_route_commit)
        self.event_bus.subscribe("tool.result", self._on_tool_result)
        self.event_bus.subscribe("tool.error", self._on_tool_error)
        self.event_bus.subscribe("input.interrupt", self._on_interrupt)

    async def _on_route_commit(self, event: Event):
        """Handle route commit - activate if this is an agent route."""
        route_id = event.payload.get("route_id", "")

        if route_id not in {"project", "deliberate", "toolchain"}:
            return

        trace_id = event.trace_id
        session_id = event.session_id
        context = event.payload.get("context", {})

        logger.info(f"DenisAgentAdapter activated for {trace_id} route={route_id}")

        # Emit thinking phase
        await self._emit_status(
            trace_id, session_id, PlanStatus.THINKING, "Analyzing request"
        )

        # Create initial plan (in real implementation, this would call denis_agent_canonical)
        plan = await self._create_initial_plan(trace_id, session_id, context)

        if plan and plan.steps:
            self._active_plans[trace_id] = plan
            await self._emit_next_step(trace_id, session_id, plan)

    async def _create_initial_plan(
        self, trace_id: str, session_id: str, context: Dict[str, Any]
    ) -> Optional[AgentPlan]:
        """
        Create initial plan from context.

        In real implementation, this would call denis_agent_canonical (the planner)
        to analyze the request and produce a plan.

        For now, returns a simple plan that can be extended.
        """
        user_message = context.get("text", context.get("user_message", ""))

        # Simple heuristic for demo - in real impl, call denis_agent_canonical
        steps = []

        # If message contains action keywords, propose tool
        action_keywords = {
            "busca": "hass.entity.search",
            "enciende": "hass.service.call",
            "apaga": "hass.service.call",
            "temperatura": "hass.state.snapshot",
            "estado": "hass.state.snapshot",
            "despliega": "deployment.execute",
            "deploy": "deployment.execute",
        }

        user_message_lower = user_message.lower()

        for keyword, tool in action_keywords.items():
            if keyword in user_message_lower:
                step = AgentPlanStep(
                    step_id=f"{trace_id}_step_0",
                    action="tool_proposal",
                    tool_name=tool,
                    args={"query": user_message}
                    if tool == "hass.entity.search"
                    else {"domain": "light", "service": "turn_on"},
                    confidence=0.8,
                    rationale=f"Detected '{keyword}' in message",
                )
                steps.append(step)
                break

        if not steps:
            # Default: just acknowledge
            steps.append(
                AgentPlanStep(
                    step_id=f"{trace_id}_step_0",
                    action="finish",
                    rationale="No specific action detected",
                )
            )

        return AgentPlan(
            plan_id=f"plan_{trace_id}",
            status=PlanStatus.PROPOSING,
            steps=steps,
            context=context,
        )

    async def _on_tool_result(self, event: Event):
        """Handle tool result - continue plan execution."""
        trace_id = event.trace_id
        plan = self._active_plans.get(trace_id)

        if not plan:
            return

        tool_result = event.payload.get("output", {})

        # Update plan status
        plan.status = PlanStatus.PROPOSING

        # Move to next step
        plan.current_step_index += 1

        if plan.current_step_index >= len(plan.steps):
            # Plan complete
            plan.status = PlanStatus.COMPLETE
            await self._emit_plan_complete(trace_id, event.session_id, tool_result)
            del self._active_plans[trace_id]
        else:
            # Emit next step
            await self._emit_next_step(trace_id, event.session_id, plan)

    async def _on_tool_error(self, event: Event):
        """Handle tool error - decide if retry or fail."""
        trace_id = event.trace_id
        plan = self._active_plans.get(trace_id)

        if not plan:
            return

        error = event.payload.get("error", "Unknown error")

        # Mark current step as failed
        plan.status = PlanStatus.FAILED

        # Emit failure status
        await self._emit_status(
            trace_id, event.session_id, PlanStatus.FAILED, f"Tool failed: {error}"
        )

        # Clean up
        del self._active_plans[trace_id]

    async def _on_interrupt(self, event: Event):
        """Handle user interruption - cancel active plans."""
        trace_id = event.trace_id

        if trace_id in self._active_plans:
            plan = self._active_plans[trace_id]
            plan.status = PlanStatus.BLOCKED

            await self._emit_status(
                trace_id,
                event.session_id,
                PlanStatus.BLOCKED,
                "Plan interrupted by user",
            )

            del self._active_plans[trace_id]
            logger.info(f"Plan {plan.plan_id} interrupted for {trace_id}")

    async def _emit_status(
        self, trace_id: str, session_id: str, status: PlanStatus, message: str
    ):
        """Emit status.phase event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="denis_agent_adapter",
            type="status.phase",
            priority=0,
            payload={
                "phase": status.value,
                "message": message,
            },
        )
        await self.event_bus.emit(event)
        logger.debug(f"Status: {status.value} - {message}")

    async def _emit_next_step(self, trace_id: str, session_id: str, plan: AgentPlan):
        """Emit the next tool proposal from the plan."""
        if plan.current_step_index >= len(plan.steps):
            return

        step = plan.steps[plan.current_step_index]

        if step.action == "tool_proposal" and step.tool_name:
            # Emit tool proposal
            event = Event(
                trace_id=trace_id,
                session_id=session_id,
                source="denis_agent_adapter",
                type="tool.proposal",
                priority=0,
                payload={
                    "tool_name": step.tool_name,
                    "args": step.args or {},
                    "confidence": step.confidence,
                    "requires_confirmation": step.requires_confirmation,
                    "rationale": step.rationale,
                    "step_id": step.step_id,
                },
            )
            await self.event_bus.emit(event)
            logger.info(f"Proposed: {step.tool_name} for {trace_id}")

        elif step.action == "finish":
            # Plan complete
            await self._emit_plan_complete(trace_id, session_id, {})

    async def _emit_plan_complete(
        self, trace_id: str, session_id: str, final_result: Dict[str, Any]
    ):
        """Emit plan.complete event."""
        event = Event(
            trace_id=trace_id,
            session_id=session_id,
            source="denis_agent_adapter",
            type="plan.complete",
            priority=0,
            payload={
                "result": final_result,
                "status": "success",
            },
        )
        await self.event_bus.emit(event)

        await self._emit_status(
            trace_id, session_id, PlanStatus.COMPLETE, "Plan executed successfully"
        )

        logger.info(f"Plan complete for {trace_id}")

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            "active_plans": len(self._active_plans),
            "plans": [
                {
                    "plan_id": p.plan_id,
                    "status": p.status.value,
                    "current_step": p.current_step_index,
                    "total_steps": len(p.steps),
                }
                for p in self._active_plans.values()
            ],
        }


# Global adapter instance
_denis_agent_adapter: Optional[DenisAgentAdapter] = None


def get_denis_agent_adapter() -> DenisAgentAdapter:
    """Get or create Denis Agent Adapter."""
    global _denis_agent_adapter
    if _denis_agent_adapter is None:
        _denis_agent_adapter = DenisAgentAdapter()
    return _denis_agent_adapter
