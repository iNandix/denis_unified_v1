"""Home Assistant adapter that reuses existing Denis HASS clients."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import time
from typing import Any

from denis_unified_v1.cortex.world_interface import BaseAdapter
from denis_unified_v1.cortex.config_resolver import ensure_hass_env_auto


CORE_ROOT = Path("/media/jotah/SSD_denis/core")
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))
DIST_ROOT = Path("/media/jotah/SSD_denis/distributed/core/external")
if str(DIST_ROOT) not in sys.path:
    sys.path.insert(0, str(DIST_ROOT))


class HomeAssistantAdapter(BaseAdapter):
    name = "home_assistant"

    def __init__(self) -> None:
        self._client = None
        self._client_mode = None
        self._init_error: str | None = None
        self._resolve_info: dict[str, Any] | None = None
        self._resolve_cache_until: float = 0.0
        try:
            from denis_home_assistant_core import DenisHACoreClient  # type: ignore

            self._client = DenisHACoreClient()
            self._client_mode = "denis_home_assistant_core"
        except Exception as exc:
            primary_error = str(exc)
            try:
                import ha_async_client as ha_module  # type: ignore
                if not hasattr(ha_module, "os"):
                    ha_module.os = os  # compat patch for module missing `import os`
                get_ha_client = ha_module.get_ha_client

                self._client = get_ha_client
                self._client_mode = "ha_async_client"
            except Exception as exc2:
                self._init_error = f"{primary_error}; fallback_error={exc2}"

    async def _ensure_connected(self) -> tuple[bool, str | None]:
        now = time.time()
        if now >= self._resolve_cache_until:
            try:
                self._resolve_info = await ensure_hass_env_auto()
            except Exception as exc:
                self._resolve_info = {"status": "error", "error": str(exc)}
            # Cache resolver result for 10 minutes to avoid repeated probing.
            self._resolve_cache_until = now + 600.0

        if self._client is None:
            return False, self._init_error or "hass_client_unavailable"
        if self._client_mode == "ha_async_client":
            try:
                resolved = await self._client()
                if resolved is None:
                    return False, "ha_async_client_unavailable"
                self._client = resolved
                self._client_mode = "ha_async_client_ready"
                return True, None
            except Exception as exc:
                return False, str(exc)
        connected = getattr(self._client, "connected", False)
        if connected:
            return True, None
        try:
            ok = await self._client.initialize()
            return bool(ok), None if ok else "hass_initialize_failed"
        except Exception as exc:
            return False, str(exc)

    async def perceive(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        ok, err = await self._ensure_connected()
        if not ok:
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "error": err,
            }

        try:
            if hasattr(self._client, "get_state"):
                state = await self._client.get_state(entity_id)
                return {
                    "status": "ok",
                    "adapter": self.name,
                    "entity_id": entity_id,
                    "state": state,
                }
            if hasattr(self._client, "get_entity_state"):
                state = await self._client.get_entity_state(entity_id)
                return {
                    "status": "ok",
                    "adapter": self.name,
                    "entity_id": entity_id,
                    "state": state,
                }

            domain = entity_id.split(".", 1)[0] if "." in entity_id else "light"
            if hasattr(self._client, "get_devices_by_type"):
                devices = await self._client.get_devices_by_type(domain)
                selected = None
                if isinstance(devices, list):
                    for item in devices:
                        if isinstance(item, dict) and item.get("entity_id") == entity_id:
                            selected = item
                            break
                return {
                    "status": "ok",
                    "adapter": self.name,
                    "entity_id": entity_id,
                    "state": selected if selected is not None else {"devices": devices},
                }
            if hasattr(self._client, "get_all_states"):
                states = await self._client.get_all_states()
                return {
                    "status": "ok",
                    "adapter": self.name,
                    "entity_id": entity_id,
                    "state": {"states_count": len(states)},
                }

            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "error": "no_perceive_method",
            }
        except Exception as exc:
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "error": str(exc),
            }

    async def act(self, entity_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        ok, err = await self._ensure_connected()
        if not ok:
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "action": action,
                "error": err,
            }

        try:
            domain = kwargs.get("domain")
            service = kwargs.get("service", action)
            if not domain:
                domain = entity_id.split(".", 1)[0] if "." in entity_id else "homeassistant"

            payload = dict(kwargs.get("data") or {})
            payload.setdefault("entity_id", entity_id)

            result = await self._client.call_service(domain, service, **payload)
            return {
                "status": "ok",
                "adapter": self.name,
                "entity_id": entity_id,
                "action": action,
                "result": result,
            }
        except Exception as exc:
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "action": action,
                "error": str(exc),
            }

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "client_available": self._client is not None,
            "client_mode": self._client_mode,
            "init_error": self._init_error,
            "hass_url_env_set": bool(os.getenv("HASS_URL")),
            "hass_token_env_set": bool(os.getenv("HASS_TOKEN") or os.getenv("HA_TOKEN")),
            "config_resolver": self._resolve_info,
        }

    def describe_json(self) -> str:
        return json.dumps(self.describe(), sort_keys=True)
