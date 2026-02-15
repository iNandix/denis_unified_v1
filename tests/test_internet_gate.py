"""Tests for internet gate + local-first enforcement.

These tests must patch BEFORE importing scheduler/router modules.
"""

import sys
from unittest.mock import patch, AsyncMock


# Create mock health class BEFORE any imports
class MockHealth:
    def __init__(self, status):
        self._status = status

    def check(self):
        return self._status


# Now do normal imports
from denis_unified_v1.kernel.scheduler import ModelScheduler, InferenceRequest
from denis_unified_v1.kernel.engine_registry import get_engine_registry, reset_registry
from denis_unified_v1.inference.router import InferenceRouter


def test_offline_skips_boosters():
    """Test: When internet is DOWN, boosters are skipped in plan."""
    reset_registry()

    mock_health = MockHealth("DOWN")

    # Patch in scheduler module where it's imported
    with patch(
        "denis_unified_v1.kernel.scheduler.get_internet_health",
        return_value=mock_health,
    ):
        scheduler = ModelScheduler()

        request = InferenceRequest(
            request_id="test_offline",
            session_id="test",
            route_type="fast_talk",
            task_type="chat",
            payload={"max_tokens": 512},
        )

        plan = scheduler.assign(request)

        # Verify: internet is DOWN and boosters skipped
        assert plan.trace_tags.get("internet_status_at_plan") == "DOWN"

        # Boosters should NOT be in fallback list
        registry = get_engine_registry()
        booster_ids = [
            eid
            for eid, e in registry.items()
            if "internet_required" in e.get("tags", [])
        ]

    for booster_id in booster_ids:
        assert booster_id not in plan.fallback_engine_ids, (
            f"Booster {booster_id} should be skipped when internet is DOWN"
        )

    print(
        f"✓ Offline test passed: primary={plan.primary_engine_id}, fallbacks={list(plan.fallback_engine_ids)}"
    )


def test_online_allows_boosters_after_local_fail():
    """Test: When internet is OK, boosters are in fallback list."""
    reset_registry()

    mock_health = MockHealth("OK")

    # Patch in scheduler module where it's imported
    with patch(
        "denis_unified_v1.kernel.scheduler.get_internet_health",
        return_value=mock_health,
    ):
        scheduler = ModelScheduler()

        request = InferenceRequest(
            request_id="test_online",
            session_id="test",
            route_type="fast_talk",
            task_type="chat",
            payload={"max_tokens": 512},
        )

        plan = scheduler.assign(request)

        # Verify: primary is local, boosters in fallbacks
        registry = get_engine_registry()
        booster_ids = [
            eid
            for eid, e in registry.items()
            if "internet_required" in e.get("tags", [])
        ]

        # Primary should be local (lowest priority)
        assert plan.primary_engine_id.startswith("llamacpp_"), (
            f"Primary should be local, got {plan.primary_engine_id}"
        )

        # At least one booster should be in fallbacks
        boosters_in_fallbacks = [
            b for b in booster_ids if b in plan.fallback_engine_ids
        ]
        assert len(boosters_in_fallbacks) > 0, (
            "Boosters should be in fallbacks when internet is OK"
        )

        print(
            f"✓ Online test passed: primary={plan.primary_engine_id}, fallbacks={list(plan.fallback_engine_ids)}"
        )


def test_router_skips_internet_required_when_offline():
    """Test: Router skips engines with internet_required tag when offline."""
    reset_registry()

    mock_health = MockHealth("DOWN")

    # Patch for offline in both modules
    with patch(
        "denis_unified_v1.kernel.internet_health.get_internet_health",
        return_value=mock_health,
    ):
        with patch(
            "denis_unified_v1.kernel.scheduler.get_internet_health",
            return_value=mock_health,
        ):
            router = InferenceRouter()

        # Mock the generate method to avoid actual calls
        for eid, e in router.engine_registry.items():
            if e.get("provider_key") == "llamacpp":
                mock_client = AsyncMock()
                mock_client.generate.return_value = {
                    "response": "error",
                    "input_tokens": 1,
                    "output_tokens": 1,
                }
                e["client"] = mock_client
                e["client"].is_available = lambda: True

        import asyncio

        result = asyncio.run(
            router.route_chat(
                messages=[{"role": "user", "content": "test"}],
                request_id="test_router",
                inference_plan=None,
            )
        )

    # When offline, should NOT use groq (internet_required)
    assert result.get("llm_used") != "groq", (
        f"Should not use groq when offline, got {result.get('llm_used')}"
    )

    print(f"✓ Router offline test passed: llm_used={result.get('llm_used')}")


if __name__ == "__main__":
    test_offline_skips_boosters()
    test_online_allows_boosters_after_local_fail()
    test_router_skips_internet_required_when_offline()
    print("\n✅ All internet gate tests passed!")
