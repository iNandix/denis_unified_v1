"""Bridge to legacy memory API running on Denis core (port 8084 by default)."""

from __future__ import annotations

import os
from typing import Any

import aiohttp


class LegacyMemoryClient:
    def __init__(self) -> None:
        self.base_url = (
            os.getenv("DENIS_LEGACY_MEMORY_URL") or "http://127.0.0.1:8084/v1/memory"
        ).rstrip("/")
        self.timeout_sec = float(os.getenv("DENIS_LEGACY_MEMORY_TIMEOUT_SEC", "6.0"))

    async def _get(self, path: str) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(0.5, self.timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}{path}") as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"legacy_memory_http_{resp.status}:{str(data)[:300]}")
                if isinstance(data, dict):
                    return data
                return {"value": data}

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(0.5, self.timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.base_url}{path}", json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    raise RuntimeError(f"legacy_memory_http_{resp.status}:{str(data)[:300]}")
                if isinstance(data, dict):
                    return data
                return {"value": data}

    async def store(
        self,
        *,
        user_id: str,
        content: str,
        layer: str,
        importance: float,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._post(
            "/store",
            {
                "user_id": user_id,
                "content": content,
                "layer": layer,
                "importance": float(importance),
                "metadata": metadata,
            },
        )

    async def neuro_layers(self) -> dict[str, Any]:
        return await self._get("/neuro/layers")

    async def neuro_synergies(self) -> dict[str, Any]:
        return await self._get("/neuro/synergies")

    async def atlas_projects(self) -> dict[str, Any]:
        return await self._get("/atlas/projects")

    async def contracts_verify(self, user_id: str) -> dict[str, Any]:
        return await self._get(f"/contracts/verify/{user_id}")
