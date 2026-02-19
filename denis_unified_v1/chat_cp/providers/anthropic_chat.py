"""Anthropic Messages adapter for chat control plane."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import aiohttp

from denis_unified_v1.chat_cp.contracts import ChatRequest, ChatResponse
from denis_unified_v1.chat_cp.errors import ChatProviderError, redact
from denis_unified_v1.chat_cp.secrets import SecretError, ensure_secret


def _extract_error_message(body: str) -> tuple[str, str]:
    try:
        parsed = json.loads(body)
    except Exception:
        return "", ""

    err = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(err, dict):
        return "", ""
    msg = str(err.get("message") or "")
    code = str(err.get("type") or err.get("code") or "")
    return code.lower(), msg.lower()


def _map_anthropic_http_error(status: int, body: str) -> ChatProviderError:
    code_hint, msg_hint = _extract_error_message(body)

    if status in (401, 403) or code_hint in {"authentication_error", "permission_error"}:
        return ChatProviderError(
            code="auth_error",
            msg="Anthropic authentication failed.",
            retryable=False,
        )

    if code_hint in {"insufficient_quota", "quota_exceeded", "credit_balance_too_low"}:
        return ChatProviderError(
            code="quota_error",
            msg="Anthropic quota exceeded.",
            retryable=False,
        )

    if "quota" in msg_hint or "billing" in msg_hint or "credit" in msg_hint:
        return ChatProviderError(
            code="quota_error",
            msg="Anthropic quota exceeded.",
            retryable=False,
        )

    if status == 429 or code_hint == "rate_limit_error":
        return ChatProviderError(
            code="rate_limit",
            msg="Anthropic rate limited.",
            retryable=True,
        )

    if status in (408, 409, 500, 502, 503, 504, 529):
        return ChatProviderError(
            code="server_error",
            msg="Anthropic temporary upstream error.",
            retryable=True,
        )

    return ChatProviderError(
        code="server_error",
        msg=redact(body[:200]) or "Anthropic request failed.",
        retryable=False,
    )


class AnthropicChatProvider:
    provider = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        connect_seconds: float = 3.0,
        total_seconds: float = 12.0,
    ) -> None:
        self.model = model or os.getenv(
            "ANTHROPIC_CHAT_MODEL", "claude-3-5-haiku-latest"
        )
        self.base_url = (
            base_url
            or os.getenv("ANTHROPIC_API_BASE_URL", "https://api.anthropic.com/v1")
        ).rstrip("/")
        self.connect_seconds = connect_seconds
        self.total_seconds = total_seconds
        self._missing_secret_reason: str | None = None

        if api_key:
            self.api_key = api_key
        else:
            self.api_key = None
            self._refresh_api_key()

    def is_configured(self) -> bool:
        return bool(self._refresh_api_key())

    def _refresh_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        try:
            self.api_key = ensure_secret("ANTHROPIC_API_KEY")
            self._missing_secret_reason = None
        except SecretError as exc:
            self.api_key = None
            self._missing_secret_reason = str(exc)
        return self.api_key

    async def chat(self, request: ChatRequest) -> ChatResponse:
        api_key = self._refresh_api_key()
        if not api_key:
            raise ChatProviderError(
                code="missing_secret",
                msg=self._missing_secret_reason or "Missing Anthropic key in keyring.",
                retryable=False,
            )

        started = time.perf_counter()
        system_parts: list[str] = []
        messages: list[dict[str, str]] = []
        for item in request.messages:
            if item.role == "system":
                system_parts.append(item.content)
                continue
            messages.append({"role": item.role, "content": item.content})

        if not messages:
            raise ChatProviderError(
                code="invalid_request",
                msg="Anthropic requires at least one non-system message.",
                retryable=False,
            )

        if request.response_format == "json":
            system_parts.append("Return only a valid JSON object.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": bool(request.stream),
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        timeout = aiohttp.ClientTimeout(
            total=self.total_seconds, connect=self.connect_seconds
        )
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url = f"{self.base_url}/messages"

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise _map_anthropic_http_error(response.status, body)
                    parsed = json.loads(body)

            content_blocks = parsed.get("content") or []
            text = "".join(
                str(block.get("text", ""))
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )

            json_body = None
            if request.response_format == "json":
                json_body = ChatResponse.safe_json_from_text(text)
                if json_body is None:
                    raise ChatProviderError(
                        code="json_parse_error",
                        msg="anthropic returned non-json content",
                        retryable=False,
                    )

            usage = (
                parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None
            )
            return ChatResponse(
                text=text if request.response_format == "text" else None,
                json=json_body,
                provider="anthropic",
                model=str(parsed.get("model") or self.model),
                usage=usage,
                latency_ms=int((time.perf_counter() - started) * 1000),
                success=True,
                trace_id=request.trace_id,
            )
        except ChatProviderError:
            raise
        except asyncio.TimeoutError as exc:
            raise ChatProviderError(
                code="timeout",
                msg="Anthropic request timed out.",
                retryable=True,
            ) from exc
        except aiohttp.ClientError as exc:
            raise ChatProviderError(
                code="network_error",
                msg="Anthropic network error.",
                retryable=True,
            ) from exc
        except Exception as exc:
            raise ChatProviderError(
                code="server_error",
                msg=redact(str(exc)[:200]) or "Anthropic unknown error.",
                retryable=True,
            ) from exc
