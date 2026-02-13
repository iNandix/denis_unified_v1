"""Self-model with consciousness and API exposure."""

from __future__ import annotations

import time
from typing import Any, Dict, List


class SelfModel:
    """Model of self with consciousness and awareness."""

    def __init__(self):
        self.layers: Dict[str, Dict[str, Any]] = {
            "l0_tools": {},
            "l1_patterns": {},
            "l2_principles": {},
            "l3_metacognitive": {},
        }
        self.awareness_level: float = 0.0
        self.last_updated: float = time.time()

    def update_awareness(self, new_level: float) -> None:
        """Update self-awareness level."""
        self.awareness_level = min(1.0, max(0.0, new_level))
        self.last_updated = time.time()

    def add_layer_data(self, layer: str, data: Dict[str, Any]) -> None:
        """Add data to a specific layer."""
        if layer in self.layers:
            self.layers[layer].update(data)
            self.last_updated = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Get current self-model status."""
        return {
            "awareness_level": self.awareness_level,
            "layers": {k: len(v) for k, v in self.layers.items()},
            "last_updated": self.last_updated,
            "consciousness_state": "active" if self.awareness_level > 0.5 else "dormant",
        }

    def reflect(self) -> Dict[str, Any]:
        """Perform self-reflection."""
        total_entities = sum(len(v) for v in self.layers.values())
        coherence = self.awareness_level * (total_entities / max(1, total_entities))
        return {
            "reflection": f"Awareness at {self.awareness_level:.2f}, {total_entities} entities tracked",
            "coherence": coherence,
            "timestamp": time.time(),
        }


def build_self_model() -> SelfModel:
    """Build self-model instance."""
    return SelfModel()
