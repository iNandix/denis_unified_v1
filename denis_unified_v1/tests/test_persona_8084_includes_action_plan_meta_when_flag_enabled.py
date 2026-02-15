import os

from fastapi.testclient import TestClient

from denis_unified_v1.persona.service_8084 import app

from unittest.mock import patch

def test_persona_8084_includes_action_plan_meta_when_flag_enabled():
    os.environ["DENIS_ENABLE_ACTION_PLANNER"] = "1"
    try:
        with patch('denis_unified_v1.persona.service_8084.InferenceRouter') as mock_router_class:
            mock_router = mock_router_class.return_value
            mock_router.route_chat.return_value = {
                "response": "mocked response",
                "llm_used": "mocked_llm",
                "engine_id": "mocked_engine",
                "model_selected": "mocked_model",
                "latency_ms": 100,
                "input_tokens": 10,
                "output_tokens": 10,
                "cost_usd": 0.0,
                "fallback_used": False,
                "attempts": 1,
                "degraded": False,
                "skipped_engines": [],
                "internet_status": "OK"
            }
            client = TestClient(app)
            response = client.post("/chat", json={"message": "test", "user_id": "1", "group_id": "1"})
            assert response.status_code == 200
            data = response.json()
            assert "meta" in data
            meta = data["meta"]
            assert "selected_candidate_id" in meta
            assert "candidates" in meta
    finally:
        del os.environ["DENIS_ENABLE_ACTION_PLANNER"]
