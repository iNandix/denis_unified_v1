"""
Propagation Engine - Motor de propagación cuántica semántica.

Implementa metáfora de propagación basada en interferencia:
- SuperpositionState: múltiples candidatos simultáneamente
- InterferenceCalculator: refuerzo/cancelación entre candidatos
- CoherenceDecay: pérdida de coherencia por distancia
- CollapseMechanism: convergencia a respuesta final

Depende de:
- quantum/entity_augmentation.py (propiedades existentes)
- metacognitive/hooks.py (TICKET F0)

Contratos aplicados:
- L3.META.ONLY_OBSERVE_L0
- L3.META.NEVER_BLOCK
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import math
import json
from collections import defaultdict

from denis_unified_v1.metacognitive.hooks import (
    get_hooks,
    emit_reflection,
    metacognitive_trace,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class QuantumCandidate:
    """Candidato en superposición."""

    id: str
    content: str
    amplitude: float
    phase: float
    source: str
    relevance_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuperpositionState:
    """Estado de superposición con múltiples candidatos."""

    query_id: str
    candidates: list[QuantumCandidate]
    total_probability: float
    coherence_score: float
    active_dimensions: list[str]
    timestamp_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_amplitudes(self) -> list[float]:
        return [c.amplitude for c in self.candidates]

    def get_phases(self) -> list[float]:
        return [c.phase for c in self.candidates]

    def get_probabilities(self) -> list[float]:
        total = sum(c.amplitude**2 for c in self.candidates)
        if total == 0:
            return [1.0 / len(self.candidates)] * len(self.candidates)
        return [(c.amplitude**2) / total for c in self.candidates]


@dataclass
class PropagationResult:
    """Resultado de la propagación."""

    collapsed_id: str
    collapsed_content: str
    confidence: float
    coherence_at_collapse: float
    iterations: int
    timestamp_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)


class InterferenceCalculator:
    """Calcula interferencia constructiva/destructiva entre candidatos."""

    def __init__(self):
        self._coupling_strength: float = 0.1

    def set_coupling_strength(self, strength: float) -> None:
        self._coupling_strength = max(0.0, min(1.0, strength))

    def calculate_interference(
        self,
        candidate_a: QuantumCandidate,
        candidate_b: QuantumCandidate,
        similarity: float,
    ) -> float:
        phase_diff = candidate_a.phase - candidate_b.phase

        interference = math.cos(phase_diff) * similarity

        coupling = self._coupling_strength * interference

        return coupling

    def propagate_amplitudes(
        self,
        state: SuperpositionState,
        similarity_matrix: list[list[float]],
    ) -> SuperpositionState:
        new_amplitudes = []
        n = len(state.candidates)

        for i, candidate in enumerate(state.candidates):
            original_amplitude = candidate.amplitude

            interference_sum = 0.0
            for j, other in enumerate(state.candidates):
                if i != j:
                    interference = self.calculate_interference(
                        candidate, other, similarity_matrix[i][j]
                    )
                    interference_sum += interference * other.amplitude

            new_amplitude = original_amplitude + interference_sum

            new_amplitude = max(0.0, min(1.0, new_amplitude))
            new_amplitudes.append(new_amplitude)

        new_candidates = []
        for i, candidate in enumerate(state.candidates):
            new_candidates.append(
                QuantumCandidate(
                    id=candidate.id,
                    content=candidate.content,
                    amplitude=new_amplitudes[i],
                    phase=candidate.phase,
                    source=candidate.source,
                    relevance_score=candidate.relevance_score,
                    metadata={
                        **candidate.metadata,
                        "iteration": state.metadata.get("iteration", 0),
                    },
                )
            )

        return SuperpositionState(
            query_id=state.query_id,
            candidates=new_candidates,
            total_probability=sum(c.amplitude**2 for c in new_candidates),
            coherence_score=self._calculate_coherence(new_amplitudes),
            active_dimensions=state.active_dimensions,
            timestamp_utc=_utc_now(),
            metadata={
                **state.metadata,
                "iteration": state.metadata.get("iteration", 0) + 1,
            },
        )

    def _calculate_coherence(self, amplitudes: list[float]) -> float:
        if not amplitudes:
            return 0.0

        mean_amp = sum(amplitudes) / len(amplitudes)
        if mean_amp == 0:
            return 0.0

        variance = sum((a - mean_amp) ** 2 for a in amplitudes) / len(amplitudes)
        std_dev = math.sqrt(variance)

        if mean_amp == 0:
            return 0.0

        coherence = 1.0 - (std_dev / mean_amp) if mean_amp > 0 else 0.0

        return max(0.0, min(1.0, coherence))


class CoherenceDecay:
    """Modela pérdida de coherencia por tiempo/distancia."""

    def __init__(self):
        self._decay_rate: float = 0.01
        self._time_scale: float = 1.0

    def set_decay_rate(self, rate: float) -> None:
        self._decay_rate = max(0.0, min(1.0, rate))

    def apply_decay(
        self,
        state: SuperpositionState,
        time_elapsed_ms: float,
    ) -> SuperpositionState:
        decay_factor = math.exp(
            -self._decay_rate * (time_elapsed_ms / 1000.0) * self._time_scale
        )

        new_candidates = []
        for candidate in state.candidates:
            new_candidates.append(
                QuantumCandidate(
                    id=candidate.id,
                    content=candidate.content,
                    amplitude=candidate.amplitude * decay_factor,
                    phase=candidate.phase,
                    source=candidate.source,
                    relevance_score=candidate.relevance_score * decay_factor,
                    metadata={**candidate.metadata, "decay_applied": True},
                )
            )

        return SuperpositionState(
            query_id=state.query_id,
            candidates=new_candidates,
            total_probability=sum(c.amplitude**2 for c in new_candidates),
            coherence_score=state.coherence_score * decay_factor,
            active_dimensions=state.active_dimensions,
            timestamp_utc=_utc_now(),
            metadata={**state.metadata, "decay_factor": decay_factor},
        )

    def apply_distance_decay(
        self,
        state: SuperpositionState,
        distances: list[float],
    ) -> SuperpositionState:
        new_candidates = []
        for i, candidate in enumerate(state.candidates):
            distance = distances[i] if i < len(distances) else 1.0
            decay = math.exp(-distance * self._decay_rate)

            new_candidates.append(
                QuantumCandidate(
                    id=candidate.id,
                    content=candidate.content,
                    amplitude=candidate.amplitude * decay,
                    phase=candidate.phase,
                    source=candidate.source,
                    relevance_score=candidate.relevance_score * decay,
                    metadata={**candidate.metadata, "distance_decay": decay},
                )
            )

        return SuperpositionState(
            query_id=state.query_id,
            candidates=new_candidates,
            total_probability=sum(c.amplitude**2 for c in new_candidates),
            coherence_score=self._calculate_coherence(
                [c.amplitude for c in new_candidates]
            ),
            active_dimensions=state.active_dimensions,
            timestamp_utc=_utc_now(),
            metadata={**state.metadata, "type": "distance_decay"},
        )

    def _calculate_coherence(self, amplitudes: list[float]) -> float:
        if not amplitudes:
            return 0.0
        mean_amp = sum(amplitudes) / len(amplitudes)
        if mean_amp == 0:
            return 0.0
        variance = sum((a - mean_amp) ** 2 for a in amplitudes) / len(amplitudes)
        std_dev = math.sqrt(variance)
        return max(0.0, min(1.0, 1.0 - (std_dev / mean_amp)))


class CollapseMechanism:
    """Convierte superposición en estado colapsado (decisión final)."""

    def __init__(self):
        self._coherence_threshold: float = 0.7
        self._max_iterations: int = 100

    def set_coherence_threshold(self, threshold: float) -> None:
        self._coherence_threshold = max(0.0, min(1.0, threshold))

    def set_max_iterations(self, max_iter: int) -> None:
        self._max_iterations = max(1, max_iter)

    def should_collapse(
        self,
        state: SuperpositionState,
        iteration: int,
    ) -> tuple[bool, str]:
        if iteration >= self._max_iterations:
            return True, "max_iterations_reached"

        if state.coherence_score >= self._coherence_threshold:
            return True, "coherence_threshold_met"

        if len(state.candidates) == 1:
            return True, "single_candidate"

        probs = state.get_probabilities()
        max_prob = max(probs)
        if max_prob > 0.9:
            return True, "dominant_candidate"

        return False, "not_ready"

    def collapse(
        self,
        state: SuperpositionState,
        iteration: int,
    ) -> PropagationResult:
        probs = state.get_probabilities()
        max_idx = probs.index(max(probs))
        winner = state.candidates[max_idx]

        confidence = probs[max_idx]

        emit_reflection(
            reflection_type="collapse",
            target=state.query_id,
            finding=f"Collapsed to {winner.id} with confidence {confidence:.3f}",
            confidence=confidence,
            recommendation=f"Iterations: {iteration}, Coherence: {state.coherence_score:.3f}",
        )

        return PropagationResult(
            collapsed_id=winner.id,
            collapsed_content=winner.content,
            confidence=confidence,
            coherence_at_collapse=state.coherence_score,
            iterations=iteration,
            timestamp_utc=_utc_now(),
            metadata={
                "winner_amplitude": winner.amplitude,
                "winner_phase": winner.phase,
                "winner_relevance": winner.relevance_score,
                "total_candidates": len(state.candidates),
                "collapse_reason": self.should_collapse(state, iteration)[1],
            },
        )


class SimilarityCalculator:
    """Calcula similaridad entre candidatos."""

    def __init__(self):
        self._default_similarity: float = 0.0

    def set_default_similarity(self, sim: float) -> None:
        self._default_similarity = max(0.0, min(1.0, sim))

    def calculate_similarity(
        self,
        candidate_a: QuantumCandidate,
        candidate_b: QuantumCandidate,
    ) -> float:
        sim = self._default_similarity

        if candidate_a.source == candidate_b.source:
            sim += 0.3

        relevance_diff = abs(candidate_a.relevance_score - candidate_b.relevance_score)
        sim += (1.0 - relevance_diff) * 0.2

        if (
            "semantic_hash" in candidate_a.metadata
            and "semantic_hash" in candidate_b.metadata
        ):
            if (
                candidate_a.metadata["semantic_hash"]
                == candidate_b.metadata["semantic_hash"]
            ):
                sim += 0.3

        return min(1.0, sim)

    def build_similarity_matrix(
        self,
        candidates: list[QuantumCandidate],
    ) -> list[list[float]]:
        n = len(candidates)
        matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i, n):
                if i == j:
                    matrix[i][j] = 1.0
                else:
                    sim = self.calculate_similarity(candidates[i], candidates[j])
                    matrix[i][j] = sim
                    matrix[j][i] = sim

        return matrix


class PropagationEngine:
    """Motor principal de propagación cuántica semántica."""

    def __init__(self):
        self._hooks = get_hooks()
        self._interference = InterferenceCalculator()
        self._decay = CoherenceDecay()
        self._collapse = CollapseMechanism()
        self._similarity = SimilarityCalculator()

        self._max_iterations = 50
        self._coherence_threshold = 0.8
        self._decay_rate = 0.01
        self._coupling_strength = 0.1

        self._total_propagations = 0
        self._total_iterations = 0

    def configure(
        self,
        max_iterations: int | None = None,
        coherence_threshold: float | None = None,
        decay_rate: float | None = None,
        coupling_strength: float | None = None,
    ) -> None:
        if max_iterations is not None:
            self._max_iterations = max_iterations
            self._collapse.set_max_iterations(max_iterations)

        if coherence_threshold is not None:
            self._coherence_threshold = coherence_threshold
            self._collapse.set_coherence_threshold(coherence_threshold)

        if decay_rate is not None:
            self._decay_rate = decay_rate
            self._decay.set_decay_rate(decay_rate)

        if coupling_strength is not None:
            self._coupling_strength = coupling_strength
            self._interference.set_coupling_strength(coupling_strength)

    @metacognitive_trace("propagation_engine")
    def propagate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        active_dimensions: list[str] | None = None,
    ) -> PropagationResult:
        self._total_propagations += 1

        if not candidates:
            return PropagationResult(
                collapsed_id="",
                collapsed_content="",
                confidence=0.0,
                coherence_at_collapse=0.0,
                iterations=0,
                timestamp_utc=_utc_now(),
                metadata={"error": "no_candidates"},
            )

        quantum_candidates = []
        for i, c in enumerate(candidates):
            quantum_candidates.append(
                QuantumCandidate(
                    id=c.get("id", f"candidate_{i}"),
                    content=c.get("content", c.get("text", str(c))),
                    amplitude=c.get("amplitude", 1.0),
                    phase=c.get("phase", 0.0),
                    source=c.get("source", "unknown"),
                    relevance_score=c.get("relevance_score", 0.5),
                    metadata=c.get("metadata", {}),
                )
            )

        state = SuperpositionState(
            query_id=f"query_{_utc_now()[:19].replace(':', '')}",
            candidates=quantum_candidates,
            total_probability=sum(c.amplitude**2 for c in quantum_candidates),
            coherence_score=self._calculate_initial_coherence(quantum_candidates),
            active_dimensions=active_dimensions or ["semantic"],
            timestamp_utc=_utc_now(),
            metadata={"query": query},
        )

        similarity_matrix = self._similarity.build_similarity_matrix(quantum_candidates)

        iteration = 0
        while True:
            ready, reason = self._collapse.should_collapse(state, iteration)

            emit_reflection(
                reflection_type="propagation_iteration",
                target=state.query_id,
                finding=f"Iteration {iteration}: coherence={state.coherence_score:.3f}, reason={reason}",
                confidence=state.coherence_score,
            )

            if ready:
                break

            if iteration >= self._max_iterations:
                emit_reflection(
                    reflection_type="propagation_timeout",
                    target=state.query_id,
                    finding=f"Max iterations reached: {iteration}",
                    confidence=state.coherence_score,
                )
                break

            state = self._interference.propagate_amplitudes(state, similarity_matrix)
            state = self._decay.apply_decay(state, 10.0)

            iteration += 1

        self._total_iterations += iteration

        result = self._collapse.collapse(state, iteration)

        emit_reflection(
            reflection_type="propagation_complete",
            target=state.query_id,
            finding=f"Propagated in {iteration} iterations",
            confidence=result.confidence,
            recommendation=f"Collapsed to: {result.collapsed_id}",
        )

        return result

    def _calculate_initial_coherence(self, candidates: list[QuantumCandidate]) -> float:
        if not candidates:
            return 0.0
        amplitudes = [c.amplitude for c in candidates]
        mean_amp = sum(amplitudes) / len(amplitudes)
        if mean_amp == 0:
            return 0.0
        variance = sum((a - mean_amp) ** 2 for a in amplitudes) / len(amplitudes)
        std_dev = math.sqrt(variance)
        return max(0.0, min(1.0, 1.0 - (std_dev / mean_amp)))

    def get_stats(self) -> dict[str, Any]:
        avg_iterations = self._total_iterations / max(1, self._total_propagations)
        return {
            "total_propagations": self._total_propagations,
            "total_iterations": self._total_iterations,
            "avg_iterations": round(avg_iterations, 2),
            "config": {
                "max_iterations": self._max_iterations,
                "coherence_threshold": self._coherence_threshold,
                "decay_rate": self._decay_rate,
                "coupling_strength": self._coupling_strength,
            },
        }


def create_propagation_engine() -> PropagationEngine:
    return PropagationEngine()


if __name__ == "__main__":
    import json

    print("=== PROPAGATION ENGINE ===")
    engine = create_propagation_engine()
    print(json.dumps(engine.get_stats(), indent=2))

    print("\n=== PROPAGATE ===")
    candidates = [
        {
            "id": "cand_1",
            "content": "Python function implementation",
            "amplitude": 0.9,
            "phase": 0.0,
            "source": "code_memory",
            "relevance_score": 0.85,
            "metadata": {"semantic_hash": "abc123"},
        },
        {
            "id": "cand_2",
            "content": "Write Python code for fibonacci",
            "amplitude": 0.8,
            "phase": 0.5,
            "source": "search_results",
            "relevance_score": 0.75,
            "metadata": {"semantic_hash": "def456"},
        },
        {
            "id": "cand_3",
            "content": "Python script example",
            "amplitude": 0.7,
            "phase": 1.0,
            "source": "documentation",
            "relevance_score": 0.65,
            "metadata": {"semantic_hash": "ghi789"},
        },
    ]

    result = engine.propagate(
        query="write python fibonacci function",
        candidates=candidates,
        active_dimensions=["semantic", "syntax"],
    )

    print("Result:")
    print(
        json.dumps(
            {
                "collapsed_id": result.collapsed_id,
                "collapsed_content": result.collapsed_content,
                "confidence": round(result.confidence, 3),
                "coherence": round(result.coherence_at_collapse, 3),
                "iterations": result.iterations,
            },
            indent=2,
            sort_keys=True,
        )
    )

    print("\n=== STATS ===")
    print(json.dumps(engine.get_stats(), indent=2))
