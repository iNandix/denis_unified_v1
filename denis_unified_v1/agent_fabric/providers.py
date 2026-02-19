"""ProviderRegistry - Production-ready provider management with real endpoints."""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class Provider:
    """Production-ready provider with real endpoint."""

    name: str
    tier: str  # free_local, free_remote, premium
    endpoint: str
    api_key_env: str
    models: List[str] = field(default_factory=list)
    latencies: List[float] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0

    @property
    def avg_latency(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.latencies.append(latency_ms)
        if len(self.latencies) > 100:
            self.latencies = self.latencies[-100:]

    def record_failure(self) -> None:
        self.fail_count += 1


class ProviderRegistry:
    """Production provider registry with real endpoints and fallback."""

    def __init__(self):
        self.providers: Dict[str, Provider] = {
            "free_local": Provider(
                name="llama_local",
                tier="free_local",
                endpoint="http://localhost:8084/inference/local",
                api_key_env="",
                models=["llama-3.1-70b"],
            ),
            "free_remote": Provider(
                name="groq",
                tier="free_remote",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                models=["llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
            ),
            "premium": Provider(
                name="openrouter",
                tier="premium",
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                api_key_env="OPENROUTER_API_KEY",
                models=["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
            ),
        }
        self._stats = {"total_calls": 0, "fallback_count": 0}

    def select_provider(
        self, intent: str, model: str = None, session_context: Dict = None
    ) -> Provider:
        """Select best provider based on intent, model availability, and stats."""
        session_context = session_context or {}

        # Priority: free_local > free_remote > premium (for cost)
        tiers_order = ["free_local", "free_remote", "premium"]

        # Check available tiers
        for tier in tiers_order:
            provider = self.providers.get(tier)
            if provider and self._is_available(provider):
                logger.info(f"Selected provider: {provider.name} (tier: {tier})")
                return provider

        # Fallback to first available
        for tier, provider in self.providers.items():
            if self._is_available(provider):
                self._stats["fallback_count"] += 1
                return provider

        # Ultimate fallback: local
        return self.providers["free_local"]

    def _is_available(self, provider: Provider) -> bool:
        """Check if provider is available (has API key or local is up)."""
        if provider.tier == "free_local":
            return self._check_local()

        api_key = os.getenv(provider.api_key_env, "")
        return bool(api_key)

    def _check_local(self) -> bool:
        """Check if local inference is available."""
        try:
            import requests

            r = requests.get("http://localhost:8084/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def execute(
        self, provider: Provider, prompt: str, system_prompt: str = "", max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """Execute prompt with given provider."""
        self._stats["total_calls"] += 1
        start = time.time()

        try:
            if provider.tier == "free_local":
                result = self._call_local(provider, prompt, system_prompt, max_tokens)
            elif provider.tier == "free_remote":
                result = self._call_groq(provider, prompt, system_prompt, max_tokens)
            elif provider.tier == "premium":
                result = self._call_openrouter(provider, prompt, system_prompt, max_tokens)
            else:
                raise ValueError(f"Unknown tier: {provider.tier}")

            latency = (time.time() - start) * 1000
            provider.record_success(latency)

            return {
                "text": result["text"],
                "model": result.get("model", provider.name),
                "tokens": result.get("tokens", 0),
                "latency_ms": latency,
                "provider": provider.name,
                "success": True,
            }

        except Exception as e:
            provider.record_failure()
            logger.error(f"Provider {provider.name} failed: {e}")

            # Try fallback
            for tier, fallback in self.providers.items():
                if fallback.name != provider.name and self._is_available(fallback):
                    self._stats["fallback_count"] += 1
                    return self.execute(fallback, prompt, system_prompt, max_tokens)

            return {
                "text": f"[Error: {str(e)[:100]}]",
                "model": provider.name,
                "tokens": 0,
                "latency_ms": (time.time() - start) * 1000,
                "provider": provider.name,
                "success": False,
                "error": str(e),
            }

    def _call_local(self, provider: Provider, prompt: str, system: str, max_tokens: int) -> Dict:
        """Call local inference server."""
        import requests

        response = requests.post(
            provider.endpoint,
            json={"prompt": f"{system}\n\n{prompt}", "max_tokens": max_tokens},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return {"text": data.get("text", data.get("response", "")), "model": "llama_local"}

    def _call_groq(self, provider: Provider, prompt: str, system: str, max_tokens: int) -> Dict:
        """Call Groq API."""
        from groq import Groq

        client = Groq(api_key=os.getenv(provider.api_key_env))
        response = client.chat.completions.create(
            model=provider.models[0],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return {"text": response.choices[0].message.content, "model": response.model}

    def _call_openrouter(
        self, provider: Provider, prompt: str, system: str, max_tokens: int
    ) -> Dict:
        """Call OpenRouter API."""
        import urllib.request
        import json

        api_key = os.getenv(provider.api_key_env)
        payload = {
            "model": provider.models[0],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            provider.endpoint,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://denis.local",
                "X-Title": "Denis",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return {
                "text": data["choices"][0]["message"]["content"],
                "model": data.get("model", "claude"),
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "total_calls": self._stats["total_calls"],
            "fallback_count": self._stats["fallback_count"],
            "providers": {
                name: {
                    "avg_latency": p.avg_latency,
                    "success_rate": p.success_rate,
                    "success_count": p.success_count,
                    "fail_count": p.fail_count,
                }
                for name, p in self.providers.items()
            },
        }

    def get_available_models(self) -> Dict[str, bool]:
        """Check which models are available."""
        return {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
            "llama_local": self._check_local(),
        }
