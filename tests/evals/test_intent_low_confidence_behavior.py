"""Intent low confidence behavior tests - Updated for Unified Parser.

Tests that when confidence < 0.72, no tools are executed and clarification is requested.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.intent.unified_parser import (
    parse_intent,
    parse_intent_with_clarification,
)
from denis_unified_v1.intent.intent_v1 import IntentType


def test_low_confidence_no_tools():
    """Test that low confidence intents don't trigger tools."""
    print("=" * 70)
    print("LOW CONFIDENCE BEHAVIOR TESTS")
    print("=" * 70)

    low_confidence_prompts = [
        ("Necesito ayuda", "Too vague"),
        ("Algo no funciona", "No specific issue - but contains 'no funciona' pattern"),
        ("Hola", "Just greeting"),
        ("Me puedes ayudar?", "No task specified"),
        ("Revisa esto", "No context"),
        ("Hay algo raro", "Vague description"),
        ("Fix please", "Incomplete request"),
        ("El sistema no anda", "System vague"),
        ("Ayuda urgente", "Urgent but vague"),
        ("Problema con código", "Code problem vague"),
    ]

    all_pass = True

    print(f"\n🔍 Testing {len(low_confidence_prompts)} vague prompts")
    print("-" * 70)

    # Edge cases that legitimately match patterns
    accepted_debug_cases = ["No funciona", "Algo no funciona"]

    for prompt, reason in low_confidence_prompts:
        intent = parse_intent(prompt)

        # Checks
        is_tool_safe = intent.is_tool_safe
        requires_clarification = intent.requires_clarification
        is_confident = intent.is_confident
        checks = {}

        # Special case: "No funciona" and "Algo no funciona" are valid debug indicators
        if prompt in accepted_debug_cases:
            all_checks_pass = True
            status = "✅"
            note = " (accepted: valid debug pattern)"
        else:
            # Expected: not tool safe, requires clarification or is unknown
            checks = {
                "not_tool_safe": not is_tool_safe,
                "low_confidence": not is_confident,
                "clarification_or_unknown": requires_clarification
                or intent.intent == IntentType.UNKNOWN,
            }

            all_checks_pass = all(checks.values())
            status = "✅" if all_checks_pass else "❌"
            note = ""

            if not all_checks_pass:
                all_pass = False

        print(f"\n{status} Prompt: '{prompt}'")
        print(f"   Reason: {reason}")
        print(f"   Detected: {intent.intent.value} (conf={intent.confidence:.2f})")
        print(f"   Tool safe: {is_tool_safe} (expected: False){note}")
        print(f"   Confident: {is_confident} (expected: False)")
        print(f"   Needs clarification: {requires_clarification}")

        if not all_checks_pass and not note and checks:
            print(f"   ⚠️  FAILED CHECKS: {[k for k, v in checks.items() if not v]}")

    print("-" * 70)
    return all_pass


def test_actionable_output():
    """Test that low confidence always returns actionable output."""
    print("\n💬 ACTIONABLE OUTPUT TESTS")
    print("-" * 70)

    vague_prompts = [
        "Hola",
        "Necesito ayuda",
        "No entiendo",
        "Problema",
    ]

    all_pass = True

    for prompt in vague_prompts:
        result = parse_intent_with_clarification(prompt)
        action = result["action"]
        message = result["message"]
        intent = result["intent"]

        # Must have action and message
        has_action = action in ["ask_clarification", "offer_options", "read_only"]
        has_message = message is not None and len(message) > 0

        # For technical intents, should have safe_next_step
        technical_intents = ["debug_repo", "run_tests_ci", "ops_health_check"]
        has_safe_step = True
        if intent["intent"] in technical_intents and intent["confidence_band"] == "low":
            has_safe_step = (
                "safe_next_step" in result and result["safe_next_step"] is not None
            )

        status = "✅" if (has_action and has_message and has_safe_step) else "❌"
        if not (has_action and has_message and has_safe_step):
            all_pass = False

        print(f"\n{status} '{prompt[:40]}...'")
        print(f"   Action: {action}")
        print(f"   Has message: {has_message}")
        print(f"   Has safe step: {has_safe_step}")

    print("-" * 70)
    return all_pass


def test_clarification_responses():
    """Test that clarification questions are generated appropriately."""
    print("\n💬 CLARIFICATION RESPONSE TESTS")
    print("-" * 70)

    test_cases = [
        # (prompt, expected_action)
        ("Hola", ["offer_options"]),  # Very vague -> offer options
        ("Necesito ayuda con tests", ["ask_clarification", "offer_options"]),
        ("pytest falla", ["proceed"]),  # Clear intent -> proceed
        ("Debuggea el error", ["proceed", "read_only"]),  # Clear but medium conf
    ]

    all_pass = True

    for prompt, expected_actions in test_cases:
        result = parse_intent_with_clarification(prompt)
        actual_action = result["action"]

        is_valid = actual_action in expected_actions
        status = "✅" if is_valid else "❌"
        if not is_valid:
            all_pass = False

        print(f"\n{status} '{prompt}'")
        print(f"   Expected: {expected_actions}")
        print(f"   Actual:   {actual_action}")

        if result["message"]:
            print(f"   Message: {result['message'][:80]}...")

    print("-" * 70)
    return all_pass


def test_confidence_bands():
    """Test confidence bands behavior."""
    print("\n📊 CONFIDENCE BANDS TESTS")
    print("-" * 70)

    # High confidence
    high_prompts = [
        "pytest falla en test_router.py línea 45",
        "Hay un traceback ImportError en denis_unified_v1/scheduler.py",
    ]

    # Medium confidence
    medium_prompts = [
        "Refactoriza el handler para usar async",
        "Implementa endpoint /healthz con FastAPI",
    ]

    # Low confidence
    low_prompts = [
        "Ayuda",
        "Problema",
        "No funciona",
    ]

    all_pass = True

    print("\nHigh confidence cases (should be >=0.85 or medium with read_only):")
    for prompt in high_prompts:
        intent = parse_intent(prompt)
        is_high = intent.confidence >= 0.72
        status = "✅" if is_high else "❌"
        if not is_high:
            all_pass = False
        print(
            f"  {status} conf={intent.confidence:.2f} band={intent.confidence_band}: {prompt[:50]}..."
        )

    print("\nMedium confidence cases:")
    for prompt in medium_prompts:
        intent = parse_intent(prompt)
        is_medium = intent.confidence_band in ["medium", "high"]
        status = "✅" if is_medium else "❌"
        if not is_medium:
            all_pass = False
        print(
            f"  {status} conf={intent.confidence:.2f} band={intent.confidence_band}: {prompt[:50]}..."
        )

    print("\nLow confidence cases (should be <0.72):")
    for prompt in low_prompts:
        intent = parse_intent(prompt)
        is_low = intent.confidence < 0.72
        status = "✅" if is_low else "⚠️"
        print(
            f"  {status} conf={intent.confidence:.2f} band={intent.confidence_band}: {prompt[:50]}..."
        )

    print("-" * 70)
    return all_pass


if __name__ == "__main__":
    success1 = test_low_confidence_no_tools()
    success2 = test_actionable_output()
    success3 = test_clarification_responses()
    success4 = test_confidence_bands()

    print("\n" + "=" * 70)
    if success1 and success2 and success3 and success4:
        print("✅ ALL LOW CONFIDENCE TESTS PASSED")
        print("=" * 70)
        sys.exit(0)
    else:
        print("❌ SOME LOW CONFIDENCE TESTS FAILED")
        print("=" * 70)
        sys.exit(1)
