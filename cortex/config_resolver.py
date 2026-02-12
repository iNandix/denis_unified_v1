"""Resolve HASS config from existing Denis sources (no manual daily setup)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import aiohttp


ROOT = Path("/media/jotah/SSD_denis")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS_ROOT = ROOT / "integrations"
if str(INTEGRATIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS_ROOT))

_CANONICAL_ENV_FILE = PROJECT_ROOT / ".env"
_LOCAL_ENV_FILE = PROJECT_ROOT / ".env.local"
_ROOT_LOCAL_ENV_FILE = ROOT / ".env.local"
_LEGACY_ENV_FILES = [
    # Prefer local secrets first (project, then root).
    _LOCAL_ENV_FILE,
    _ROOT_LOCAL_ENV_FILE,
    ROOT / ".env.prod.local",
    ROOT / ".env.platform",
    ROOT / ".env.ultimate",
    ROOT / ".env.jordi",
    ROOT / ".env",
    ROOT / ".env.denis",
    ROOT / ".env.hass",
    ROOT / ".env.denis.hass",
    ROOT / "denis-ha-complete" / ".env",
]
_ENV_FILES = [*_LEGACY_ENV_FILES, _CANONICAL_ENV_FILE]

_JSON_FILES = [
    ROOT / ".denis_hass_full_config.json",
    ROOT / ".denis_hass_agent_config.json",
    ROOT / ".denis_hass_setup_report.json",
]

_TOKEN_KEYS = (
    "HA_TOKEN",
    "HASS_TOKEN",
    "HASS_LONG_LIVED_TOKEN",
    "DENIS_HA_TOKEN",
    "TOKEN",
    "hass_token",
    "ha_token",
)
_URL_KEYS = (
    "HA_BASE_URL",
    "HASS_URL",
    "HASS_BASE_URL",
    "HA_URL",
    "DENIS_HA_URL",
    "hass_url",
    "url",
    "base_url",
)


def _normalize_url(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return base


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        data[key] = value
    return data


def _extract_from_dict(d: dict[str, Any]) -> tuple[str | None, str | None]:
    url = None
    token = None
    for key in _URL_KEYS:
        if key in d and isinstance(d[key], str) and d[key].strip():
            url = _normalize_url(d[key])
            break
    for key in _TOKEN_KEYS:
        if key in d and isinstance(d[key], str) and d[key].strip():
            token = d[key].strip()
            break
    return url, token


def _collect_from_runtime_env() -> list[dict[str, str]]:
    env = dict(os.environ)
    url, token = _extract_from_dict(env)
    if url and token:
        return [{"source": "runtime_env", "url": _normalize_url(url), "token": token}]
    return []


def _collect_from_env_files() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in _ENV_FILES:
        env = _load_env_file(path)
        if not env:
            continue
        url, token = _extract_from_dict(env)
        if url and token:
            rows.append(
                {
                    "source": f"env_file:{path}",
                    "url": _normalize_url(url),
                    "token": token,
                }
            )
    return rows


def _collect_from_json_files() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in _JSON_FILES:
        if not path.exists():
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        url, token = _extract_from_dict(obj)
        if url and token:
            rows.append(
                {
                    "source": f"json_file:{path}",
                    "url": _normalize_url(url),
                    "token": token,
                }
            )
    return rows


def _collect_hass_urls_from_network_inventory() -> list[str]:
    urls: list[str] = []
    try:
        from denis_network_controller import get_network_controller, ServiceType  # type: ignore

        ctl = get_network_controller()
        service = ctl.get_service(ServiceType.HASS)
        if service:
            urls.append(_normalize_url(f"http://{service.host}:{service.port}"))
        url = ctl.get_hass_url()
        if isinstance(url, str) and url.strip():
            urls.append(_normalize_url(url))
    except Exception:
        pass
    try:
        import redis

        client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
        )
        redis_url = client.get("denis:service:hass")
        if redis_url:
            urls.append(_normalize_url(redis_url))
    except Exception:
        pass
    # De-duplicate preserving order
    dedup: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u not in seen:
            dedup.append(u)
            seen.add(u)
    return dedup


async def _is_valid_hass(
    url: str, token: str, timeout_sec: float = 4.0
) -> tuple[bool, int | None, str | None]:
    endpoint = f"{_normalize_url(url)}/api/"
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(endpoint, headers=headers) as resp:
                ok = resp.status == 200
                text = await resp.text()
                msg = None if ok else text[:180]
                return ok, resp.status, msg
    except Exception as exc:
        return False, None, str(exc)


def _token_fingerprint(token: str) -> str:
    # Security: fingerprint only, never log token itself.
    # Keep short and non-reversible.
    return re.sub(r"[^A-Za-z0-9]", "", token[-8:]).lower()


async def ensure_hass_env_auto() -> dict[str, Any]:
    candidates: list[dict[str, str]] = []
    # Canonical project .env first, then legacy env files, then runtime/json fallbacks.
    candidates.extend(_collect_from_env_files())
    candidates.extend(_collect_from_runtime_env())
    candidates.extend(_collect_from_json_files())

    inventory_urls = _collect_hass_urls_from_network_inventory()
    # Expand candidates by pairing known tokens with discovered urls.
    expanded: list[dict[str, str]] = []
    for c in candidates:
        expanded.append(c)
        for inv_url in inventory_urls:
            if inv_url != c["url"]:
                expanded.append(
                    {
                        "source": f"{c['source']}+inventory_url",
                        "url": inv_url,
                        "token": c["token"],
                    }
                )

    # De-duplicate by url+token fingerprint.
    dedup: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for c in expanded:
        fp = _token_fingerprint(c["token"])
        key = (_normalize_url(c["url"]), fp)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)

    attempts: list[dict[str, Any]] = []
    for c in dedup:
        ok, status, err = await _is_valid_hass(c["url"], c["token"])
        attempts.append(
            {
                "source": c["source"],
                "url": _normalize_url(c["url"]),
                "token_fp": _token_fingerprint(c["token"]),
                "ok": ok,
                "status_code": status,
                "error": err,
            }
        )
        if ok:
            os.environ["HA_BASE_URL"] = _normalize_url(c["url"])
            os.environ["HA_TOKEN"] = c["token"]
            os.environ["HASS_URL"] = _normalize_url(c["url"])
            os.environ["HASS_TOKEN"] = c["token"]
            return {
                "status": "ok",
                "selected_source": c["source"],
                "selected_url": _normalize_url(c["url"]),
                "token_fp": _token_fingerprint(c["token"]),
                "attempts": attempts,
            }

    return {
        "status": "error",
        "error": "no_valid_hass_config_found",
        "attempts": attempts,
        "inventory_urls": inventory_urls,
    }
