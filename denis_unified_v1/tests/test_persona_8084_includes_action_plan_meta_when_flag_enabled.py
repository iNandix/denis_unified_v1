import os

from fastapi.testclient import TestClient

from denis_unified_v1.persona.service_8084 import app

def test_persona_8084_includes_action_plan_meta_when_flag_enabled():
    os.environ["DENIS_ENABLE_ACTION_PLANNER"] = "1"
    try:
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
