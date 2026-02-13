"""Engine Catalog - fuente de verdad para engines de inferencia."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import os
import json


@dataclass
class EngineSpec:
    id: str
    provider: str
    model: str
    capabilities: List[str] = field(default_factory=list)
    safety_level: str = "medium"
    context_len: int = 4096
    cost: float = 0.0
    priority: int = 100
    timeout_ms: int = 30000
    host: str = ""
    api_key: str = ""
    port: int = 0

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def base_url(self) -> str:
        if self.port:
            return f"{self.host}:{self.port}"
        return self.host

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "model": self.model,
            "capabilities": self.capabilities,
            "safety_level": self.safety_level,
            "context_len": self.context_len,
            "cost": self.cost,
            "priority": self.priority,
            "timeout_ms": self.timeout_ms,
        }


class EngineCatalog:
    def __init__(self):
        self.engines: Dict[str, EngineSpec] = {}
        self._load_default_engines()
        self._load_openai_compat_engines()

    def _load_default_engines(self):
        default_engines = [
            EngineSpec(
                id="smx_response",
                provider="smx",
                model="qwen3b",
                host="http://127.0.0.1",
                port=9997,
                capabilities=["chat", "code", "tools"],
                safety_level="high",
                context_len=8192,
                cost=0.0,
                priority=90,
                timeout_ms=8000,
            ),
            EngineSpec(
                id="smx_macro",
                provider="smx",
                model="qwencoder7b",
                host="http://127.0.0.1",
                port=9998,
                capabilities=["chat", "code"],
                safety_level="medium",
                context_len=8192,
                cost=0.0,
                priority=80,
                timeout_ms=10000,
            ),
            EngineSpec(
                id="smx_fast_check",
                provider="smx",
                model="qwen05b",
                host="http://10.10.10.2",
                port=8003,
                capabilities=["chat"],
                safety_level="medium",
                context_len=2048,
                cost=0.0,
                priority=95,
                timeout_ms=2000,
            ),
            EngineSpec(
                id="smx_tokenize",
                provider="smx",
                model="smollm2",
                host="http://10.10.10.2",
                port=8006,
                capabilities=["tokenize"],
                safety_level="high",
                context_len=4096,
                cost=0.0,
                priority=70,
                timeout_ms=1000,
            ),
            EngineSpec(
                id="smx_safety",
                provider="smx",
                model="gemma1b",
                host="http://10.10.10.2",
                port=8007,
                capabilities=["safety"],
                safety_level="critical",
                context_len=4096,
                cost=0.0,
                priority=100,
                timeout_ms=1500,
            ),
            EngineSpec(
                id="smx_intent",
                provider="smx",
                model="qwen15b",
                host="http://10.10.10.2",
                port=8008,
                capabilities=["intent"],
                safety_level="medium",
                context_len=4096,
                cost=0.0,
                priority=85,
                timeout_ms=3000,
            ),
        ]

        for engine in default_engines:
            self.engines[engine.id] = engine

    def _load_openai_compat_engines(self):
        base_base_url = os.getenv("OPENAI_COMPAT_BASE_URL", "")
        api_key = os.getenv("OPENAI_COMPAT_API_KEY", "")

        if not base_base_url:
            return

        openai_engines = [
            EngineSpec(
                id="openai_gpt4",
                provider="openai_compat",
                model="gpt-4",
                host=base_base_url,
                api_key=api_key,
                capabilities=["chat", "code", "tools", "vision"],
                safety_level="high",
                context_len=8192,
                cost=0.03,
                priority=75,
                timeout_ms=60000,
            ),
            EngineSpec(
                id="openai_gpt35",
                provider="openai_compat",
                model="gpt-3.5-turbo",
                host=base_base_url,
                api_key=api_key,
                capabilities=["chat", "code", "tools"],
                safety_level="medium",
                context_len=4096,
                cost=0.002,
                priority=60,
                timeout_ms=30000,
            ),
            EngineSpec(
                id="openai_coder",
                provider="openai_compat",
                model="gpt-4-code",
                host=base_base_url,
                api_key=api_key,
                capabilities=["code"],
                safety_level="high",
                context_len=16384,
                cost=0.06,
                priority=70,
                timeout_ms=90000,
            ),
        ]

        for engine in openai_engines:
            if base_base_url:
                self.engines[engine.id] = engine

    def get(self, engine_id: str) -> Optional[EngineSpec]:
        return self.engines.get(engine_id)

    def list_all(self) -> List[EngineSpec]:
        return list(self.engines.values())

    def list_by_capability(self, capability: str) -> List[EngineSpec]:
        return [e for e in self.engines.values() if e.supports(capability)]

    def list_by_safety(self, min_safety: str) -> List[EngineSpec]:
        safety_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_level = safety_order.get(min_safety, 0)
        return [
            e
            for e in self.engines.values()
            if safety_order.get(e.safety_level, 0) >= min_level
        ]


def get_engine_catalog() -> EngineCatalog:
    return EngineCatalog()
