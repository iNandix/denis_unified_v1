"""Tests for WS10-G: Graph-first Intent/Plan/Tasks creation.

Covers:
- Intent node creation with sha256(user_text)
- Plan node linked to Intent
- 4 Tasks (S1-S4) linked to Plan
- Idempotency (same turn_id => no duplication)
- Fail-open (graph disabled => returns warning)
- No raw user text stored in graph
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch


def test_create_intent_stores_hash_not_raw_text(monkeypatch):
    """WS10-G: Intent node must store sha256, not raw text."""
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")

    captured_cypher = []

    def mock_run_write(cypher, params=None):
        captured_cypher.append({"cypher": cypher, "params": params})
        return True

    with patch("denis_unified_v1.graph.graph_client.get_graph_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.run_write = mock_run_write
        mock_gc.return_value = mock_client

        from denis_unified_v1.graph.graph_intent_plan import create_intent

        ok, intent_id = create_intent(
            conversation_id="conv1",
            turn_id="turn1",
            user_text="my secret password 12345",
            modality="text",
        )

        assert ok is True
        assert intent_id is not None
        assert "my secret" not in str(captured_cypher)
        assert "sha256" in str(captured_cypher).lower()


def test_create_plan_links_to_intent(monkeypatch):
    """WS10-G: Plan node must be linked to Intent via HAS_PLAN edge."""
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")

    captured_cypher = []

    def mock_run_write(cypher, params=None):
        captured_cypher.append({"cypher": cypher, "params": params})
        return True

    with patch("denis_unified_v1.graph.graph_client.get_graph_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.run_write = mock_run_write
        mock_gc.return_value = mock_client

        from denis_unified_v1.graph.graph_intent_plan import create_plan

        ok, plan_id = create_plan(
            intent_id="abc123",
            specialties=["S1", "S2", "S3", "S4"],
        )

        assert ok is True
        assert plan_id == "abc123:plan"
        edge_cypher = [c["cypher"] for c in captured_cypher]
        assert any("HAS_PLAN" in c for c in edge_cypher)


def test_create_specialty_tasks_creates_4_tasks(monkeypatch):
    """WS10-G: Must create exactly 4 tasks, one per specialty."""
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")

    captured_tasks = []

    def mock_run_write(cypher, params=None):
        if "Task" in cypher and "MERGE" in cypher:
            captured_tasks.append(params.get("specialty"))
        return True

    with patch("denis_unified_v1.graph.graph_client.get_graph_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.run_write = mock_run_write
        mock_gc.return_value = mock_client

        from denis_unified_v1.graph.graph_intent_plan import create_specialty_tasks

        ok, task_ids = create_specialty_tasks(
            plan_id="plan1",
            intent_id="intent1",
            conversation_id="conv1",
            turn_id="turn1",
        )

        assert ok is True
        assert len(task_ids) == 4
        assert len(captured_tasks) == 4
        assert "S1_CORE_GRAPH_CONTROLROOM" in captured_tasks
        assert "S2_VOICE_PIPECAT" in captured_tasks
        assert "S3_FRONT_UI_VISUALIZATION" in captured_tasks
        assert "S4_GOV_OPS_SAFETY" in captured_tasks


def test_full_flow_returns_correct_structure(monkeypatch):
    """WS10-G: Full flow returns intent_id, plan_id, task_ids."""
    call_count = 0

    def mock_run_write(cypher, params=None):
        nonlocal call_count
        call_count += 1
        return True

    with patch("denis_unified_v1.graph.graph_client.get_graph_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.run_write = mock_run_write
        mock_gc.return_value = mock_client

        from denis_unified_v1.graph.graph_intent_plan import create_intent_plan_tasks

        result = create_intent_plan_tasks(
            conversation_id="conv_test",
            turn_id="turn_test",
            user_text="hello world",
        )

        assert result["success"] is True
        assert result["intent_id"] is not None
        assert result["plan_id"] is not None
        assert len(result["task_ids"]) == 4
        assert result["warning"] is None


def test_fail_open_when_graph_disabled(monkeypatch):
    """WS10-G: If graph disabled, returns warning but no crash."""
    monkeypatch.setenv("GRAPH_ENABLED", "0")

    from denis_unified_v1.graph.graph_intent_plan import create_intent_plan_tasks

    result = create_intent_plan_tasks(
        conversation_id="conv1",
        turn_id="turn1",
        user_text="test",
    )

    assert result["success"] is False
    assert result["warning"] == "graph_unavailable"


def test_idempotency_same_turn_id(monkeypatch):
    """WS10-G: Same turn_id should MERGE (not duplicate)."""
    monkeypatch.setenv("GRAPH_ENABLED", "1")
    monkeypatch.setenv("NEO4J_PASSWORD", "test_pass")

    merge_count = 0

    def mock_run_write(cypher, params=None):
        nonlocal merge_count
        if "MERGE" in cypher:
            merge_count += 1
        return True

    with patch("denis_unified_v1.graph.graph_client.get_graph_client") as mock_gc:
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.run_write = mock_run_write
        mock_gc.return_value = mock_client

        from denis_unified_v1.graph.graph_intent_plan import (
            create_intent,
            create_plan,
            create_specialty_tasks,
        )

        conv_id = "conv1"
        turn_id = "turn1"

        create_intent(conversation_id=conv_id, turn_id=turn_id, user_text="test1")
        create_intent(conversation_id=conv_id, turn_id=turn_id, user_text="test2")

        first_calls = merge_count

        create_plan(intent_id=f"{conv_id}:{turn_id}")
        create_plan(intent_id=f"{conv_id}:{turn_id}")

        assert merge_count > first_calls
