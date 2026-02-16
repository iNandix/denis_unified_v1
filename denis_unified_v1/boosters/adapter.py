"""Adapter - Ejecuta tareas con boosters.

Base adapters para diferentes tipos de boosters.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any
from abc import ABC, abstractmethod

from denis_unified_v1.boosters.models import Adapter, BoosterSpec

logger = logging.getLogger(__name__)


class BaseAdapter(Adapter):
    """Base adapter con lógica común."""

    async def execute(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Ejecuta tarea con booster."""
        if not self.is_available(booster):
            raise Exception(f"Booster {booster.id} not available")

        try:
            return await self._execute_task(task, booster)
        except Exception as e:
            logger.error(f"Adapter execution failed for {booster.id}: {e}")
            raise

    @abstractmethod
    async def _execute_task(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Implementación específica de ejecución."""
        pass

    def is_available(self, booster: BoosterSpec) -> bool:
        """Verifica disponibilidad básica."""
        return booster.active and booster.health.get("reliability", 0) > 0.5


class HFAdapter(BaseAdapter):
    """Adapter para Hugging Face Spaces."""

    async def _execute_task(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Ejecuta en HF Space (mock)."""
        # TODO: Real HF API call
        await asyncio.sleep(0.1)  # Simulate latency

        if task.get("type") == "inference":
            return {
                "response": f"HF response for: {task.get('prompt', '')}",
                "booster_used": booster.id,
                "latency_ms": booster.latency.get("p50_ms", 200)
            }
        else:
            raise Exception("Unsupported task type")

    def is_available(self, booster: BoosterSpec) -> bool:
        """Check HF Space availability."""
        # TODO: Ping HF Space
        return super().is_available(booster)


class GPUAdapter(BaseAdapter):
    """Adapter para GPUs ociosas."""

    async def _execute_task(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Ejecuta en GPU (mock)."""
        # TODO: Real GPU API call
        await asyncio.sleep(0.05)  # Simulate fast GPU

        if "gpu" in task.get("requirements", []):
            return {
                "response": f"GPU accelerated result for: {task.get('data', '')}",
                "booster_used": booster.id,
                "latency_ms": booster.latency.get("p50_ms", 50)
            }
        else:
            raise Exception("Task not suitable for GPU")

    def is_available(self, booster: BoosterSpec) -> bool:
        """Check GPU availability."""
        # TODO: Check GPU status
        return super().is_available(booster)


class LocalAdapter(BaseAdapter):
    """Adapter para recursos locales (fallback)."""

    async def _execute_task(self, task: Dict[str, Any], booster: BoosterSpec) -> Dict[str, Any]:
        """Ejecuta localmente."""
        # Simulate local execution
        await asyncio.sleep(0.02)

        return {
            "response": f"Local response for: {task.get('prompt', '')}",
            "booster_used": booster.id,
            "latency_ms": booster.latency.get("p50_ms", 20)
        }

    def is_available(self, booster: BoosterSpec) -> bool:
        """Local always available."""
        return True


# Adapter factory
ADAPTER_CLASSES = {
    "HFAdapter": HFAdapter,
    "GPUAdapter": GPUAdapter,
    "LocalAdapter": LocalAdapter,
    "GenericAdapter": BaseAdapter,
}

def create_adapter(adapter_class: str) -> Adapter:
    """Factory para crear adapter."""
    cls = ADAPTER_CLASSES.get(adapter_class)
    if not cls:
        logger.warning(f"Unknown adapter class {adapter_class}, using BaseAdapter")
        cls = BaseAdapter
    return cls()