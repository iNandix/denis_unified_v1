"""Unified cortex interface over existing integrations (incremental wrapper)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, List

from denis_unified_v1.cortex.metacognitive_perception import PerceptionReflection, AttentionMechanism


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(event: str, **payload: Any) -> None:
    record = {"ts_utc": _utc_now(), "event": event, **payload}
    print(json.dumps(record, sort_keys=True))


@dataclass
class WorldEntity:
    entity_id: str
    category: str
    source: str
    state: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now)


class BaseAdapter(ABC):
    """Adapter contract used by cortex wrappers."""

    name: str = "base"

    @abstractmethod
    async def perceive(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def act(self, entity_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def subscribe(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "not_supported",
            "adapter": self.name,
            "entity_id": entity_id,
        }


class CortexWorldInterface:
    """Orchestrates adapters without replacing existing legacy flows."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._entities: dict[str, WorldEntity] = {}
        self.perception_reflection = PerceptionReflection()
        self.attention_mechanism = AttentionMechanism()

    def register_adapter(self, source: str, adapter: BaseAdapter) -> None:
        self._adapters[source] = adapter
        _log("cortex_adapter_registered", source=source, adapter=adapter.name)

    def register_entity(self, entity: WorldEntity) -> None:
        self._entities[entity.entity_id] = entity
        _log(
            "cortex_entity_registered",
            entity_id=entity.entity_id,
            source=entity.source,
            category=entity.category,
        )

    def get_entity(self, entity_id: str) -> WorldEntity | None:
        return self._entities.get(entity_id)

    async def perceive_multiple(self, entity_ids: List[str]) -> dict[str, Any]:
        """Percibe múltiples entidades con metacognición."""
        # Percepción base
        entities = []
        for entity_id in entity_ids:
            result = await self.perceive(entity_id)
            if result.get("status") == "ok":
                entity = self.get_entity(entity_id)
                if entity:
                    entities.append({
                        "name": entity_id,
                        "type": entity.category,
                        "status": result.get("state", {}).get("status", "unknown"),
                        "last_updated": entity.updated_at,
                    })
        
        perception = {"entities": entities}
        
        # Reflexión metacognitiva (NUEVO)
        reflection = self.perception_reflection.reflect(perception)
        
        # Priorización de atención (NUEVO)
        prioritized = self.attention_mechanism.prioritize(
            perception.get("entities", []),
            reflection
        )
        
        return {
            **perception,
            "metacognition": reflection,
            "prioritized_entities": prioritized,
        }

    async def perceive(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return {"status": "error", "error": f"unknown_entity:{entity_id}"}

        adapter = self._adapters.get(entity.source)
        if adapter is None:
            return {"status": "error", "error": f"unknown_source:{entity.source}"}

        result = await adapter.perceive(entity_id=entity_id, **kwargs)
        if result.get("status") == "ok":
            entity.state = result.get("state", {})
            entity.updated_at = _utc_now()
        return result

    async def act(self, entity_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return {"status": "error", "error": f"unknown_entity:{entity_id}"}

        adapter = self._adapters.get(entity.source)
        if adapter is None:
            return {"status": "error", "error": f"unknown_source:{entity.source}"}

        return await adapter.act(entity_id=entity_id, action=action, **kwargs)

