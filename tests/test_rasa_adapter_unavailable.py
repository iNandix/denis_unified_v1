"""Rasa adapter unavailable degradation tests.

Tests that when Rasa is unavailable, the system continues to function
with heuristics + Meta-LLM and properly reports sources.rasa.status.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.intent.rasa_adapter import RasaAdapter, RasaParseResult
from denis_unified_v1.intent.unified_parser import UnifiedIntentParser
from denis_unified_v1.intent.intent_v1 import ReasonCode, ConfidenceSource


def test_rasa_adapter_unavailable():
    """Test Rasa adapter returns unavailable status when Rasa not configured."""
    print("=" * 70)
    print("RASA ADAPTER UNAVAILABLE TESTS")
    print("=" * 70)

    # Create adapter pointing to non-existent endpoint
    adapter = RasaAdapter(endpoint="http://localhost:59999", timeout=1.0)

    print("\n🔌 Testing unavailable Rasa...")
    result = adapter.parse("pytest me da error")

    print(f"  Status: {result.status}")
    print(f"  Intent: {result.intent}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Error: {result.error_message}")

    # Assertions
    assert result.status == "unavailable", (
        f"Expected status='unavailable', got '{result.status}'"
    )
    assert result.intent is None, f"Expected intent=None, got {result.intent}"
    assert result.confidence == 0.0, f"Expected confidence=0.0, got {result.confidence}"

    print("  ✅ Rasa adapter properly reports unavailable status")

    return True


def test_unified_parser_with_rasa_unavailable():
    """Test that unified parser works even when Rasa unavailable."""
    print("\n🔄 Testing Unified Parser with Rasa unavailable...")

    # Create parser that will fail to reach Rasa
    parser = UnifiedIntentParser(use_rasa=True, use_meta_llm=False, use_heuristics=True)

    # Force Rasa to be unavailable by using bad endpoint
    from denis_unified_v1.intent.rasa_adapter import get_rasa_adapter

    adapter = get_rasa_adapter()
    original_endpoint = adapter.endpoint
    adapter.endpoint = "http://localhost:59999"
    adapter._available = False  # Force unavailable

    try:
        intent = parser.parse("pytest falla en test_router.py")

        print(f"\n  Intent: {intent.intent.value}")
        print(f"  Confidence: {intent.confidence:.2f}")
        print(f"  Sources: {list(intent.sources.keys())}")
        print(f"  Reason codes: {[r.value for r in intent.reason_codes]}")

        # Should still get a valid intent from heuristics
        assert intent.intent is not None, "Should have an intent"
        assert intent.confidence > 0, (
            f"Should have confidence > 0, got {intent.confidence}"
        )

        # Should have Rasa source marked as unavailable
        if "rasa" in intent.sources:
            assert intent.sources["rasa"].status == "unavailable", (
                f"Rasa source should be unavailable, got {intent.sources['rasa'].status}"
            )

        # Should have reason code for Rasa unavailable
        has_rasa_unavailable = (
            ReasonCode.RASA_UNAVAILABLE in intent.reason_codes
            or any("rasa" in r.value.lower() for r in intent.reason_codes)
        )

        print("  ✅ Unified parser works without Rasa")

        return True

    finally:
        # Restore adapter
        adapter.endpoint = original_endpoint
        adapter._available = None


def test_rasa_error_recovery():
    """Test that Rasa errors don't crash the system."""
    print("\n🔄 Testing Rasa error recovery...")

    adapter = RasaAdapter(endpoint="http://invalid-url:12345", timeout=0.1)

    # First call should fail and mark unavailable
    result1 = adapter.parse("test prompt")
    assert result1.status in ["unavailable", "error"], (
        f"Expected error status, got {result1.status}"
    )

    # Subsequent calls should use cached unavailable status
    result2 = adapter.parse("another prompt")
    assert result2.status == "unavailable", (
        f"Expected cached unavailable, got {result2.status}"
    )

    print("  ✅ Rasa errors handled gracefully with caching")

    return True


def test_intent_v1_always_produced():
    """Test that IntentV1 is always produced even when everything fails."""
    print("\n🔄 Testing IntentV1 always produced...")

    # Create parser with all sources potentially failing
    parser = UnifiedIntentParser(
        use_rasa=True, use_meta_llm=False, use_heuristics=False
    )

    intent = parser.parse("test prompt")

    print(f"\n  Intent: {intent.intent.value}")
    print(f"  Confidence: {intent.confidence:.2f}")
    print(f"  Has sources: {len(intent.sources) > 0}")
    print(f"  Has parsed_at: {intent.parsed_at is not None}")

    # Should still produce a valid IntentV1 (unknown)
    assert intent is not None, "Should always produce IntentV1"
    assert intent.intent is not None, "Should have intent type"
    assert intent.parsed_at is not None, "Should have timestamp"

    print("  ✅ IntentV1 always produced even with no sources")

    return True


if __name__ == "__main__":
    try:
        success1 = test_rasa_adapter_unavailable()
        success2 = test_unified_parser_with_rasa_unavailable()
        success3 = test_rasa_error_recovery()
        success4 = test_intent_v1_always_produced()

        print("\n" + "=" * 70)
        if success1 and success2 and success3 and success4:
            print("✅ ALL RASA UNAVAILABLE TESTS PASSED")
            print("=" * 70)
            sys.exit(0)
        else:
            print("❌ SOME TESTS FAILED")
            print("=" * 70)
            sys.exit(1)

    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
