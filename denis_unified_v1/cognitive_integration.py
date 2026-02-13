"""Cognitive Event Bus for real-time NeuroLayer ↔ MentalLoop integration.

This module provides:
- Event emission when neurolayers process data
- Event routing to appropriate mental-loops
- Graph persistence for all cognitive events
- Feedback mechanisms for adaptation
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class NeuroLayerEventType(Enum):
    """Types of events emitted by neurolayers."""

    SENSORY_INPUT = "sensory_input"
    WORKING_UPDATE = "working_update"
    EPISODIC_ENCODE = "episodic_encode"
    PROCEDURAL_INVOKE = "procedural_invoke"
    SOCIAL_PROCESS = "social_process"
    IDENTITY_UPDATE = "identity_update"
    RELATIONAL_ANALYZE = "relational_analyze"
    METACOG_EVALUATE = "metacog_evaluate"


class MentalLoopEventType(Enum):
    """Types of events processed by mental-loops."""

    REFLECTION_TRIGGER = "reflection_trigger"
    META_REFLECTION_TRIGGER = "meta_reflection_trigger"
    PATTERN_DETECTED = "pattern_detected"
    CONSCIOUSNESS_EXPANDED = "consciousness_expanded"


class FeedbackType(Enum):
    """Types of feedback from mental-loops to neurolayers."""

    REINFORCEMENT = "reinforcement"
    INHIBITION = "inhibition"
    ADAPTATION = "adaptation"
    REORGANIZATION = "reorganization"


@dataclass
class CognitiveEvent:
    """Event representing cognitive processing between neurolayers and mental-loops."""

    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    source_neurolayer: Optional[str] = None
    target_mental_loop: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    processed: bool = False
    graph_recorded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source_neurolayer": self.source_neurolayer,
            "target_mental_loop": self.target_mental_loop,
            "data": self.data,
            "timestamp": self.timestamp,
            "processed": self.processed,
            "graph_recorded": self.graph_recorded,
        }


@dataclass
class NeuroMentalFeedback:
    """Feedback from mental-loop to neurolayer for adaptation."""

    id: str = field(default_factory=lambda: str(uuid4()))
    source_mental_loop: str = ""
    target_neurolayer: str = ""
    feedback_type: FeedbackType = FeedbackType.REINFORCEMENT
    intensity: float = 0.5
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    applied: bool = False


class CognitiveEventBus:
    """Event bus for real-time NeuroLayer ↔ MentalLoop communication.

    This is the core of the cognitive integration - it enables:
    - Neurolayers to emit events when they process data
    - Mental-loops to subscribe and react to events
    - Graph persistence of all cognitive interactions
    """

    # Mapping from neurolayers to their corresponding mental-loops
    NEUROLAYER_TO_MENTAL_LOOP: Dict[str, str] = {
        "L1_SENSORY": "reflection",
        "L2_WORKING": "reflection",
        "L3_EPISODIC": "pattern_recognition",
        "L5_PROCEDURAL": "meta_reflection",
        "L8_SOCIAL": "pattern_recognition",
        "L9_IDENTITY": "expansive_consciousness",
        "L10_RELATIONAL": "pattern_recognition",
        "L12_METACOG": "expansive_consciousness",
    }

    MENTAL_LOOP_TO_NEUROLAYERS: Dict[str, List[str]] = {
        "reflection": ["L1_SENSORY", "L2_WORKING"],
        "meta_reflection": ["L5_PROCEDURAL", "L12_METACOG"],
        "pattern_recognition": ["L3_EPISODIC", "L8_SOCIAL", "L10_RELATIONAL"],
        "expansive_consciousness": ["L9_IDENTITY", "L12_METACOG"],
    }

    def __init__(self, graph_writer=None):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_history: List[CognitiveEvent] = []
        self._max_history = 1000
        self._lock = threading.RLock()
        self._graph_writer = graph_writer
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        self._processor_task: Optional[asyncio.Task] = None

    def set_graph_writer(self, graph_writer):
        """Set the graph writer for persisting events."""
        self._graph_writer = graph_writer

    def subscribe(self, event_type: str, callback: Callable[[CognitiveEvent], None]):
        """Subscribe to events of a specific type."""
        with self._lock:
            self._subscribers[event_type].append(callback)
            logger.info(f"Subscriber added for event type: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from events."""
        with self._lock:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def emit(self, event: CognitiveEvent) -> CognitiveEvent:
        """Emit a cognitive event and notify subscribers."""
        with self._lock:
            # Determine target mental loop if not set
            if event.target_mental_loop and not event.target_mental_loop:
                if event.source_neurolayer in self.NEUROLAYER_TO_MENTAL_LOOP:
                    event.target_mental_loop = self.NEUROLAYER_TO_MENTAL_LOOP[
                        event.source_neurolayer
                    ]

            # Add to history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

        # Notify subscribers synchronously
        with self._lock:
            callbacks = list(self._subscribers.get(event.event_type, []))
            callbacks.extend(self._subscribers.get("*", []))  # Wildcard subscribers

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event subscriber: {e}")

        # Record in graph asynchronously
        self._record_in_graph(event)

        return event

    def emit_neurolayer_event(
        self, neurolayer: str, event_type: NeuroLayerEventType, data: Dict[str, Any]
    ) -> CognitiveEvent:
        """Emit an event from a neurolayer to its corresponding mental-loop."""
        mental_loop = self.NEUROLAYER_TO_MENTAL_LOOP.get(neurolayer, "reflection")

        event = CognitiveEvent(
            event_type=event_type.value,
            source_neurolayer=neurolayer,
            target_mental_loop=mental_loop,
            data=data,
        )

        return self.emit(event)

    def _record_in_graph(self, event: CognitiveEvent):
        """Record event in Neo4j graph."""
        if not self._graph_writer or event.graph_recorded:
            return

        try:
            if event.source_neurolayer and event.target_mental_loop:
                success = self._graph_writer.record_neurolayer_mental_loop(
                    neurolayer=event.source_neurolayer,
                    mental_loop=event.target_mental_loop,
                    feedback_type="event_processed",
                )
                if success:
                    event.graph_recorded = True
                    logger.debug(f"Event {event.id} recorded in graph")
        except Exception as e:
            logger.warning(f"Failed to record event in graph: {e}")

    def get_event_history(
        self,
        neurolayer: Optional[str] = None,
        mental_loop: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get event history with optional filtering."""
        with self._lock:
            events = self._event_history

        if neurolayer:
            events = [e for e in events if e.source_neurolayer == neurolayer]
        if mental_loop:
            events = [e for e in events if e.target_mental_loop == mental_loop]

        return [e.to_dict() for e in events[-limit:]]

    def get_active_integrations(self) -> List[Dict[str, Any]]:
        """Get currently active neuro-mental integrations."""
        with self._lock:
            active = set()
            for event in self._event_history[-100:]:  # Last 100 events
                if event.source_neurolayer and event.target_mental_loop:
                    active.add((event.source_neurolayer, event.target_mental_loop))

        return [
            {"neurolayer": nl, "mental_loop": ml, "status": "active"}
            for nl, ml in active
        ]


class NeuroMentalIntegrationService:
    """Service that orchestrates real NeuroLayer ↔ MentalLoop integration.

    This service:
    - Processes cognitive events through mental-loops
    - Generates feedback from mental-loops to neurolayers
    - Records all interactions in the graph
    - Provides adaptive learning based on patterns
    """

    def __init__(
        self, event_bus: Optional[CognitiveEventBus] = None, graph_writer=None
    ):
        self._event_bus = event_bus or CognitiveEventBus()
        self._graph_writer = graph_writer
        self._event_bus.set_graph_writer(graph_writer)

        self._pending_feedback: List[NeuroMentalFeedback] = []
        self._feedback_lock = threading.Lock()

        # Register default mental-loop processors
        self._register_default_processors()

    def _register_default_processors(self):
        """Register default event processors for mental-loops."""
        self._event_bus.subscribe("sensory_input", self._process_reflection)
        self._event_bus.subscribe("working_update", self._process_reflection)
        self._event_bus.subscribe("episodic_encode", self._process_pattern_recognition)
        self._event_bus.subscribe("social_process", self._process_pattern_recognition)
        self._event_bus.subscribe(
            "relational_analyze", self._process_pattern_recognition
        )
        self._event_bus.subscribe("procedural_invoke", self._process_meta_reflection)
        self._event_bus.subscribe(
            "identity_update", self._process_expansive_consciousness
        )
        self._event_bus.subscribe(
            "metacog_evaluate", self._process_expansive_consciousness
        )

    def _process_reflection(self, event: CognitiveEvent):
        """Process reflection mental-loop."""
        logger.debug(f"Processing reflection for event from {event.source_neurolayer}")

        # Generate feedback for reinforcement
        feedback = NeuroMentalFeedback(
            source_mental_loop="reflection",
            target_neurolayer=event.source_neurolayer,
            feedback_type=FeedbackType.REINFORCEMENT,
            intensity=0.7,
            data={"event_id": event.id, "reflection_completed": True},
        )
        self._add_feedback(feedback)

    def _process_meta_reflection(self, event: CognitiveEvent):
        """Process meta-reflection mental-loop."""
        logger.debug(
            f"Processing meta-reflection for event from {event.source_neurolayer}"
        )

        feedback = NeuroMentalFeedback(
            source_mental_loop="meta_reflection",
            target_neurolayer=event.source_neurolayer,
            feedback_type=FeedbackType.ADAPTATION,
            intensity=0.6,
            data={"event_id": event.id, "strategy_adjusted": True},
        )
        self._add_feedback(feedback)

    def _process_pattern_recognition(self, event: CognitiveEvent):
        """Process pattern recognition mental-loop."""
        logger.debug(
            f"Processing pattern recognition for event from {event.source_neurolayer}"
        )

        feedback = NeuroMentalFeedback(
            source_mental_loop="pattern_recognition",
            target_neurolayer=event.source_neurolayer,
            feedback_type=FeedbackType.REINFORCEMENT,
            intensity=0.8,
            data={"event_id": event.id, "pattern_identified": True},
        )
        self._add_feedback(feedback)

    def _process_expansive_consciousness(self, event: CognitiveEvent):
        """Process expansive consciousness mental-loop."""
        logger.debug(
            f"Processing expansive consciousness for event from {event.source_neurolayer}"
        )

        feedback = NeuroMentalFeedback(
            source_mental_loop="expansive_consciousness",
            target_neurolayer=event.source_neurolayer,
            feedback_type=FeedbackType.REORGANIZATION,
            intensity=0.5,
            data={"event_id": event.id, "consciousness_expanded": True},
        )
        self._add_feedback(feedback)

    def _add_feedback(self, feedback: NeuroMentalFeedback):
        """Add feedback to pending queue."""
        with self._feedback_lock:
            self._pending_feedback.append(feedback)
            # Keep only last 100
            if len(self._pending_feedback) > 100:
                self._pending_feedback.pop(0)

    def emit_cognitive_event(
        self, neurolayer: str, event_type: str, data: Dict[str, Any]
    ) -> CognitiveEvent:
        """Emit a cognitive event from a neurolayer."""
        event = self._event_bus.emit_neurolayer_event(
            neurolayer=neurolayer, event_type=NeuroLayerEventType(event_type), data=data
        )

        # Record in graph explicitly
        if self._graph_writer and event.source_neurolayer and event.target_mental_loop:
            self._graph_writer.record_neurolayer_mental_loop(
                neurolayer=event.source_neurolayer,
                mental_loop=event.target_mental_loop,
                feedback_type="event_emitted",
            )

        return event

    def get_pending_feedback(
        self, neurolayer: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get pending feedback for neurolayers."""
        with self._feedback_lock:
            feedback_list = self._pending_feedback

        if neurolayer:
            feedback_list = [
                f for f in feedback_list if f.target_neurolayer == neurolayer
            ]

        return [
            {
                "id": f.id,
                "source_mental_loop": f.source_mental_loop,
                "target_neurolayer": f.target_neurolayer,
                "feedback_type": f.feedback_type.value,
                "intensity": f.intensity,
                "data": f.data,
                "timestamp": f.timestamp,
                "applied": f.applied,
            }
            for f in feedback_list
        ]

    def apply_feedback(self, feedback_id: str) -> bool:
        """Mark feedback as applied."""
        with self._feedback_lock:
            for f in self._pending_feedback:
                if f.id == feedback_id:
                    f.applied = True
                    return True
        return False

    def get_integration_status(self) -> Dict[str, Any]:
        """Get current integration status."""
        active_integrations = self._event_bus.get_active_integrations()

        with self._feedback_lock:
            pending_count = len([f for f in self._pending_feedback if not f.applied])

        return {
            "status": "integrated",
            "active_integrations": active_integrations,
            "pending_feedback": pending_count,
            "total_events": len(self._event_bus._event_history),
            "neurolayer_to_mental_loop": CognitiveEventBus.NEUROLAYER_TO_MENTAL_LOOP,
            "mental_loop_to_neurolayers": CognitiveEventBus.MENTAL_LOOP_TO_NEUROLAYERS,
        }

    def get_event_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get cognitive event history."""
        return self._event_bus.get_event_history(limit=limit)


# Global instance
_cognitive_event_bus: Optional[CognitiveEventBus] = None
_integration_service: Optional[NeuroMentalIntegrationService] = None
_service_lock = threading.Lock()


def get_cognitive_event_bus() -> CognitiveEventBus:
    """Get global CognitiveEventBus instance."""
    global _cognitive_event_bus
    if _cognitive_event_bus is None:
        with _service_lock:
            if _cognitive_event_bus is None:
                _cognitive_event_bus = CognitiveEventBus()
    return _cognitive_event_bus


def get_integration_service(graph_writer=None) -> NeuroMentalIntegrationService:
    """Get global NeuroMentalIntegrationService instance."""
    global _integration_service
    if _integration_service is None:
        with _service_lock:
            if _integration_service is None:
                _integration_service = NeuroMentalIntegrationService(
                    event_bus=get_cognitive_event_bus(), graph_writer=graph_writer
                )
    elif graph_writer and _integration_service._graph_writer is None:
        _integration_service._graph_writer = graph_writer
        _integration_service._event_bus.set_graph_writer(graph_writer)
    return _integration_service


def reset_integration_service():
    """Reset the global integration service (for testing)."""
    global _cognitive_event_bus, _integration_service
    with _service_lock:
        _cognitive_event_bus = None
        _integration_service = None
