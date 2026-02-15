"""Test router response contract - ensures all required fields are present."""

import pytest
from unittest.mock import patch, AsyncMock
from denis_unified_v1.inference.router import InferenceRouter
from denis_unified_v1.kernel.scheduler import InferencePlan


class MockClient:
    """Mock client for testing."""

    def __init__(self, provider: str, should_fail: bool = False):
        self.provider = provider
        self.cost_factor = 0.001
        self.should_fail = should_fail

    def is_available(self) -> bool:
        return True

    async def generate(self, messages, timeout_sec, **kwargs):
        if self.should_fail:
            raise RuntimeError("mock failure")
        return {
            "response": "test response",
            "input_tokens": 1,
            "output_tokens": 1,
        }


@pytest.mark.asyncio
async def test_response_has_required_fields():
    """Test that route_chat always returns required fields."""

    # Setup router with mock clients
    router = InferenceRouter()

    # Mock local engine to succeed
    router.engine_registry["llamacpp_node2_1"]["client"] = MockClient(
        "llamacpp", should_fail=False
    )

    plan = InferencePlan(
        primary_engine_id="llamacpp_node2_1",
        fallback_engine_ids=[],
        expected_model="llama-3.1-8b",
        params={},
        timeouts_ms={"total_ms": 1000},
        budget={},
        trace_tags={},
        attempt_policy={},
    )

    result = await router.route_chat(
        messages=[{"role": "user", "content": "test"}],
        request_id="test_req_001",
        inference_plan=plan,
    )

    # Required fields
    required_fields = [
        "response",
        "llm_used",
        "engine_id",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "fallback_used",
        "attempts",
    ]

    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    # Optional but important fields
    assert "skipped_engines" in result
    assert "internet_status" in result

    print("✅ All required fields present")
    print(f"  - llm_used: {result['llm_used']}")
    print(f"  - engine_id: {result['engine_id']}")
    print(f"  - fallback_used: {result['fallback_used']}")


@pytest.mark.asyncio
async def test_fallback_includes_degraded_field():
    """Test that fallback includes degraded flag."""

    router = InferenceRouter()

    # Mock local to fail
    router.engine_registry["llamacpp_node2_1"]["client"] = MockClient(
        "llamacpp", should_fail=True
    )

    # No fallbacks
    plan = InferencePlan(
        primary_engine_id="llamacpp_node2_1",
        fallback_engine_ids=[],
        expected_model="llama-3.1-8b",
        params={},
        timeouts_ms={"total_ms": 100},
        budget={},
        trace_tags={},
        attempt_policy={},
    )

    result = await router.route_chat(
        messages=[{"role": "user", "content": "test"}],
        request_id="test_fallback",
        inference_plan=plan,
    )

    assert "degraded" in result or result.get("llm_used") == "degraded_fallback"
    print(f"✅ Degraded field present: {result.get('degraded', 'degraded_fallback')}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_response_has_required_fields())
    asyncio.run(test_fallback_includes_degraded_field())
    print("\n✅ All contract tests passed!")
