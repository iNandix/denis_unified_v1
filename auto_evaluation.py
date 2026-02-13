from typing import Dict, List, Any

class AutoEvaluator:
    def evaluate(self, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not changes:
            return {"overall_score": 0.0, "evaluated_changes": 0, "recommendations": ["no_changes"]}
        success_rate = sum(bool(c.get("success", False)) for c in changes) / len(changes)
        return {
            "overall_score": success_rate,
            "evaluated_changes": len(changes),
            "recommendations": ["improve error handling"] if success_rate < 0.8 else [],
        }

class ABTester:
    def test(self, variant_a: Dict[str, Any], variant_b: Dict[str, Any]) -> Dict[str, Any]:
        a_score = float(variant_a.get("score", 0.5))
        b_score = float(variant_b.get("score", 0.5))
        winner = "A" if a_score > b_score else "B"
        return {"winner": winner, "a_score": a_score, "b_score": b_score, "confidence": 0.9}

class FeedbackLoopCloser:
    def close(self, evaluation: Dict[str, Any], ab_test: Dict[str, Any]) -> Dict[str, Any]:
        actions = []
        if evaluation.get("overall_score", 0.0) < 0.8:
            actions.append("rollback_changes")
        if ab_test.get("winner") == "B":
            actions.append("adopt_variant_b")
        return {"actions_taken": actions, "loop_closed": True}

def process_evaluation(
    changes: List[Dict[str, Any]],
    variant_a: Dict[str, Any],
    variant_b: Dict[str, Any],
) -> Dict[str, Any]:
    evaluator = AutoEvaluator()
    ab_tester = ABTester()
    closer = FeedbackLoopCloser()

    evaluation = evaluator.evaluate(changes)
    ab_test = ab_tester.test(variant_a, variant_b)
    loop_close = closer.close(evaluation, ab_test)

    return {"evaluation": evaluation, "ab_test": ab_test, "loop_close": loop_close}
