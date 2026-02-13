"""Cliente unificado para los 6 motores SMX."""
import asyncio
import httpx
from typing import Dict, List, Optional
from dataclasses import dataclass

from metacognitive.hooks import metacognitive_trace

@dataclass
class SMXMotor:
    role: str
    model: str
    url: str
    port: int
    node: str
    healthy: bool = True

class SMXClient:
    """Cliente para orquestar llamadas a los 6 motores SMX."""

    def __init__(self):
        self.motors = [
            SMXMotor("fast_check", "qwen05b", "http://10.10.10.2", 8003, "nodo2"),
            SMXMotor("tokenize", "smollm2", "http://10.10.10.2", 8006, "nodo2"),
            SMXMotor("safety", "gemma1b", "http://10.10.10.2", 8007, "nodo2"),
            SMXMotor("intent", "qwen15b", "http://10.10.10.2", 8008, "nodo2"),
            SMXMotor("response", "qwen3b", "http://127.0.0.1", 9997, "nodo1"),
            SMXMotor("macro", "qwencoder7b", "http://127.0.0.1", 9998, "nodo1"),
        ]
        self.client = httpx.AsyncClient(timeout=10.0)

        # Semáforos por capacidad real de cada motor
        self.semaphores = {
            "fast_check": asyncio.Semaphore(4),   # Qwen 0.5B: 4 slots
            "tokenize": asyncio.Semaphore(3),     # SmolLM2: 3 slots
            "safety": asyncio.Semaphore(2),       # Gemma 1B: 2 slots
            "intent": asyncio.Semaphore(2),       # Qwen 1.5B: 2 slots
            "response": asyncio.Semaphore(4),     # Qwen 3B: 4 slots
            "macro": asyncio.Semaphore(2),        # QwenCoder 7B: 2 slots
        }

    async def health_check_all(self) -> Dict[str, bool]:
        """Verifica salud de todos los motores."""
        results = {}
        for motor in self.motors:
            try:
                resp = await self.client.get(f"{motor.url}:{motor.port}/health")
                motor.healthy = resp.status_code == 200
                results[motor.role] = motor.healthy
            except:
                motor.healthy = False
                results[motor.role] = False
        return results

    @metacognitive_trace(operation="smx_motor_call")
    async def call_motor(self, role: str, messages: List[Dict], max_tokens: int = 50, stream: bool = False):
        """Llama a motor con rate limiting por slot."""
        motor = next((m for m in self.motors if m.role == role), None)
        if not motor or not motor.healthy:
            raise ValueError(f"Motor {role} not available")

        # Adquirir slot
        sem = self.semaphores.get(role)
        if not sem:
            raise ValueError(f"No semaphore for {role}")

        async with sem:  # Bloquea si slots llenos
            payload = {
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": stream,
            }

            resp = await self.client.post(
                f"{motor.url}:{motor.port}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
