"""
SMX Orchestrator - 6 motores especializados
"""

import asyncio
import time
from typing import Optional
import httpx

from .models import SMXLayerResult


class SMXOrchestrator:
    """Orchestrator para 6 motores SMX"""
    
    MODELS = {
        # NODE2 (10.10.10.2)
        "tokenize": "http://10.10.10.2:8006",  # SmolLM2 1.7B
        "safety": "http://10.10.10.2:8007",    # Gemma 1B
        "fast": "http://10.10.10.2:8003",      # Qwen 0.5B
        "intent": "http://10.10.10.2:8008",    # Qwen 1.5B
        # NODE1 (localhost - este PC)
        "macro": "http://127.0.0.1:9998",      # QwenCoder 7B
        "response": "http://127.0.0.1:9997",   # Qwen 3B
    }
    
    def __init__(self):
        self.http = httpx.AsyncClient(timeout=10.0)
    
    async def call_layer(
        self,
        layer: str,
        text: str,
        context: Optional[dict] = None,
        timeout: float = 5.0
    ) -> SMXLayerResult:
        """Llama a un motor SMX específico"""
        t0 = time.time()
        
        url = self.MODELS.get(layer)
        if not url:
            return SMXLayerResult(
                layer_name=layer,
                success=False,
                output="",
                latency_ms=0,
                error=f"Unknown layer: {layer}"
            )
        
        try:
            prompt = self._build_prompt(layer, text, context)
            
            async with asyncio.timeout(timeout):
                resp = await self.http.post(
                    f"{url}/v1/completions",
                    json={
                        "prompt": prompt,
                        "max_tokens": self._get_max_tokens(layer),
                        "temperature": 0.2,
                        "stream": False,
                    }
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    output = data.get("choices", [{}])[0].get("text", "")
                    
                    return SMXLayerResult(
                        layer_name=layer,
                        success=True,
                        output=output.strip(),
                        latency_ms=int((time.time() - t0) * 1000)
                    )
                else:
                    return SMXLayerResult(
                        layer_name=layer,
                        success=False,
                        output="",
                        latency_ms=int((time.time() - t0) * 1000),
                        error=f"HTTP {resp.status_code}"
                    )
        
        except asyncio.TimeoutError:
            return SMXLayerResult(
                layer_name=layer,
                success=False,
                output="",
                latency_ms=int((time.time() - t0) * 1000),
                error="Timeout"
            )
        except Exception as e:
            return SMXLayerResult(
                layer_name=layer,
                success=False,
                output="",
                latency_ms=int((time.time() - t0) * 1000),
                error=str(e)
            )
    
    def _build_prompt(self, layer: str, text: str, context: Optional[dict]) -> str:
        """Construye prompt específico por layer"""
        prompts = {
            "tokenize": f"Normaliza este texto: {text}",
            "safety": f"¿Es seguro este texto? Responde SEGURO o BLOQUEADO: {text}",
            "fast": f"Responde brevemente: {text}",
            "intent": f"Intent del usuario: {text}",
            "macro": f"Plan de acciones para: {text}",
            "response": f"Responde: {text}",
        }
        return prompts.get(layer, text)
    
    def _get_max_tokens(self, layer: str) -> int:
        """Tokens máximos por layer"""
        return {
            "tokenize": 32,
            "safety": 16,
            "fast": 64,
            "intent": 32,
            "macro": 128,
            "response": 192,
        }.get(layer, 64)
    
    async def close(self):
        """Cerrar cliente HTTP"""
        await self.http.aclose()
