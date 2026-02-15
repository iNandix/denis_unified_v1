from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid
import json
import os
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class TraceStep:
    """Legacy trace step for backward compatibility."""
    name: str
    ts_ms: int
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ts_ms": self.ts_ms, "data": self.data}


@dataclass
class TraceSpan:
    """A span in the trace tree."""
    span_id: str
    name: str
    start_ts_ms: int
    parent_span_id: Optional[str] = None
    end_ts_ms: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> Optional[int]:
        if self.end_ts_ms is None:
            return None
        return self.end_ts_ms - self.start_ts_ms
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_ts_ms": self.start_ts_ms,
            "end_ts_ms": self.end_ts_ms,
            "duration_ms": self.duration_ms,
            "data": self.data,
        }


@dataclass
class TracePhase:
    """A phase in the request processing."""
    name: str
    span_id: str
    start_ts_ms: int
    end_ts_ms: Optional[int] = None
    budget_planned: Optional[int] = None
    budget_actual: Optional[int] = None
    
    @property
    def duration_ms(self) -> Optional[int]:
        if self.end_ts_ms is None:
            return None
        return self.end_ts_ms - self.start_ts_ms
    
    @property
    def budget_delta(self) -> Optional[int]:
        if self.budget_actual is None or self.budget_planned is None:
            return None
        return self.budget_actual - self.budget_planned
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "start_ts_ms": self.start_ts_ms,
            "end_ts_ms": self.end_ts_ms,
            "duration_ms": self.duration_ms,
            "budget_planned": self.budget_planned,
            "budget_actual": self.budget_actual,
            "budget_delta": self.budget_delta,
        }


