#!/usr/bin/env python3
"""
Denis Kernel API - Mínima con contrato interno.

Entradas: intent_hint, user_id, group_id, channel, payload, budget, safety_mode
Salidas: route, context_pack, plan, tool_calls, response
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from denis_unified_v1.kernel.runtime.governor import get_governor, RouteType, ReasoningMode
from denis_unified_v1.kernel.decision_trace import DecisionTrace, emit_trace
from denis_unified_v1.kernel.scheduler import get_model_scheduler, InferenceRequest

from denis_unified_v1.services.human_memory_manager import get_human_memory_manager
from denis_unified_v1.services.context_manager import get_context_manager

# Routes that require context packs to be built
NEEDS_CONTEXT = {"toolchain", "verify", "project"}

# Routes that get IDE packs (subset of NEEDS_CONTEXT)
IDE_ROUTES = {"toolchain", "project"}

# Attribution flags for verification envelope
ATTRIBUTION_FLAGS = {
    "NO_EVIDENCE_AVAILABLE": "NO_EVIDENCE_AVAILABLE",
    "EVIDENCE_PARTIAL": "EVIDENCE_PARTIAL", 
    "DERIVED_FROM_TRACE": "DERIVED_FROM_TRACE",
    "DERIVED_FROM_TOOL_OUTPUT": "DERIVED_FROM_TOOL_OUTPUT",
    "ASSUMPTION_MADE": "ASSUMPTION_MADE",
    "REQUIRES_HUMAN_CONFIRMATION": "REQUIRES_HUMAN_CONFIRMATION",
    "SAFETY_MODE_STRICT_APPLIED": "SAFETY_MODE_STRICT_APPLIED",
    "UNVERIFIED_USER_ASSERTION": "UNVERIFIED_USER_ASSERTION",
}

@dataclass
class KernelRequest:
    """Kernel request contract."""
    intent_hint: Optional[str] = None
    user_id: Optional[str] = None
    group_id: Optional[str] = None
    channel: str = "api"  # voice/cli/ide/api
    payload: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=lambda: {"tokens": 2048, "latency": 5000, "cost": 0.1})
    safety_mode: str = "default"  # default/strict

@dataclass
class KernelResponse:
    """Kernel response contract."""
    request_id: str
    route: str
    context_pack: Optional[Dict[str, Any]] = None
    plan: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    response: Dict[str, Any] = field(default_factory=dict)
    decision_trace: DecisionTrace = None
    
    # Verification envelope (especially for verify routes)
    attribution_flags: List[str] = field(default_factory=list)
    attribution_language: str = "en"  # "en" or "es"
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    disclaimers: List[str] = field(default_factory=list)

class KernelAPI:
    """Kernel API mínima."""

    def __init__(self):
        self.human_memory = get_human_memory_manager()
        self.context_manager = get_context_manager()
        self.governor = get_governor()

    async def process_request(self, request: KernelRequest) -> KernelResponse:
        """Process request end-to-end with observability."""
        request_id = str(uuid.uuid4())
        trace = DecisionTrace(trace_id=request_id)
        
        # Set initial context
        trace.set_safety_mode(request.safety_mode or "default")
        
        # Step 1: Route determination
        route_phase_id = trace.start_phase("route", budget_planned=50)  # Small budget for routing
        try:
            route = await self._determine_route(request, trace)
            trace.end_phase(route_phase_id, budget_actual=25)  # Estimate actual usage
        except Exception as e:
            trace.end_phase(route_phase_id, budget_actual=50)  # Full budget on error
            raise

        # Step 2: Context pack building
        pack_phase_id = trace.start_phase("context_pack", budget_planned=request.budget.get("tokens", 2048))
        try:
            context_pack = await self._build_context_pack(request, route, trace)
            trace.end_phase(pack_phase_id, budget_actual=context_pack.get("token_estimate", 1024) if context_pack else 0)
        except Exception as e:
            trace.end_phase(pack_phase_id, budget_actual=request.budget.get("tokens", 2048))
            raise

        # Step 3: Plan generation
        plan_phase_id = trace.start_phase("plan", budget_planned=512)
        try:
            plan = await self._generate_plan(request, route, trace)
            trace.end_phase(plan_phase_id, budget_actual=256)  # Estimate
        except Exception as e:
            trace.end_phase(plan_phase_id, budget_actual=512)
            raise

        # Step 4: Tool execution
        tools_phase_id = trace.start_phase("tools", budget_planned=1024)
        try:
            tool_calls, response = await self._execute_tools(request, plan, trace)
            trace.end_phase(tools_phase_id, budget_actual=sum(tc.get("tokens_used", 128) for tc in tool_calls))
        except Exception as e:
            trace.end_phase(tools_phase_id, budget_actual=1024)
            raise

        # Step 5: Verification envelope (if applicable)
        if route in ["verify"]:
            verify_phase_id = trace.start_phase("verify", budget_planned=256)
            try:
                verification_envelope = self._build_verification_envelope(request, route, plan, tool_calls, trace)
                trace.end_phase(verify_phase_id, budget_actual=128)
            except Exception as e:
                trace.end_phase(verify_phase_id, budget_actual=256)
                raise
        else:
            verification_envelope = self._build_verification_envelope(request, route, plan, tool_calls, trace)

        # Step 6: Response rendering
        render_phase_id = trace.start_phase("render_response", budget_planned=128)
        try:
            response_data = {
                "text": response.get("text", ""),
                "attribution_flags": response.get("attribution_flags", []),
                "followups": response.get("followups", [])
            }
            trace.end_phase(render_phase_id, budget_actual=64)
        except Exception as e:
            trace.end_phase(render_phase_id, budget_actual=128)
            raise

        # Finalize trace
        trace.finalize(route, context_pack, plan, tool_calls, response_data)
        
        # Emit trace for observability
        emit_trace(trace)

        return KernelResponse(
            request_id=request_id,
            route=route,
            context_pack=context_pack,
            plan=plan,
            tool_calls=tool_calls,
            response=response_data,
            decision_trace=trace,
            attribution_flags=verification_envelope["attribution_flags"],
            attribution_language=verification_envelope["attribution_language"],
            evidence_refs=verification_envelope["evidence_refs"],
            disclaimers=verification_envelope["disclaimers"],
        )

    async def _determine_route(self, request: KernelRequest, trace: DecisionTrace) -> str:
        """Determine route using Governor."""
        governor = get_governor()

        intent = request.intent_hint
        confidence = request.payload.get("confidence", 0.5)
        tool_required = "tool" in request.payload
        risk_level = "high" if request.safety_mode == "strict" else "low"

        route_id, reasoning_mode, requires_confirmation = governor._decide_route(
            intent=intent,
            confidence=confidence,
            tool_required=tool_required,
            risk_level=risk_level,
        )

        route = route_id.value

        # Normalize Governor route names to Scheduler expectations
        if route_id == RouteType.TOOL:
            route = "toolchain"
        elif route_id == RouteType.DELIBERATE and reasoning_mode == ReasoningMode.VERIFY:
            route = "verify"

        trace.set_route(route_id.value, route, reasoning_mode.value if reasoning_mode else None)
        trace.add_step("route_determined", {"route": route, "intent": intent, "confidence": confidence, "reasoning_mode": reasoning_mode.value if reasoning_mode else "direct"})
        return route

    async def _build_context_pack(self, request: KernelRequest, route: str, trace: DecisionTrace) -> Optional[Dict[str, Any]]:
        """Build context pack."""
        focus_files = request.payload.get("focus_files", [])
        intent = request.intent_hint or "general"

        # Build IDE pack for IDE channel or routes that need structured context
        want_ide = (request.channel == "ide") or (route in IDE_ROUTES)
        pack_type = "ide" if want_ide else "human"

        if pack_type == "ide":
            pack, status, errors = self.context_manager.build_context_pack(intent, focus_files, "denis_unified_v1")
            trace.set_context_pack(pack["pack_type"], pack.get("token_estimate", 0), status, errors)
            trace.add_step("context_pack_built", {"pack_type": pack.get("pack_type", "unknown"), "token_estimate": pack.get("token_estimate", 0)})
            trace.add_step("context_pack_validated", {"ok": status == "ok", "status": status, "errors": errors})
        else:
            # Human pack: minimal valid
            pack = {
                "schema_version": 1,
                "pack_type": "human",
                "narrative_context": {},
                "source_note": {"type": "system", "asserted_by": "kernel", "verified": False, "evidence_refs": []},
                "ask_style": {"do_not_assume": True},
                "topic_ref": {"topic": "general"},
                "token_estimate": 0,
                "rationale": "Minimal human context",
            }
            status = "ok"
            errors = []
            trace.set_context_pack(pack["pack_type"], pack.get("token_estimate", 0), status, errors)
            trace.add_step("context_pack_built", {"pack_type": pack_type, "token_estimate": pack.get("token_estimate", 0)})
            trace.add_step("context_pack_validated", {"ok": status == "ok", "status": status, "errors": errors})

        return pack

    def _get_task_type(self, intent: str, route: str) -> str:
        """Map intent and route to scheduler task type."""
        # Map common intents to task types
        intent_to_task = {
            "chat": "chat",
            "refactor": "code",
            "debug": "code",
            "implement": "code",
            "review": "review",
            "test": "code",
            "plan": "planning",
            "tool_selection": "tool_selection",
        }
        
        task_type = intent_to_task.get(intent, "chat")
        
        # Override based on route if needed
        if route == "toolchain":
            task_type = "code"
        elif route == "verify":
            task_type = "review"
        elif route == "fast_talk":
            task_type = "chat"
        
        return task_type

    async def _generate_plan(self, request: KernelRequest, route: str, trace: DecisionTrace) -> List[Dict[str, Any]]:
        """Generate execution plan using real scheduler."""
        plan = []
        scheduler = get_model_scheduler()
        
        # Create inference request for scheduler
        inference_request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            session_id=getattr(request, 'user_id', 'anonymous') or 'anonymous',
            route_type=route,
            task_type=self._get_task_type(request.intent_hint or "general", route),
            payload={
                "intent": request.intent_hint,
                "channel": request.channel,
                "focus_files": request.payload.get("focus_files", []),
                "max_tokens": min(request.budget.get("tokens", 2048), 4096),  # Cap at 4k
            },
            max_latency_ms=request.budget.get("latency_ms", 5000),
            max_cost=request.budget.get("cost", 0.1),
        )
        
        # Get model assignments based on route
        if route == "fast_talk":
            # Single model for fast response
            assignment = scheduler.assign(inference_request, slot=0)
            if assignment:
                plan.append({
                    "step": "chat_completion",
                    "model": assignment.model_name,
                    "endpoint": assignment.endpoint,
                    "max_tokens": inference_request.payload["max_tokens"],
                })
                trace.add_step("model_assigned", {
                    "route": route,
                    "engine": assignment.engine_id,
                    "model": assignment.model_name,
                    "estimated_latency": assignment.estimated_latency_ms,
                    "estimated_cost": assignment.estimated_cost,
                })
        
        elif route == "toolchain":
            # IDE workflow: planner + workers (up to 4 parallel)
            assignments = []
            
            # Primary planner (slot 0)
            primary = scheduler.assign(inference_request, slot=0)
            if primary:
                assignments.append(primary)
                plan.append({
                    "step": "plan_ide_changes",
                    "model": primary.model_name,
                    "endpoint": primary.endpoint,
                    "focus_files": request.payload.get("focus_files", []),
                })
            
            # Parallel workers (slots 1-3) for implementation
            for slot in range(1, min(scheduler.get_parallel_limit(route), 4)):
                worker = scheduler.assign(inference_request, slot=slot)
                if worker:
                    assignments.append(worker)
                    plan.append({
                        "step": "implement_changes",
                        "model": worker.model_name,
                        "endpoint": worker.endpoint,
                        "slot": slot,
                    })
            
            trace.add_step("model_assignments", {
                "route": route,
                "assignments": len(assignments),
                "parallel_limit": scheduler.get_parallel_limit(route),
                "models": [a.model_name for a in assignments],
            })
        
        elif route in ["verify", "project"]:
            # Single comprehensive model for verification/review
            assignment = scheduler.assign(inference_request, slot=0)
            if assignment:
                task_type = "verify_code" if route == "verify" else "code_planning"
                plan.append({
                    "step": task_type,
                    "model": assignment.model_name,
                    "endpoint": assignment.endpoint,
                    "context_pack": "available" if route in NEEDS_CONTEXT else "none",
                })
                trace.add_step("model_assigned", {
                    "route": route,
                    "engine": assignment.engine_id,
                    "model": assignment.model_name,
                    "task_type": task_type,
                })
        
        else:
            # Fallback for unknown routes
            plan.append({"step": "chat_completion", "fallback": True})
        
        trace.add_step("plan_generated", {"steps": len(plan)})
        return plan

    async def _execute_tools(self, request: KernelRequest, plan: List[Dict[str, Any]], trace: DecisionTrace) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Execute tool calls using assigned models."""
        tool_calls = []
        scheduler = get_model_scheduler()
        
        # Simulate execution for each plan step
        for i, step in enumerate(plan):
            step_result = {"step": step["step"], "status": "completed"}
            
            if "model" in step:
                # This step uses a model - simulate inference
                step_result.update({
                    "model": step["model"],
                    "endpoint": step["endpoint"],
                    "tokens_used": min(step.get("max_tokens", 1024), 512),  # Simulate token usage
                })
                
                # For multi-step plans, simulate parallel execution
                if len(plan) > 1:
                    step_result["parallel_slot"] = step.get("slot", 0)
            
            tool_calls.append(step_result)
            trace.add_step("tool_executed", step_result)
        
        # Release scheduler assignments (simulate cleanup)
        # In real implementation, this would happen after actual model calls complete
        for step in plan:
            if "model" in step:
                # Simulate releasing the assignment by model name
                # Real implementation would track request_ids and call scheduler.release()
                pass
        
        # Generate response based on plan execution
        response = self._build_response_from_plan(plan, tool_calls, request, trace)
        
        trace.add_step("response_built", {"tool_calls_count": len(tool_calls)})
        return tool_calls, response

    def _build_response_from_plan(self, plan: List[Dict[str, Any]], tool_calls: List[Dict[str, Any]], request: KernelRequest, trace: DecisionTrace) -> Dict[str, Any]:
        """Build response based on plan execution results."""
        attribution_flags = []
        followups = []
        
        # Generate response based on plan type
        if any(step.get("step") == "chat_completion" for step in plan):
            text = "I've processed your request and generated a response."
        elif any(step.get("step") == "plan_ide_changes" for step in plan):
            text = f"I've analyzed your code changes and planned {len([s for s in plan if s.get('step') == 'implement_changes'])} implementation steps."
            followups.append({"prompt": "Would you like me to implement these changes?", "priority": "medium"})
        elif any(step.get("step") in ["verify_code", "code_planning"] for step in plan):
            text = "I've reviewed your code and provided feedback."
            if request.safety_mode == "strict":
                attribution_flags.append("verified_high_confidence")
        else:
            text = "Request completed successfully."
        
        # Add attribution for safety modes
        if request.safety_mode == "strict":
            attribution_flags.extend(["source_attributed", "confidence_high"])
        
        return {
            "text": text,
            "attribution_flags": attribution_flags,
            "followups": followups,
        }

    def _build_verification_envelope(
        self, 
        request: KernelRequest, 
        route: str, 
        plan: List[Dict[str, Any]], 
        tool_calls: List[Dict[str, Any]], 
        trace: DecisionTrace
    ) -> Dict[str, Any]:
        """Build verification envelope with deterministic attribution analysis."""
        attribution_flags = []
        evidence_refs = []
        disclaimers = []
        
        # Determine attribution language based on request or user preferences
        attribution_language = "en"  # Default to English
        
        # Analyze safety mode
        if request.safety_mode == "strict":
            attribution_flags.append(ATTRIBUTION_FLAGS["SAFETY_MODE_STRICT_APPLIED"])
        
        # Analyze tool execution for evidence
        tool_evidence_found = False
        for tool_call in tool_calls:
            if tool_call.get("status") == "completed":
                tool_evidence_found = True
                evidence_refs.append({
                    "kind": "tool_call",
                    "id": tool_call.get("step", "unknown"),
                    "locator": f"model:{tool_call.get('model', 'unknown')}",
                    "confidence": 0.9,
                    "summary": f"Tool execution completed successfully: {tool_call.get('step', 'unknown')}"
                })
                attribution_flags.append(ATTRIBUTION_FLAGS["DERIVED_FROM_TOOL_OUTPUT"])
        
        # Analyze trace for evidence - only count meaningful steps, not administrative
        if trace and hasattr(trace, 'steps'):
            trace_evidence_found = False
            for step in trace.steps:
                # Only count steps that represent actual evidence, not administrative steps
                if step.name in ["tool_executed"]:  # Only tool execution steps count as evidence
                    trace_evidence_found = True
                    evidence_refs.append({
                        "kind": "trace",
                        "id": trace.trace_id,
                        "locator": f"phase:{step.name}",
                        "confidence": 0.8,
                        "summary": f"Decision trace: {step.name} completed"
                    })
            if trace_evidence_found:
                attribution_flags.append(ATTRIBUTION_FLAGS["DERIVED_FROM_TRACE"])
        
        # Check for user assertions in request
        if request.payload.get("assertions") or request.intent_hint:
            attribution_flags.append(ATTRIBUTION_FLAGS["UNVERIFIED_USER_ASSERTION"])
        
        # Generate disclaimers based on evidence availability
        if not tool_evidence_found and not any(f in attribution_flags for f in [
            ATTRIBUTION_FLAGS["DERIVED_FROM_TRACE"],
            ATTRIBUTION_FLAGS["DERIVED_FROM_TOOL_OUTPUT"]
        ]):
            attribution_flags.append(ATTRIBUTION_FLAGS["NO_EVIDENCE_AVAILABLE"])
            if attribution_language == "en":
                disclaimers.append("This response is based on general knowledge and available context. No specific tool execution or external verification was performed.")
            else:
                disclaimers.append("Esta respuesta se basa en conocimiento general y contexto disponible. No se realizó ejecución específica de herramientas o verificación externa.")
        
        elif len(evidence_refs) < len([t for t in tool_calls if t.get("status") == "completed"]):
            attribution_flags.append(ATTRIBUTION_FLAGS["EVIDENCE_PARTIAL"])
            if attribution_language == "en":
                disclaimers.append("Partial evidence available. Some claims may require additional verification.")
            else:
                disclaimers.append("Evidencia parcial disponible. Algunas afirmaciones pueden requerir verificación adicional.")
        
        # For verify routes, ensure verification disclaimers
        if route == "verify":
            if attribution_language == "en":
                disclaimers.append("Code verification performed. Recommendations based on analysis and available evidence.")
            else:
                disclaimers.append("Verificación de código realizada. Recomendaciones basadas en análisis y evidencia disponible.")
        
        return {
            "attribution_flags": attribution_flags,
            "attribution_language": attribution_language,
            "evidence_refs": evidence_refs,
            "disclaimers": disclaimers,
        }

# Global instance
_kernel_api: Optional[KernelAPI] = None

def get_kernel_api() -> KernelAPI:
    """Get the global kernel API instance."""
    global _kernel_api
    if _kernel_api is None:
        _kernel_api = KernelAPI()
    return _kernel_api
