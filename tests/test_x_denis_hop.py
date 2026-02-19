import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_openai_compat_blocks_reentry_by_default(monkeypatch):
    from api.openai_compatible import build_openai_router

    monkeypatch.setenv("DENIS_OPENAI_COMPAT_MAX_HOP", "0")

    class DummyRuntime:
        def __init__(self):
            self.called = 0
            self.models = [{"id": "denis-cognitive", "object": "model"}]

        async def generate(self, req):
            self.called += 1
            return {"ok": True}

    runtime = DummyRuntime()
    app = FastAPI()
    app.include_router(build_openai_router(runtime))

    with TestClient(app) as client:
        resp = client.post(
            "/v1/chat/completions",
            headers={"X-Denis-Hop": "1"},
            json={"model": "denis-cognitive", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("meta", {}).get("path") == "blocked_hop"
    assert runtime.called == 0


def test_llamacpp_client_propagates_x_denis_hop(monkeypatch):
    import aiohttp

    from denis_unified_v1.inference.hop import set_current_hop, reset as reset_hop
    from denis_unified_v1.inference.llamacpp_client import LlamaCppClient

    seen = {"headers": None, "url": None}

    class FakeResp:
        status = 200

        async def json(self, content_type=None):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self._timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            return FakeResp()

    monkeypatch.setattr(aiohttp, "ClientSession", FakeSession)

    client = LlamaCppClient("http://engine.local:8003")
    token = set_current_hop(0)
    try:
        out = asyncio.run(
            client.generate(messages=[{"role": "user", "content": "ping"}], timeout_sec=1.0)
        )
    finally:
        reset_hop(token)

    assert out["response"] == "ok"
    assert seen["url"].endswith("/v1/chat/completions")
    assert isinstance(seen["headers"], dict)
    assert seen["headers"].get("X-Denis-Hop") == "1"
