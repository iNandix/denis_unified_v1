"""Smoke test for Denis Middleware API."""

import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_middleware_status():
    """Test /middleware/status endpoint."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/middleware/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["mode"] == "low_impact"


def test_middleware_prepare():
    """Test /middleware/prepare endpoint."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/middleware/prepare",
        json={
            "session_id": "test-session",
            "user_text": "Write a function to sort an array in Python",
            "target_provider": "openrouter",
            "target_model": "qwen3-coder",
            "budget": {"max_prompt_tokens": 20000, "max_output_tokens": 1500},
            "artifacts": [],
            "repo_context": {},
            "mode": "low_impact",
            "output_preference": "json",
            "risk_level": "low",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "prepared_prompt" in data
    assert "contextpack" in data
    assert "recommended" in data
    assert "trace_ref" in data
    assert data["contextpack"]["intent"] == "write_code"
    assert "python" in data["contextpack"]["constraints"]


def test_middleware_prepare_intent_classification():
    """Test intent classification in prepare endpoint."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    test_cases = [
        ("Fix the bug in login", "fix_bug"),
        ("Refactor this function", "refactor"),
        ("Explain how this works", "explain"),
        ("Write tests for the API", "write_tests"),
    ]

    for text, expected_intent in test_cases:
        response = client.post(
            "/middleware/prepare",
            json={
                "session_id": "test-session",
                "user_text": text,
                "target_provider": "openrouter",
                "target_model": "qwen3-coder",
                "budget": {"max_prompt_tokens": 20000, "max_output_tokens": 1500},
                "artifacts": [],
                "mode": "low_impact",
            },
        )
        data = response.json()
        assert data["contextpack"]["intent"] == expected_intent, f"Failed for: {text}"


def test_middleware_postprocess():
    """Test /middleware/postprocess endpoint."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/middleware/postprocess",
        json={
            "session_id": "test-session",
            "target_model": "qwen3-coder",
            "raw_output": '{"result": "success"}',
            "output_mode": "json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["parse_ok"] == True
    assert "final_output" in data
    assert len(data["repairs_applied"]) == 0


def test_middleware_postprocess_invalid_json():
    """Test JSON repair in postprocess."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/middleware/postprocess",
        json={
            "session_id": "test-session",
            "target_model": "qwen3-coder",
            "raw_output": "{'result': 'success'}",
            "output_mode": "json",
        },
    )

    data = response.json()
    assert data["parse_ok"] == True
    assert len(data["repairs_applied"]) > 0


def test_intent_project_health_check():
    """Test project_health_check intent resolution.

    Covers: original triggers + newly added triggers (ES + EN).
    Mapping: project_health_check -> incident_triage, shallow_scan, read_only.
    """
    from api.middleware_api import _resolve_intent_legacy, _resolve_intent_from_graph

    test_cases = [
        # A) Original long prompt
        "analiza el directorio /media/jotah/SSD_denis/home_jotah/denis_unified_v1 y dime el estado en que se encuentra y los proximos pasos sugeridos",
        # B) Short "estado del repo"
        "estado del repo",
        # Existing triggers
        "estado del proyecto",
        "próximos pasos sugeridos",
        "dime el estado del proyecto",
        "health check del repositorio",
        # New triggers (ES)
        "revisa el proyecto y dime qué falta",
        "audita el repo de denis",
        "revisar el repositorio para ver su estado",
        "estado del repositorio",
        # New triggers (EN)
        "repo health of denis_unified_v1",
        "audit the repo and report status",
    ]

    for text in test_cases:
        legacy = _resolve_intent_legacy(text)
        graph = _resolve_intent_from_graph(text, "support", "DISCOVERY")

        assert legacy[0] == "project_health_check", f"Legacy failed for: {text}"
        assert graph["intent"] == "project_health_check", f"Graph failed for: {text}"
        assert graph["task_profile_id"] == "incident_triage", (
            f"Task profile wrong for: {text}"
        )

    # Verify phase is shallow_scan
    legacy_phase = _resolve_intent_legacy("estado del repo")
    assert legacy_phase[1] == "shallow_scan", (
        f"Phase should be shallow_scan, got {legacy_phase[1]}"
    )


def test_intent_git_work():
    """Test git_work intent resolution (regression check).

    C) "haz un PR para actualizar X" -> git_work
    D) "git status del repo" -> git_work
    Decision: "git status" contains "git" which is a git_work trigger.
    Even though it also contains "repo", the git keyword should take precedence
    because the legacy resolver checks project_health_check keywords first,
    and "git status del repo" does NOT contain any health check keyword
    (it contains "repo" but not "estado del repo" as a phrase).
    """
    from api.middleware_api import _resolve_intent_legacy, _resolve_intent_from_graph

    test_cases = [
        # C) PR creation -> git_work
        ("haz un PR para actualizar X", "git_work"),
        # D) git status -> git_work (not project_health_check)
        ("git status del repo", "git_work"),
        # More git_work cases
        ("haz commit de los cambios", "git_work"),
        ("push al remote", "git_work"),
        ("pull de cambios", "git_work"),
        ("merge la rama feature", "git_work"),
        ("crea un pull request", "git_work"),
    ]

    for text, expected in test_cases:
        legacy = _resolve_intent_legacy(text)
        graph = _resolve_intent_from_graph(text, "support", "DISCOVERY")

        assert legacy[0] == expected, f"Legacy failed for: {text} (got {legacy[0]})"
        assert graph["intent"] == expected, (
            f"Graph failed for: {text} (got {graph['intent']})"
        )


def test_intent_boundary_health_vs_git():
    """Boundary test: prompts that could match both health check and git_work.

    The rule is: project_health_check keywords are checked BEFORE git_work,
    but git-specific keywords (commit, push, PR) should still route to git_work
    because they contain explicit git action words.
    """
    from api.middleware_api import _resolve_intent_legacy

    # These should be project_health_check (no git action words)
    health_prompts = [
        "estado del repo",
        "revisa el proyecto",
        "health check del repositorio",
    ]
    for text in health_prompts:
        result = _resolve_intent_legacy(text)
        assert result[0] == "project_health_check", (
            f"Should be project_health_check: {text} (got {result[0]})"
        )

    # These should be git_work (explicit git action words)
    git_prompts = [
        "haz un PR del repo",
        "git status del repo",
        "push los cambios del proyecto",
    ]
    for text in git_prompts:
        result = _resolve_intent_legacy(text)
        assert result[0] == "git_work", f"Should be git_work: {text} (got {result[0]})"


def test_intent_system_health_check():
    """Test system_health_check intent (no repo access needed).

    ES: "salud del sistema", "estado del sistema"
    EN: "system health", "system status"
    """
    from api.middleware_api import _resolve_intent_legacy, _resolve_intent_from_graph

    es_prompts = [
        "salud del sistema",
        "estado del sistema",
        "verificar el sistema",
    ]

    en_prompts = [
        "system health",
        "system status",
        "check system health",
    ]

    for text in es_prompts + en_prompts:
        legacy = _resolve_intent_legacy(text)
        graph = _resolve_intent_from_graph(text, "support", "DISCOVERY")

        assert legacy[0] == "system_health_check", f"Legacy failed for: {text}"
        assert graph["intent"] == "system_health_check", f"Graph failed for: {text}"
        assert legacy[1] == "local", f"Phase should be local for: {text}"

    # Verify needs_repo = false (system health doesn't need repo)
    graph = _resolve_intent_from_graph("salud del sistema", "support", "DISCOVERY")
    assert graph["tool_policy_id"] == "system_readonly"


def test_intent_repo_structure_explore():
    """Test repo_structure_explore intent (repo access needed).

    ES: "estructura del repositorio", "explora el repositorio"
    EN: "repo structure", "file structure"

    Note: "revisa el repositorio" maps to project_health_check (review/check)
    because it's about checking/reviewing, not just exploring structure.
    """
    from api.middleware_api import _resolve_intent_legacy, _resolve_intent_from_graph

    es_prompts = [
        "estructura del repositorio",
        "explora el repositorio",
    ]

    en_prompts = [
        "repo structure",
        "file structure",
        "folder structure",
    ]

    for text in es_prompts + en_prompts:
        legacy = _resolve_intent_legacy(text)
        graph = _resolve_intent_from_graph(text, "builder", "DISCOVERY")

        assert legacy[0] == "repo_structure_explore", f"Legacy failed for: {text}"
        assert graph["intent"] == "repo_structure_explore", f"Graph failed for: {text}"
        assert legacy[1] == "shallow_scan", f"Phase should be shallow_scan for: {text}"

    # Verify needs_repo = true (structure exploration needs repo)
    graph = _resolve_intent_from_graph("repo structure", "builder", "DISCOVERY")
    assert graph["tool_policy_id"] == "code_analysis"


def test_intent_resolve_endpoint_contract():
    """Test that /middleware/intent/resolve returns all contract fields.

    Required fields:
    - intent_legacy
    - phase_legacy
    - intent_graph
    - phase_graph
    - task_profile_id
    - tool_policy_id
    - discrepancy
    - confidence
    - latency_ms
    """
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/middleware/intent/resolve",
        json={
            "prompt": "salud del sistema",
            "bot_profile": "support",
            "journey_state": "DISCOVERY",
            "session_id": "test-contract",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Verify all contract fields are present
    required_fields = [
        "intent_legacy",
        "phase_legacy",
        "intent_graph",
        "phase_graph",
        "task_profile_id",
        "tool_policy_id",
        "discrepancy",
        "confidence",
        "latency_ms",
    ]

    for field in required_fields:
        assert field in data, f"Missing contract field: {field}"

    # Verify values
    assert data["intent_legacy"] == "system_health_check"
    assert data["phase_legacy"] == "local"
    assert data["intent_graph"] == "system_health_check"
    assert data["phase_graph"] == "local"
    assert data["tool_policy_id"] == "system_readonly"
    assert data["discrepancy"] == False
    assert data["confidence"] in ["high", "medium", "low"]
    assert data["latency_ms"] >= 0


def test_intent_resolve_discrepancy_tracking():
    """Test that discrepancies are tracked when legacy != graph."""
    from api.middleware_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Test known discrepancy case (if any)
    response = client.post(
        "/middleware/intent/resolve",
        json={
            "prompt": "salud del sistema",
            "bot_profile": "support",
            "journey_state": "DISCOVERY",
            "session_id": "test-disc",
        },
    )

    data = response.json()
    # When legacy == graph, discrepancy should be False
    if data["intent_legacy"] == data["intent_graph"]:
        assert data["discrepancy"] == False
    else:
        assert data["discrepancy"] == True
        assert data["discrepancy_reason"] is not None


def test_intent_discrepancy_logging():
    """Test that legacy and graph agree (discrepancy=false)."""
    from api.middleware_api import _resolve_intent_legacy, _resolve_intent_from_graph

    prompts = [
        "analiza el directorio /media/jotah/SSD_denis/home_jotah/denis_unified_v1 y dime el estado en que se encuentra y los proximos pasos sugeridos",
        "estado del proyecto",
        "estado del repo",
    ]
    for prompt in prompts:
        legacy = _resolve_intent_legacy(prompt)
        graph = _resolve_intent_from_graph(prompt, "support", "DISCOVERY")
        assert legacy[0] == graph["intent"], (
            f"Discrepancy for '{prompt[:60]}...': legacy={legacy[0]} graph={graph['intent']}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
