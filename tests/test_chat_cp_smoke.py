from __future__ import annotations

import argparse

import pytest

from denis_unified_v1.chat_cp.contracts import ChatError, ChatResponse
from denis_unified_v1.chat_cp.errors import ChatProviderError
import tools.chat_cp_smoke as smoke


def _args(**kwargs: object) -> argparse.Namespace:
    data = {
        "provider": "auto",
        "message": "ping",
        "response_format": "text",
        "temperature": 0.2,
        "max_output_tokens": 64,
        "trace_id": None,
        "service": "denis_chat_cp",
        "timeout_seconds": 3.0,
        "shadow_mode": False,
        "via_router": False,
        "no_preflight": False,
        "strict_preflight": False,
        "debug_keyring": False,
        "openai_api_key": None,
        "anthropic_api_key": None,
    }
    data.update(kwargs)
    return argparse.Namespace(**data)


@pytest.mark.asyncio
async def test_smoke_missing_secret_prints_hint(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "run_chat_cp_preflight",
        lambda **kwargs: {"ready": True, "provider": kwargs.get("provider")},
    )
    monkeypatch.setattr(
        smoke,
        "format_preflight_lines",
        lambda payload: [f"preflight_ready={payload.get('ready')}"],
    )

    class DummyOpenAIProvider:
        def __init__(self, api_key=None):
            _ = api_key

        async def chat(self, request):
            _ = request
            raise ChatProviderError(
                code="missing_secret",
                msg="OpenAI key missing",
                retryable=False,
            )

    import denis_unified_v1.chat_cp.providers.openai_chat as openai_mod

    monkeypatch.setattr(openai_mod, "OpenAIChatProvider", DummyOpenAIProvider)

    code = await smoke._run(_args(provider="openai"))
    out = capsys.readouterr().out

    assert code == 2
    assert "missing_secret" in out
    assert "OPENAI_API_KEY" in out
    assert "chat_cp.secrets set" in out


@pytest.mark.asyncio
async def test_smoke_direct_provider_uses_prefetched_secret(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "run_chat_cp_preflight",
        lambda **kwargs: {"ready": True, "provider": kwargs.get("provider")},
    )
    monkeypatch.setattr(smoke, "format_preflight_lines", lambda payload: [])

    observed = {"api_key": None}

    class DummyOpenAIProvider:
        def __init__(self, api_key=None):
            observed["api_key"] = api_key

        async def chat(self, request):
            _ = request
            return ChatResponse(
                text="ok",
                json=None,
                provider="openai",
                model="gpt-test",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=1,
                success=True,
                trace_id="test-trace",
            )

    import denis_unified_v1.chat_cp.providers.openai_chat as openai_mod

    monkeypatch.setattr(openai_mod, "OpenAIChatProvider", DummyOpenAIProvider)

    code = await smoke._run(_args(provider="openai", openai_api_key="k-test"))
    out = capsys.readouterr().out

    assert code == 0
    assert observed["api_key"] == "k-test"
    assert "provider=openai" in out


@pytest.mark.asyncio
async def test_smoke_router_fallback_local(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "run_chat_cp_preflight",
        lambda **kwargs: {"ready": True, "provider": kwargs.get("provider")},
    )
    monkeypatch.setattr(smoke, "format_preflight_lines", lambda payload: [])

    async def fake_chat(request, *, shadow_mode=False):
        _ = request
        _ = shadow_mode
        return ChatResponse(
            text="Denis local fail-open response.",
            json=None,
            provider="local",
            model="local_stub",
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=2,
            success=True,
            error=ChatError(code="fail_open", msg="external providers unavailable"),
            trace_id="trace-fallback",
        )

    import denis_unified_v1.chat_cp.client as chat_client

    monkeypatch.setattr(chat_client, "chat", fake_chat)

    code = await smoke._run(_args(provider="auto", shadow_mode=True))
    out = capsys.readouterr().out

    assert code == 0
    assert "provider=local" in out
    assert "fail_open" in out


def test_prefetch_secret_handles_backend_error(monkeypatch):
    def fake_get_secret(name: str, required: bool = False):
        _ = name
        _ = required
        raise RuntimeError("backend down")

    import denis_unified_v1.chat_cp.secrets as secrets_mod

    monkeypatch.setattr(secrets_mod, "get_secret", fake_get_secret)
    monkeypatch.setattr(secrets_mod, "SecretError", RuntimeError)

    assert smoke._prefetch_secret("OPENAI_API_KEY", retries=2) is None


@pytest.mark.asyncio
async def test_smoke_preflight_blocks_direct_provider(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "run_chat_cp_preflight",
        lambda **kwargs: {"ready": False, "provider": kwargs.get("provider")},
    )
    monkeypatch.setattr(
        smoke,
        "format_preflight_lines",
        lambda payload: [f"preflight_ready={payload.get('ready')}"],
    )

    code = await smoke._run(_args(provider="openai"))
    out = capsys.readouterr().out

    assert code == 2
    assert "preflight_failed=true" in out


@pytest.mark.asyncio
async def test_smoke_preflight_degraded_allows_router(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke,
        "run_chat_cp_preflight",
        lambda **kwargs: {"ready": False, "provider": kwargs.get("provider")},
    )
    monkeypatch.setattr(
        smoke,
        "format_preflight_lines",
        lambda payload: [f"preflight_ready={payload.get('ready')}"],
    )

    async def fake_chat(request, *, shadow_mode=False):
        _ = request
        _ = shadow_mode
        return ChatResponse(
            text="local ok",
            json=None,
            provider="local",
            model="local_stub",
            usage={"input_tokens": 0, "output_tokens": 0},
            latency_ms=1,
            success=True,
            trace_id="trace-auto",
        )

    import denis_unified_v1.chat_cp.client as chat_client

    monkeypatch.setattr(chat_client, "chat", fake_chat)
    code = await smoke._run(_args(provider="auto"))
    out = capsys.readouterr().out

    assert code == 0
    assert "provider=local" in out
