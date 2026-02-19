"""Runtime preflight checks for Chat CP providers."""

from __future__ import annotations

import socket
import ssl
import urllib.request
from typing import Any

from denis_unified_v1.chat_cp.secrets import (
    preflight_keyring,
    required_secrets_for_provider,
    get_secret,
)

_PROVIDER_HOSTS: dict[str, str] = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
}


def run_chat_cp_preflight(
    *,
    provider: str = "auto",
    service: str = "denis_chat_cp",
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    provider_key = (provider or "auto").strip().lower()
    if provider_key not in {"auto", "openai", "anthropic", "local"}:
        provider_key = "auto"

    providers_to_probe: tuple[str, ...]
    if provider_key == "auto":
        providers_to_probe = ("openai", "anthropic")
    elif provider_key in {"openai", "anthropic"}:
        providers_to_probe = (provider_key,)
    else:
        providers_to_probe = ()

    required_secret_names: list[str] = []
    for item in providers_to_probe:
        required_secret_names.extend(required_secrets_for_provider(item))

    keyring_diag = preflight_keyring(
        required_secrets=tuple(required_secret_names),
        service=service,
    )
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "keyring",
            "ok": bool(keyring_diag.get("keyring_available", False)),
            "detail": f"backend={keyring_diag.get('backend', 'unknown')}",
            "required": provider_key in {"openai", "anthropic"},
        }
    )

    external_health: dict[str, dict[str, Any]] = {}
    for external in providers_to_probe:
        host = _PROVIDER_HOSTS[external]
        dns_ok, dns_detail = _check_dns(host)
        tcp_ok, tcp_detail = _check_tcp(host, 443, timeout_seconds=timeout_seconds)
        tls_ok, tls_detail = _check_tls(host, 443, timeout_seconds=timeout_seconds)
        secret_name = required_secrets_for_provider(external)[0]
        secret_row = (keyring_diag.get("secrets") or {}).get(secret_name, {})
        secret_ok = isinstance(secret_row, dict) and secret_row.get("status") == "set"
        probe_ok, probe_detail = _probe_provider_models(
            external,
            timeout_seconds=timeout_seconds,
        ) if secret_ok and dns_ok and tcp_ok and tls_ok else (False, "skipped")
        external_ok = bool(secret_ok and dns_ok and tcp_ok and tls_ok and probe_ok)
        external_health[external] = {
            "provider": external,
            "host": host,
            "secret_ok": bool(secret_ok),
            "dns_ok": bool(dns_ok),
            "tcp_ok": bool(tcp_ok),
            "tls_ok": bool(tls_ok),
            "probe_ok": bool(probe_ok),
            "ok": external_ok,
            "details": {
                "secret": secret_row,
                "dns": dns_detail,
                "tcp": tcp_detail,
                "tls": tls_detail,
                "probe": probe_detail,
            },
        }
        checks.append(
            {
                "name": f"{external}_secret",
                "ok": bool(secret_ok),
                "detail": f"status={secret_row.get('status', 'unknown') if isinstance(secret_row, dict) else 'unknown'}",
                "required": provider_key == external,
            }
        )
        checks.append(
            {
                "name": f"{external}_dns",
                "ok": bool(dns_ok),
                "detail": dns_detail,
                "required": provider_key == external,
            }
        )
        checks.append(
            {
                "name": f"{external}_tcp_443",
                "ok": bool(tcp_ok),
                "detail": tcp_detail,
                "required": provider_key == external,
            }
        )
        checks.append(
            {
                "name": f"{external}_tls",
                "ok": bool(tls_ok),
                "detail": tls_detail,
                "required": provider_key == external,
            }
        )
        checks.append(
            {
                "name": f"{external}_probe_models",
                "ok": bool(probe_ok) if secret_ok else True,
                "detail": probe_detail,
                "required": provider_key == external,
            }
        )

    external_ready = any(row["ok"] for row in external_health.values())
    if provider_key == "local":
        ready = True
        degraded = False
    elif provider_key == "auto":
        ready = True
        degraded = not external_ready
    else:
        ready = bool(external_health.get(provider_key, {}).get("ok", False))
        degraded = False

    return {
        "provider": provider_key,
        "ready": ready,
        "degraded": degraded,
        "external_ready": external_ready,
        "keyring": keyring_diag,
        "providers": external_health,
        "checks": checks,
    }


def format_preflight_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(
        "preflight: "
        f"provider={payload.get('provider')} ready={payload.get('ready')} "
        f"degraded={payload.get('degraded')} external_ready={payload.get('external_ready')}"
    )
    keyring = payload.get("keyring", {})
    if isinstance(keyring, dict):
        lines.append(
            "keyring: "
            f"available={keyring.get('keyring_available')} backend={keyring.get('backend')}"
        )
        secrets = keyring.get("secrets", {})
        if isinstance(secrets, dict):
            for name, row in secrets.items():
                status = row.get("status") if isinstance(row, dict) else "unknown"
                lines.append(f"secret {name}: {status}")

    checks = payload.get("checks", [])
    if isinstance(checks, list):
        for row in checks:
            if not isinstance(row, dict):
                continue
            if row.get("ok", False):
                continue
            lines.append(
                "check failed: "
                f"{row.get('name')} detail={row.get('detail')} required={row.get('required')}"
            )
    return lines


def _check_dns(host: str) -> tuple[bool, str]:
    try:
        addrs = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except Exception as exc:
        return False, f"dns_error={type(exc).__name__}"
    if not addrs:
        return False, "dns_no_records"
    return True, f"resolved={len(addrs)}"


def _check_tcp(host: str, port: int, *, timeout_seconds: float) -> tuple[bool, str]:
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout_seconds)
    except Exception as exc:
        return False, f"tcp_error={type(exc).__name__}"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return True, "connected"


def _check_tls(host: str, port: int, *, timeout_seconds: float) -> tuple[bool, str]:
    sock = None
    ssock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout_seconds)
        ctx = ssl.create_default_context()
        ssock = ctx.wrap_socket(sock, server_hostname=host)
        _ = ssock.version()
    except Exception as exc:
        return False, f"tls_error={type(exc).__name__}"
    finally:
        if ssock is not None:
            try:
                ssock.close()
            except Exception:
                pass
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return True, "handshake_ok"


def _probe_provider_models(provider: str, *, timeout_seconds: float) -> tuple[bool, str]:
    provider_key = (provider or "").strip().lower()
    if provider_key == "openai":
        key = get_secret("OPENAI_API_KEY", required=False)
        if not key:
            return False, "missing_secret"
        url = "https://api.openai.com/v1/models"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {key}")
    elif provider_key == "anthropic":
        key = get_secret("ANTHROPIC_API_KEY", required=False)
        if not key:
            return False, "missing_secret"
        url = "https://api.anthropic.com/v1/models"
        req = urllib.request.Request(url)
        req.add_header("x-api-key", key)
        req.add_header("anthropic-version", "2023-06-01")
    else:
        return False, "unsupported"

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            status = int(getattr(resp, "status", 200))
            if 200 <= status < 300:
                return True, f"http_{status}"
            if status in (401, 403):
                return False, "auth_error"
            if status == 429:
                return False, "rate_limit"
            if status >= 500:
                return False, "server_error"
            return False, f"http_{status}"
    except Exception as exc:
        return False, f"probe_error={type(exc).__name__}"
