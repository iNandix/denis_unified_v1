"""OpenAI contract tests for API stability."""

import json
import pytest
from typing import Dict, Any
from fastapi.testclient import TestClient

from api.fastapi_server import create_app


def normalize_openai_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize OpenAI response for stable contract testing."""
    return {
        # Fixed fields for contract validation
        "id": "NORMALIZED_ID",
        "object": response.get("object"),
        "created": 1234567890,  # Fixed timestamp
        "model": response.get("model"),

        # Choices structure
        "choices": [{
            "index": choice["index"],
            "message": {
                "role": choice["message"]["role"],
                "content": (
                    "NONEMPTY_STRING" if choice["message"].get("content") else None
                ),
                "tool_calls": (
                    [{
                        "id": "NORMALIZED_TOOL_ID",
                        "type": tc["type"],
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": "NORMALIZED_JSON_ARGS"
                        }
                    } for tc in choice["message"].get("tool_calls", [])]
                    if choice["message"].get("tool_calls") else None
                )
            },
            "finish_reason": choice["finish_reason"]
        } for choice in response.get("choices", [])],

        # Usage structure
        "usage": {
            "prompt_tokens": max(0, response.get("usage", {}).get("prompt_tokens", 0)),
            "completion_tokens": max(0, response.get("usage", {}).get("completion_tokens", 0)),
            "total_tokens": max(0, response.get("usage", {}).get("total_tokens", 0))
        },

        # Optional extensions (if present)
        **({"extensions": response.get("extensions", {})} if "extensions" in response else {})
    }


class TestOpenAIContract:
    """OpenAI API contract stability tests."""

    @pytest.fixture
    def client(self, monkeypatch):
        """Test client with deterministic runtime."""
        from fastapi.testclient import TestClient
        from api.fastapi_server import create_app

        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
        monkeypatch.setenv("DENIS_TEST_MODE", "1")

        app = create_app()
        with TestClient(app) as c:
            yield c

    def test_chat_completions_contract_shape(self, client):
        """Test OpenAI chat completions contract shape."""
        response = client.post("/v1/chat/completions", json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "Hello world"}]
        })

        assert response.status_code == 200
        data = response.json()

        # Validate top-level structure
        assert "id" in data and isinstance(data["id"], str)
        assert data.get("object") == "chat.completion"
        assert isinstance(data.get("created"), int)
        assert "model" in data
        assert "choices" in data and isinstance(data["choices"], list)
        assert "usage" in data and isinstance(data["usage"], dict)

        # Validate choices structure
        assert len(data["choices"]) > 0
        choice = data["choices"][0]
        assert choice["index"] == 0
        assert "message" in choice
        assert choice["message"]["role"] == "assistant"
        assert "content" in choice["message"] or "tool_calls" in choice["message"]
        assert "finish_reason" in choice

        # Validate usage structure
        usage = data["usage"]
        assert all(key in usage for key in ["prompt_tokens", "completion_tokens", "total_tokens"])
        assert all(isinstance(v, int) and v >= 0 for v in usage.values())
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_chat_completions_contract_invariants(self, client):
        """Test OpenAI response invariants that must always hold."""
        # Test normal response
        response = client.post("/v1/chat/completions", json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "Test message"}]
        })

        assert response.status_code == 200
        data = response.json()

        # Invariants
        choice = data["choices"][0]
        assert choice["finish_reason"] == "stop"
        assert choice["message"]["content"] is not None
        assert choice["message"]["tool_calls"] is None

        # Test tool call response
        response = client.post("/v1/chat/completions", json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "Use tool please"}]
        })

        assert response.status_code == 200
        data = response.json()

        choice = data["choices"][0]
        assert choice["finish_reason"] == "tool_calls"
        assert choice["message"]["content"] is None
        assert choice["message"]["tool_calls"] is not None
        assert len(choice["message"]["tool_calls"]) > 0

        tool_call = choice["message"]["tool_calls"][0]
        assert tool_call["type"] == "function"
        assert "function" in tool_call
        assert tool_call["function"]["name"]
        assert tool_call["function"]["arguments"]

    def test_chat_completions_streaming_contract(self, client):
        """Test streaming response contract."""
        response = client.post("/v1/chat/completions", json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "Stream test"}],
            "stream": True
        })

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Parse SSE stream
        lines = response.text.strip().split('\n\n')
        events = []

        for line in lines:
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    events.append(data)
                except json.JSONDecodeError:
                    continue

        # Validate SSE contract
        assert len(events) >= 2  # At least start and end events

        # Should have proper event types and structure
        event_types = {event.get("type") for event in events if "type" in event}
        assert "status" in event_types or "content" in event_types

        # If content event present, should have content field
        content_events = [e for e in events if e.get("type") == "content"]
        if content_events:
            assert "content" in content_events[0]

        # Should end with done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) > 0

    @pytest.mark.contract
    def test_chat_completions_golden_snapshot(self, client):
        """Golden snapshot test for contract validation."""
        response = client.post("/v1/chat/completions", json={
            "model": "denis-contract-test",
            "messages": [{"role": "user", "content": "Golden snapshot test"}]
        })

        assert response.status_code == 200
        data = response.json()

        # Normalize for stable comparison
        normalized = normalize_openai_response(data)

        # Load golden fixture
        golden_path = "tests/fixtures/openai_chat_completions_golden.json"
        try:
            with open(golden_path, 'r') as f:
                golden = json.load(f)

            # Compare normalized response to golden
            assert normalized == golden, "OpenAI response does not match golden contract"

        except FileNotFoundError:
            # Create golden fixture on first run
            with open(golden_path, 'w') as f:
                json.dump(normalized, f, indent=2)
            pytest.skip(f"Created new golden fixture: {golden_path}")


def test_models_endpoint_contract(client):
    """Test /v1/models endpoint contract."""
    response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()

    # Validate structure
    assert data.get("object") == "list"
    assert "data" in data and isinstance(data["data"], list)

    # Should have at least one model
    assert len(data["data"]) > 0

    # Validate model structure
    model = data["data"][0]
    assert "id" in model and isinstance(model["id"], str)
    assert model.get("object") == "model"


@pytest.mark.contract
def test_openai_router_inclusion_in_test_mode(client):
    """
    Test that the OpenAI router is properly included in test mode.
    
    This protects against the bug where _safe_include was not defined,
    causing the DenisRuntime router to not be included and tests to hit
    the degraded fallback instead of the actual contract implementation.
    """
    # In test mode with DENIS_CONTRACT_TEST_MODE=1, the app should
    # successfully include the DenisRuntime router, not fall back to degraded
    
    # Make a request that should hit the DenisRuntime, not degraded fallback
    response = client.post('/v1/chat/completions', json={
        'model': 'denis-contract-test',
        'messages': [{'role': 'user', 'content': 'Router inclusion test'}]
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # If this hits degraded fallback, it will have "denis-cognitive" model
    # and "Degraded runtime response." content. But in test mode with 
    # proper router inclusion, it should return the deterministic response
    # with "denis-contract-test" model and proper content.
    
    # This assertion will fail if the router inclusion bug reoccurs
    assert data.get("model") == "denis-contract-test"
    assert "Deterministic test response" in data.get("choices", [{}])[0].get("message", {}).get("content", "")
