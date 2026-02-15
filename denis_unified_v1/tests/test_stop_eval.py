from denis_unified_v1.actions.stop_eval import eval_stop_condition

from denis_unified_v1.actions.models import StopCondition, StopOp

def test_eval_stop_condition_eq():
    cond = StopCondition(key="exit_code", op=StopOp.eq, value=0)
    assert eval_stop_condition(cond, {"exit_code": 0}) == True
    assert eval_stop_condition(cond, {"exit_code": 1}) == False

def test_eval_stop_condition_exists():
    cond = StopCondition(key="error_lines", op=StopOp.exists)
    assert eval_stop_condition(cond, {"error_lines": []}) == True
    assert eval_stop_condition(cond, {}) == False

def test_eval_stop_condition_is_true():
    cond = StopCondition(key="services_down", op=StopOp.is_true)
    assert eval_stop_condition(cond, {"services_down": True}) == True
    assert eval_stop_condition(cond, {"services_down": False}) == False

def test_eval_stop_condition_gt():
    cond = StopCondition(key="disk_usage_pct", op=StopOp.gt, value=90)
    assert eval_stop_condition(cond, {"disk_usage_pct": 95}) == True
    assert eval_stop_condition(cond, {"disk_usage_pct": 85}) == False
