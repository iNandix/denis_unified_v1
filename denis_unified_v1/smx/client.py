"""Cliente unificado para los 6 motores SMX."""

import asyncio
import httpx
from typing import Dict, List, Optional
from dataclasses import dataclass
import time


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
            "fast_check": asyncio.Semaphore(4),
            "tokenize": asyncio.Semaphore(3),
            "safety": asyncio.Semaphore(2),
            "intent": asyncio.Semaphore(2),
            "response": asyncio.Semaphore(4),
            "macro": asyncio.Semaphore(2),
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

    async def call_motor(
        self,
        role: str,
        messages: List[Dict],
        max_tokens: int = 50,
        stream: bool = False,
    ):
        """Llama a motor con rate limiting por slot."""
        motor = next((m for m in self.motors if m.role == role), None)
        if not motor or not motor.healthy:
            raise ValueError(f"Motor {role} not available")

        sem = self.semaphores.get(role)
        if not sem:
            raise ValueError(f"No semaphore for {role}")

        start_time = time.time()

        try:
            async with sem:
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
                latency_ms = int((time.time() - start_time) * 1000)
                return resp.json()

        except Exception as e:
            raise ValueError(f"Motor {role} failed: {e}")

    async def close(self):
        await self.client.aclose()
