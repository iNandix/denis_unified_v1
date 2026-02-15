"""Intent accuracy smoke tests - Updated for Unified Parser.

Tests that IntentV1 parser achieves >=90% accuracy on golden dataset.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
from datetime import datetime, timezone

from denis_unified_v1.intent.unified_parser import parse_intent
from denis_unified_v1.intent.intent_v1 import IntentType
from tests.evals.intent_eval_dataset import (
    INTENT_EVAL_DATASET,
    TOTAL_PROMPTS,
    EXPECTED_ACCURACY,
)


def test_intent_accuracy_smoke():
    """Test intent classification accuracy on golden dataset."""
    print("=" * 70)
    print("INTENT ACCURACY SMOKE TEST (Unified Parser)")
    print("=" * 70)

    results = {
        "total": 0,
        "correct_intent": 0,
        "correct_confidence": 0,
        "both_correct": 0,
        "by_intent": {},
        "failures": [],
    }

    for item in INTENT_EVAL_DATASET:
        prompt = item["prompt"]
        expected_intent = item["expected_intent"]
        expected_confident = item["expected_confident"]
        notes = item.get("notes", "")

        # Parse intent using unified parser
        intent = parse_intent(prompt)

        results["total"] += 1

        # Track by intent type
        intent_key = expected_intent
        if intent_key not in results["by_intent"]:
            results["by_intent"][intent_key] = {
                "total": 0,
                "correct": 0,
                "confidence_correct": 0,
            }
        results["by_intent"][intent_key]["total"] += 1

        # Check intent accuracy
        intent_correct = intent.intent.value == expected_intent
        if intent_correct:
            results["correct_intent"] += 1
            results["by_intent"][intent_key]["correct"] += 1

        # Check confidence accuracy
        confidence_correct = intent.is_confident == expected_confident
        if confidence_correct:
            results["correct_confidence"] += 1
            results["by_intent"][intent_key]["confidence_correct"] += 1

        # Both correct
        if intent_correct and confidence_correct:
            results["both_correct"] += 1
        else:
            results["failures"].append(
                {
                    "prompt": prompt,
                    "expected": expected_intent,
                    "got": intent.intent.value,
                    "expected_confident": expected_confident,
                    "got_confident": intent.is_confident,
                    "confidence": intent.confidence,
                    "notes": notes,
                }
            )

    # Calculate metrics
    intent_accuracy = results["correct_intent"] / results["total"]
    confidence_accuracy = results["correct_confidence"] / results["total"]
    overall_accuracy = results["both_correct"] / results["total"]

    # Print results
    print(f"\n📊 OVERALL METRICS")
    print(f"  Total prompts: {results['total']}")
    print(
        f"  Intent accuracy: {intent_accuracy:.1%} ({results['correct_intent']}/{results['total']})"
    )
    print(
        f"  Confidence accuracy: {confidence_accuracy:.1%} ({results['correct_confidence']}/{results['total']})"
    )
    print(
        f"  Both correct: {overall_accuracy:.1%} ({results['both_correct']}/{results['total']})"
    )
    print(f"  Target: ≥{EXPECTED_ACCURACY:.0%}")

    print(f"\n📈 BY INTENT TYPE")
    for intent_type, stats in sorted(results["by_intent"].items()):
        if stats["total"] > 0:
            intent_acc = stats["correct"] / stats["total"]
            print(
                f"  {intent_type:20s}: {intent_acc:5.1%} ({stats['correct']}/{stats['total']})"
            )

    if results["failures"]:
        print(f"\n❌ FAILURES ({len(results['failures'])})")
        for f in results["failures"][:10]:  # Show first 10
            print(f"\n  Prompt: {f['prompt'][:60]}...")
            print(
                f"    Expected: {f['expected']} (confident={f['expected_confident']})"
            )
            print(
                f"    Got:      {f['got']} (confident={f['got_confident']}, conf={f['confidence']:.2f})"
            )
            print(f"    Notes:    {f['notes']}")

    # Save snapshot
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "total": results["total"],
            "intent_accuracy": round(intent_accuracy, 3),
            "confidence_accuracy": round(confidence_accuracy, 3),
            "overall_accuracy": round(overall_accuracy, 3),
            "target": EXPECTED_ACCURACY,
        },
        "by_intent": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"], 3)
                if v["total"] > 0
                else 0,
            }
            for k, v in results["by_intent"].items()
        },
        "failures_count": len(results["failures"]),
    }

    snapshot_path = Path("denis_unified_v1/_reports/intent_accuracy_snapshot.json")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n💾 Snapshot saved: {snapshot_path}")

    # Assert target met
    print("\n" + "=" * 70)
    if overall_accuracy >= EXPECTED_ACCURACY:
        print(
            f"✅ PASS: Overall accuracy {overall_accuracy:.1%} >= {EXPECTED_ACCURACY:.0%}"
        )
        print("=" * 70)
        return True
    else:
        print(
            f"❌ FAIL: Overall accuracy {overall_accuracy:.1%} < {EXPECTED_ACCURACY:.0%}"
        )
        print("=" * 70)
        return False


def test_specific_intents():
    """Test specific intent classifications."""
    test_cases = [
        ("pytest falla en test_user.py", IntentType.RUN_TESTS_CI, True),
        ("Hay un traceback en el log", IntentType.DEBUG_REPO, True),
        ("Necesito migrar a FastAPI", IntentType.REFACTOR_MIGRATION, True),
        ("Implementa un endpoint nuevo", IntentType.IMPLEMENT_FEATURE, True),
        ("Verifica el estado del sistema", IntentType.OPS_HEALTH_CHECK, True),
        ("Explica cómo funciona el router", IntentType.EXPLAIN_CONCEPT, True),
        ("Hay un incidente en producción", IntentType.INCIDENT_TRIAGE, True),
        ("Actualiza la imagen Docker", IntentType.TOOLCHAIN_TASK, True),
        ("Escribe documentación", IntentType.WRITE_DOCS, True),
        ("Hola", IntentType.UNKNOWN, False),
    ]

    print("\n🎯 SPECIFIC INTENT TESTS")
    print("-" * 70)

    all_pass = True
    for prompt, expected_intent, expected_confident in test_cases:
        intent = parse_intent(prompt)

        intent_ok = intent.intent == expected_intent
        conf_ok = intent.is_confident == expected_confident

        status = "✅" if (intent_ok and conf_ok) else "❌"
        if not (intent_ok and conf_ok):
            all_pass = False

        print(f"\n{status} {expected_intent.value:20s} (conf={expected_confident})")
        if not intent_ok:
            print(f"   Expected: {expected_intent.value}")
            print(f"   Got:      {intent.intent.value}")
        if not conf_ok:
            print(f"   Expected confident: {expected_confident}")
            print(
                f"   Got confident: {intent.is_confident} (conf={intent.confidence:.2f})"
            )

    print("-" * 70)
    return all_pass


def test_extended_fields():
    """Test that extended fields are populated."""
    print("\n🔍 EXTENDED FIELDS TEST")
    print("-" * 70)

    prompt = "pytest me da error en test_router.py línea 45, necesito debuggear"
    intent = parse_intent(prompt)

    checks = {
        "intent": intent.intent is not None,
        "confidence": 0 <= intent.confidence <= 1,
        "confidence_band": intent.confidence_band in ["high", "medium", "low"],
        "entities": len(intent.entities) > 0,
        "sources": len(intent.sources) > 0,
        "reason_codes": len(intent.reason_codes) > 0,
        "tone": intent.tone is not None,
        "risk": intent.risk is not None,
        "acceptance_criteria": len(intent.acceptance_criteria) > 0,
        "parsed_at": intent.parsed_at is not None,
    }

    all_pass = True
    for field, ok in checks.items():
        status = "✅" if ok else "❌"
        if not ok:
            all_pass = False
        print(f"  {status} {field}")

    # Show actual values
    print(f"\n  Intent: {intent.intent.value}")
    print(f"  Confidence: {intent.confidence:.2f} ({intent.confidence_band})")
    print(f"  Tone: {intent.tone.value}")
    print(f"  Risk: {intent.risk.value}")
    print(f"  Entities: {[e.type + ':' + e.value for e in intent.entities[:3]]}")
    print(f"  Sources: {list(intent.sources.keys())}")
    print(f"  Reason codes: {[r.value for r in intent.reason_codes]}")

    print("-" * 70)
    return all_pass


if __name__ == "__main__":
    success1 = test_intent_accuracy_smoke()
    success2 = test_specific_intents()
    success3 = test_extended_fields()

    if success1 and success2 and success3:
        print("\n🎉 ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n💥 SOME TESTS FAILED")
        sys.exit(1)
