#!/usr/bin/env python3
"""Smoke CLI for chat control plane."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR in sys.path:
    sys.path.remove(SCRIPT_DIR)
if ROOT_DIR in sys.path:
    sys.path.remove(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

from denis_unified_v1.chat_cp.contracts import ChatRequest
from denis_unified_v1.chat_cp.preflight import format_preflight_lines, run_chat_cp_preflight


async def _run(args: argparse.Namespace) -> int:
    use_router = args.provider == "auto" or bool(args.shadow_mode) or bool(args.via_router)
    preflight_provider = "auto" if use_router else args.provider
    if not bool(args.no_preflight):
        preflight = run_chat_cp_preflight(
            provider=preflight_provider,
            service=getattr(args, "service", "denis_chat_cp"),
            timeout_seconds=float(getattr(args, "timeout_seconds", 3.0)),
        )
        for line in format_preflight_lines(preflight):
            print(line)

        if bool(args.strict_preflight) and not bool(preflight.get("ready", False)):
            print("preflight_strict_failed=true")
            return 2
        if not use_router and not bool(preflight.get("ready", False)):
            print("preflight_failed=true")
            secret_name = (
                "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
            )
            print(
                "hint: verify keyring with "
                "`python3 tools/chat_cp_secrets_doctor.py --provider "
                f"{args.provider}`"
            )
            print(
                "hint: set secret with "
                f"`python3 -m denis_unified_v1.chat_cp.secrets set {secret_name}`"
            )
            return 2

    if args.debug_keyring:
        from denis_unified_v1.chat_cp.secrets import (
            SecretError,
            _explicit_backends,
            get_backend_type,
            get_secret,
            is_keyring_available,
        )
        import keyring  # type: ignore

        print(
            json.dumps(
                {
                    "keyring_available": bool(is_keyring_available()),
                    "keyring_backend": get_backend_type(),
                    "keyring_module": getattr(keyring, "__file__", "unknown"),
                },
                ensure_ascii=True,
            )
        )
        for backend in _explicit_backends():
            payload: dict[str, Any] = {
                "explicit_backend_module": backend.__class__.__module__,
                "explicit_backend_name": backend.__class__.__name__,
            }
            for secret_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                try:
                    value = backend.get_password("denis_chat_cp", secret_name)
                    payload[secret_name] = "set" if bool(value) else "not_set"
                except Exception as exc:
                    payload[secret_name] = f"error:{type(exc).__name__}"
            print(json.dumps(payload, ensure_ascii=True))
        for secret_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            try:
                value = get_secret(secret_name, required=False)
                print(
                    json.dumps(
                        {
                            "secret": secret_name,
                            "status": "set" if bool(value) else "not_set",
                        },
                        ensure_ascii=True,
                    )
                )
            except SecretError as exc:
                print(
                    json.dumps(
                        {
                            "secret": secret_name,
                            "status": "error",
                            "error": str(exc),
                        },
                        ensure_ascii=True,
                    )
                )

    metadata: dict[str, Any] | None = {"source": "chat_cp_smoke"} if use_router else None
    if use_router and args.provider != "auto":
        metadata["preferred_provider"] = args.provider

    request = ChatRequest.from_payload(
        {
            "messages": [{"role": "user", "content": args.message}],
            "response_format": args.response_format,
            "temperature": args.temperature,
            "max_output_tokens": args.max_output_tokens,
            "stream": False,
            "trace_id": args.trace_id,
            "metadata": metadata,
            "task_profile_id": "control_plane_chat",
        }
    )

    try:
        if use_router:
            from denis_unified_v1.chat_cp.client import chat as chat_cp_chat
            response = await chat_cp_chat(
                request,
                shadow_mode=bool(args.shadow_mode),
            )
        elif args.provider == "openai":
            from denis_unified_v1.chat_cp.providers.openai_chat import OpenAIChatProvider
            response = await OpenAIChatProvider(
                api_key=getattr(args, "openai_api_key", None)
            ).chat(request)
        elif args.provider == "anthropic":
            from denis_unified_v1.chat_cp.providers.anthropic_chat import AnthropicChatProvider
            response = await AnthropicChatProvider(
                api_key=getattr(args, "anthropic_api_key", None)
            ).chat(request)
        else:
            from denis_unified_v1.chat_cp.providers.local_chat import LocalChatProvider
            response = await LocalChatProvider().chat(request)
    except Exception as exc:
        from denis_unified_v1.chat_cp.errors import ChatProviderError

        if isinstance(exc, ChatProviderError):
            print(f"provider={args.provider} latency_ms=0")
            print(
                json.dumps(
                    {
                        "error": {
                            "code": exc.code,
                            "msg": str(exc),
                            "retryable": exc.retryable,
                        }
                    },
                    ensure_ascii=True,
                )
            )
            if exc.code == "missing_secret":
                secret_name = (
                    "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
                )
                print(
                    "hint: set secret with "
                    f"`python3 -m denis_unified_v1.chat_cp.secrets set {secret_name}`"
                )
            if exc.code in {"quota_exceeded", "auth_error", "missing_secret"}:
                return 2
            return 1
        print(f"provider={args.provider} latency_ms=0")
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 1

    print(f"provider={response.provider} latency_ms={response.latency_ms}")
    print(
        json.dumps(
            {
                "success": bool(response.success),
                "model": response.model,
                "trace_id": response.trace_id,
            },
            ensure_ascii=True,
        )
    )
    if response.json is not None:
        print(json.dumps(response.json, ensure_ascii=True))
    else:
        print(response.text or "")

    if response.error is not None:
        print(json.dumps(response.error.as_dict(), ensure_ascii=True))
        if response.error.code in {"quota_exceeded", "auth_error", "missing_secret"}:
            return 2

    return 0


def _prefetch_secret(name: str, retries: int = 5) -> str | None:
    from denis_unified_v1.chat_cp.secrets import SecretError, get_secret

    for attempt in range(retries):
        try:
            value = get_secret(name, required=False)
            if value:
                return value
        except SecretError:
            if attempt >= retries - 1:
                return None
        time.sleep(min(0.1 * (attempt + 1), 0.4))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="chat_cp smoke test")
    parser.add_argument("--provider", default="auto", choices=["auto", "openai", "anthropic", "local"])
    parser.add_argument("--message", default="ping")
    parser.add_argument("--response-format", default="text", choices=["text", "json"])
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--service", default="denis_chat_cp")
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--shadow-mode", action="store_true")
    parser.add_argument("--via-router", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-preflight", action="store_true")
    parser.add_argument("--strict-preflight", action="store_true")
    parser.add_argument("--debug-keyring", action="store_true")
    args = parser.parse_args()

    if bool(args.strict):
        os.environ["DENIS_CHAT_CP_STRICT"] = "1"

    use_router = args.provider == "auto" or bool(args.shadow_mode) or bool(args.via_router)
    args.openai_api_key = None
    args.anthropic_api_key = None
    if not use_router and args.provider == "openai":
        args.openai_api_key = _prefetch_secret("OPENAI_API_KEY")
    if not use_router and args.provider == "anthropic":
        args.anthropic_api_key = _prefetch_secret("ANTHROPIC_API_KEY")

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