@dataclass
class DecisionTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_ts_ms: int = field(default_factory=_now_ms)
    end_ts_ms: Optional[int] = None

    # Request context
    route_raw: Optional[str] = None
    route: Optional[str] = None
    reasoning_mode: Optional[str] = None
    safety_mode: Optional[str] = None
    model_selected: Optional[str] = None

    # Legacy steps (for backward compatibility)
    steps: List[TraceStep] = field(default_factory=list)

    # New structured tracing
    root_span_id: str = field(init=False)
    phases: List[TracePhase] = field(default_factory=list)
    spans: List[TraceSpan] = field(default_factory=list)
    current_phase_span_id: Optional[str] = None

    # Budget tracking
    budget_planned_total: Optional[int] = None
    budget_actual_total: Optional[int] = None

    # Context pack info
    context_pack_type: Optional[str] = None
    context_pack_token_estimate: Optional[int] = None
    context_pack_status: Optional[str] = None
    context_pack_errors: List[str] = field(default_factory=list)

    tool_calls_count: int = 0

    def __post_init__(self):
        """Initialize root span after trace_id is set."""
        self.root_span_id = f"{self.trace_id}_root"
        # Create root span
        root_span = TraceSpan(
            span_id=self.root_span_id,
            parent_span_id=None,  # Root has no parent
            name="request",
            start_ts_ms=self.start_ts_ms,
        )
        self.spans.append(root_span)

    def add_step(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.steps.append(TraceStep(name=name, ts_ms=_now_ms(), data=data or {}))

    def start_phase(self, phase_name: str, budget_planned: Optional[int] = None) -> str:
        """Start a new phase and return its span_id."""
        span_id = f"{self.trace_id}_{phase_name}_{len(self.phases)}"
        parent_span_id = self.root_span_id  # All phases hang from root
        
        phase = TracePhase(
            name=phase_name,
            span_id=span_id,
            start_ts_ms=_now_ms(),
            budget_planned=budget_planned,
        )
        self.phases.append(phase)
        
        # Create span
        span = TraceSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=phase_name,
            start_ts_ms=phase.start_ts_ms,
        )
        self.spans.append(span)
        
        # Update current phase for sub-spans
        self.current_phase_span_id = span_id
        
        return span_id

    def end_phase(self, span_id: str, budget_actual: Optional[int] = None) -> None:
        """End a phase by span_id."""
        end_ts = _now_ms()
        
        # Update phase
        for phase in self.phases:
            if phase.span_id == span_id:
                phase.end_ts_ms = end_ts
                if budget_actual is not None:
                    phase.budget_actual = budget_actual
                break
        
        # Update span
        for span in self.spans:
            if span.span_id == span_id:
                span.end_ts_ms = end_ts
                break
        
        # Reset current phase if this was the current one
        if self.current_phase_span_id == span_id:
            # Find parent span_id
            for span in self.spans:
                if span.span_id == span_id:
                    self.current_phase_span_id = span.parent_span_id
                    break

    def add_span(self, name: str, data: Optional[Dict[str, Any]] = None) -> str:
        """Add a sub-span under current phase."""
        span_id = f"{self.trace_id}_span_{len(self.spans)}"
        span = TraceSpan(
            span_id=span_id,
            parent_span_id=self.current_phase_span_id,
            name=name,
            start_ts_ms=_now_ms(),
            data=data or {},
        )
        self.spans.append(span)
        return span_id

    def end_span(self, span_id: str) -> None:
        """End a span."""
        for span in self.spans:
            if span.span_id == span_id:
                span.end_ts_ms = _now_ms()
                break

    def set_safety_mode(self, safety_mode: str) -> None:
        """Set the safety mode for this trace."""
        self.safety_mode = safety_mode

    def set_model_selected(self, model_name: str) -> None:
        """Set the selected model for this trace."""
        self.model_selected = model_name

    def set_context_pack(self, pack_type: str, token_estimate: int, status: str, errors: List[str]) -> None:
        """Set context pack information for this trace."""
        self.context_pack_type = pack_type
        self.context_pack_token_estimate = token_estimate
        self.context_pack_status = status
        self.context_pack_errors = errors

    def finalize(self, route: str = None, context_pack: Dict[str, Any] = None, plan: List[Dict[str, Any]] = None, tool_calls: List[Dict[str, Any]] = None, response_data: Dict[str, Any] = None) -> None:
        """Finalize the trace by calculating totals and marking as complete."""
        # Store final state information
        if route is not None:
            self.final_route = route
        if context_pack is not None:
            self.final_context_pack = context_pack
        if plan is not None:
            self.final_plan = plan
        if tool_calls is not None:
            self.final_tool_calls = tool_calls
        if response_data is not None:
            self.final_response_data = response_data
            
        self.update_budget_totals()
        self.end_ts_ms = _now_ms()
        self.duration_ms = self.end_ts_ms - self.start_ts_ms

    def set_route(self, route_raw: str, route: str, reasoning_mode: Optional[str] = None) -> None:
        """Set routing information (backward compatibility)."""
        self.route_raw = route_raw
        self.route = route
        self.reasoning_mode = reasoning_mode

    def update_budget_totals(self) -> None:
        """Calculate total planned and actual budgets from phases."""
        self.budget_planned_total = sum(
            phase.budget_planned or 0 for phase in self.phases
        )
        self.budget_actual_total = sum(
            phase.budget_actual or 0 for phase in self.phases
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to machine-readable dict for auditing."""
        if self.end_ts_ms is None:
            end = _now_ms()
        else:
            end = self.end_ts_ms

        # Ensure budget totals are calculated
        self.update_budget_totals()
        budget_delta_total = None
        if self.budget_planned_total is not None and self.budget_actual_total is not None:
            budget_delta_total = self.budget_actual_total - self.budget_planned_total

        return {
            "schema_version": "decision_trace_v1",
            "trace_id": self.trace_id,
            "start_ts_ms": self.start_ts_ms,
            "end_ts_ms": self.end_ts_ms,
            "duration_ms": end - self.start_ts_ms,

            # Routing / safety / model
            "route_raw": self.route_raw,
            "route": self.route,
            "reasoning_mode": self.reasoning_mode,
            "safety_mode": self.safety_mode,
            "model_selected": self.model_selected,

            # Context pack
            "context_pack": {
                "pack_type": self.context_pack_type,
                "token_estimate": self.context_pack_token_estimate,
                "status": self.context_pack_status,
                "errors": self.context_pack_errors,
            },

            # Budgets
            "budget": {
                "planned_total": self.budget_planned_total,
                "actual_total": self.budget_actual_total,
                "delta_total": budget_delta_total,
            },

            # Structured timings
            "phases": [p.to_dict() for p in self.phases],
            "spans": [s.to_dict() for s in self.spans],

            # Tools + legacy
            "tool_calls_count": self.tool_calls_count,
            "steps": [s.to_dict() for s in self.steps],
        }


class TraceSink(ABC):
    """Abstract base class for trace persistence."""
    
    @abstractmethod
    def emit(self, trace_dict: Dict[str, Any]) -> None:
        """Emit a complete trace."""
        pass
    
    @abstractmethod  
    def emit_span(self, span_dict: Dict[str, Any]) -> None:
        """Emit a span (for streaming)."""
        pass


class JsonlTraceSink(TraceSink):
    """JSONL-based trace sink for development and testing."""
    
    def __init__(self, file_path: str = "traces.jsonl"):
        self.file_path = file_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    def emit(self, trace_dict: Dict[str, Any]) -> None:
        """Append trace to JSONL file."""
        try:
            # Validate schema version for compatibility
            schema_version = trace_dict.get("schema_version")
            if schema_version and not self._is_supported_schema_version(schema_version):
                logger.warning(f"Unsupported schema version: {schema_version}, trace may be incomplete")
            
            with open(self.file_path, 'a', encoding='utf-8') as f:
                json.dump(trace_dict, f, default=str)
                f.write('\n')
        except Exception as e:
            logger.error(f"Failed to emit trace to file: {e}")
    
    def _is_supported_schema_version(self, version: str) -> bool:
        """Check if schema version is supported (backward compatible)."""
        supported_versions = {
            "decision_trace_v1",  # Current version
            # Add older versions as needed for rollback compatibility
        }
        return version in supported_versions
    
    def emit_span(self, span_dict: Dict[str, Any]) -> None:
        """Spans not persisted in JSONL sink (could be extended)."""
        pass


class NullTraceSink(TraceSink):
    """No-op sink for testing or when tracing is disabled."""
    
    def emit(self, trace_dict: Dict[str, Any]) -> None:
        pass
    
    def emit_span(self, span_dict: Dict[str, Any]) -> None:
        pass


# Schema version compatibility helpers
def migrate_trace_schema(trace_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate older schema versions to current format."""
    schema_version = trace_dict.get("schema_version")
    
    if schema_version == "decision_trace_v1":
        # Current version, no migration needed
        return trace_dict
    
    # Add migration logic for older versions here
    # For example:
    # if schema_version is None or schema_version == "decision_trace_v0":
    #     # Migrate v0 to v1
    #     trace_dict["schema_version"] = "decision_trace_v1"
    #     # Add missing fields with defaults
    #     trace_dict.setdefault("safety_mode", "default")
    #     trace_dict.setdefault("model_selected", None)
    #     # Transform budget structure if needed
    #     if "budget" not in trace_dict:
    #         trace_dict["budget"] = {
    #             "planned_total": trace_dict.pop("budget_planned_total", None),
    #             "actual_total": trace_dict.pop("budget_actual_total", None),
    #             "delta_total": None
    #         }
    
    # Default: assume current version
    if "schema_version" not in trace_dict:
        trace_dict["schema_version"] = "decision_trace_v1"
    
    return trace_dict


# Global trace sink instance
_trace_sink: Optional[TraceSink] = None
_trace_sample_rate: float = 1.0  # Sample all traces in dev


def get_trace_sink() -> TraceSink:
    """Get the global trace sink."""
    global _trace_sink
    if _trace_sink is None:
        # Default to JSONL sink in development
        if os.getenv("DENIS_TEST_MODE") == "1":
            _trace_sink = JsonlTraceSink("traces/test_traces.jsonl")
        else:
            _trace_sink = JsonlTraceSink("traces.jsonl")
    return _trace_sink


def set_trace_sink(sink: TraceSink) -> None:
    """Set the global trace sink."""
    global _trace_sink
    _trace_sink = sink


def set_trace_sample_rate(rate: float) -> None:
    """Set trace sampling rate (0.0 to 1.0)."""
    global _trace_sample_rate
    _trace_sample_rate = max(0.0, min(1.0, rate))


def should_sample_trace() -> bool:
    """Check if current trace should be sampled."""
    import random
    return random.random() < _trace_sample_rate


def emit_trace(trace: DecisionTrace) -> None:
    """Emit a trace if sampling allows."""
    if should_sample_trace():
        sink = get_trace_sink()
        sink.emit(trace.to_dict())
