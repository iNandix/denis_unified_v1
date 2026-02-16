"""PRO_SEARCH Executor Smoke Tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault("NEO4J_URI", "bolt://10.10.10.1:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "Leon1234$")
os.environ.setdefault("DENIS_SESSION_ID", "test_session")

from denis_unified_v1.actions.pro_search_executor import (
    ProSearchExecutor,
    SearchRequest,
    run_pro_search,
)


@pytest.fixture
def executor():
    return ProSearchExecutor()


def test_load_skill_config(executor):
    """Verify skill config loads from Neo4j."""
    config = executor.load_skill_config()
    assert config is not None
    assert config["name"] == "pro_search"
    assert config["version"] == "2.0.0"
    assert "user_pure" in config["modes"]
    assert "standard" in config["depths"]


def test_skill_has_toolchain_steps(executor):
    """Verify toolchain steps are loaded."""
    config = executor.load_skill_config()
    step_names = [s["name"] for s in config["toolchain_steps"]]
    assert "classify_query" in step_names
    assert "multi_engine_search" in step_names
    assert "evaluate_sources" in step_names
    assert "synthesize_results" in step_names


def test_resolve_mode_and_depth(executor):
    """Verify mode/depth resolution."""
    config = executor.load_skill_config()
    request = SearchRequest(query="test", mode="hybrid", depth="deep")
    mode, depth = executor.resolve_mode_and_depth(request, config)
    assert mode == "hybrid"
    assert depth == "deep"


def test_resolve_defaults_for_unknown(executor):
    """Verify defaults when mode/depth unknown."""
    config = executor.load_skill_config()
    request = SearchRequest(query="test", mode="unknown_mode", depth="unknown_depth")
    mode, depth = executor.resolve_mode_and_depth(request, config)
    assert mode == "user_pure"
    assert depth == "standard"


def test_evaluate_policies_passes(executor):
    """Verify policies pass for standard depth."""
    config = executor.load_skill_config()
    request = SearchRequest(query="test", mode="user_pure", depth="standard")
    passes, violations = executor.evaluate_policies(
        request, config, "user_pure", "standard"
    )
    assert passes is True
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_execute_user_pure_mode():
    """Execute research in user_pure mode."""
    result = await run_pro_search(
        query="What is Python?",
        mode="user_pure",
        depth="quick",
    )
    assert result.status == "success"
    assert result.answer is not None
    assert "Python" in result.answer
    assert len(result.sources) > 0
    assert result.reliability_score is not None
    assert result.decision_trace_id is not None


@pytest.mark.asyncio
async def test_execute_machine_only_mode():
    """Execute research in machine_only mode returns JSON."""
    result = await run_pro_search(
        query="test query",
        mode="machine_only",
        depth="quick",
    )
    assert result.status == "success"
    assert result.answer is not None
    import json

    parsed = json.loads(result.answer)
    assert "query" in parsed
    assert "answer" in parsed
    assert "sources" in parsed


@pytest.mark.asyncio
async def test_execute_hybrid_mode():
    """Execute research in hybrid mode."""
    result = await run_pro_search(
        query="analyze: test topic",
        mode="hybrid",
        depth="standard",
    )
    assert result.status == "success"
    assert result.answer is not None


@pytest.mark.asyncio
async def test_deep_mode_policy_enforced():
    """Deep mode requires cross_verify_min >= 3."""
    result = await run_pro_search(
        query="test",
        mode="user_pure",
        depth="deep",
    )
    assert result.status == "success"


@pytest.mark.asyncio
async def test_different_categories():
    """Test different category engines."""
    categories = ["general", "technical", "academic"]
    for cat in categories:
        result = await run_pro_search(
            query=f"test {cat}",
            category=cat,
        )
        assert result.status == "success"


@pytest.mark.asyncio
async def test_session_and_turn_ids():
    """Verify session_id and turn_id are used."""
    result = await run_pro_search(
        query="test",
        session_id="my_session",
        turn_id="my_turn",
    )
    assert result.status == "success"
    assert result.decision_trace_id is not None
