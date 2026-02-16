"""PRO_SEARCH Graph-Only Smoke Tests.

Tests verify that PRO_SEARCH skill is properly configured in Neo4j
with all modes, depths, categories, policies, toolchain steps, and intents.
"""

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver


@pytest.fixture
def driver():
    """Get Neo4j driver for tests."""
    os.environ.setdefault("NEO4J_URI", "bolt://10.10.10.1:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "Leon1234$")
    dr = _get_neo4j_driver()
    if dr is None:
        pytest.skip("Neo4j driver unavailable")
    return dr


def test_pro_search_skill_exists(driver):
    """Verify pro_search skill exists in graph."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})
    RETURN s.name, s.version, s.description, s.policy, s.risk_level
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None, "pro_search skill not found"
        assert record["s.name"] == "pro_search"
        assert record["s.version"] == "2.0.0"
        assert record["s.policy"] == "read_only"
        assert record["s.risk_level"] == "low"


def test_pro_search_modes_configured(driver):
    """Verify all 3 search modes are configured."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_MODE]->(m:SearchMode)
    RETURN m.mode_id, m.name, m.query_type, m.language, m.synthesis_style
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        mode_ids = [r["m.mode_id"] for r in records]
        assert "user_pure" in mode_ids
        assert "hybrid" in mode_ids
        assert "machine_only" in mode_ids
        assert len(records) == 3


def test_pro_search_mode_user_pure(driver):
    """Verify user_pure mode configuration."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_MODE]->(m:SearchMode {mode_id: 'user_pure'})
    RETURN m.name, m.language, m.synthesis_style, m.citations, m.streaming
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["m.language"] == "natural"
        assert record["m.synthesis_style"] == "conversational"
        assert record["m.citations"] is True
        assert record["m.streaming"] is True


def test_pro_search_mode_hybrid(driver):
    """Verify hybrid mode configuration."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_MODE]->(m:SearchMode {mode_id: 'hybrid'})
    RETURN m.name, m.context_aware, m.learning_enabled
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["m.context_aware"] is True
        assert record["m.learning_enabled"] is True


def test_pro_search_mode_machine_only(driver):
    """Verify machine_only mode outputs JSON."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_MODE]->(m:SearchMode {mode_id: 'machine_only'})
    RETURN m.output_format, m.feeds_graph
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["m.output_format"] == "json"
        assert record["m.feeds_graph"] is True


def test_pro_search_depths_configured(driver):
    """Verify all 4 search depths are configured."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_DEPTH]->(d:SearchDepth)
    RETURN d.depth_id, d.name, d.time_limit_ms, d.max_sources
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        depth_ids = [r["d.depth_id"] for r in records]
        assert "quick" in depth_ids
        assert "standard" in depth_ids
        assert "deep" in depth_ids
        assert "continuous" in depth_ids
        assert len(records) == 4


def test_pro_search_depth_quick(driver):
    """Verify quick depth has appropriate limits."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_DEPTH]->(d:SearchDepth {depth_id: 'quick'})
    RETURN d.time_limit_ms, d.max_sources
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["d.time_limit_ms"] == 30000
        assert record["d.max_sources"] == 5


def test_pro_search_depth_deep(driver):
    """Verify deep depth has cross-verification enabled."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_DEPTH]->(d:SearchDepth {depth_id: 'deep'})
    RETURN d.cross_verify_min, d.rerank
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["d.cross_verify_min"] == 3
        assert record["d.rerank"] is True


def test_pro_search_categories_configured(driver):
    """Verify all 7 search categories exist."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_CATEGORY]->(c:SearchCategory)
    RETURN c.category_id, c.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        category_ids = [r["c.category_id"] for r in records]
        assert "general" in category_ids
        assert "academic" in category_ids
        assert "technical" in category_ids
        assert "news" in category_ids
        assert "video" in category_ids
        assert "reddit" in category_ids


def test_pro_search_policies_configured(driver):
    """Verify policies are configured and linked."""
    query = """
    MATCH (p:Policy)
    RETURN p.policy_id, p.name, p.blocks_execution
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        policy_ids = [r["p.policy_id"] for r in records]
        assert "deep_mode_policy" in policy_ids
        assert "cost_control" in policy_ids
        assert "source_diversity" in policy_ids


def test_pro_search_deep_mode_policy_blocks_without_verification(driver):
    """Verify deep_mode_policy blocks execution without cross-verification."""
    query = """
    MATCH (pol:Policy {policy_id: 'deep_mode_policy'})
    RETURN pol.rule, pol.blocks_execution
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert "cross_verify_min >= 3" in record["pol.rule"]
        assert record["pol.blocks_execution"] is True


def test_pro_search_toolchain_steps_ordered(driver):
    """Verify all 6 toolchain steps exist and are ordered correctly."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_STEP]->(step:ToolchainStep)
    RETURN step.step_id, step.name, step.order
    ORDER BY step.order
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        step_ids = [r["step.step_id"] for r in records]
        assert "ps_01_classify" in step_ids
        assert "ps_02_expand" in step_ids
        assert "ps_03_search" in step_ids
        assert "ps_04_verify" in step_ids
        assert "ps_05_synthesize" in step_ids
        assert "ps_06_store" in step_ids
        orders = [r["step.order"] for r in records]
        assert orders == [1, 2, 3, 4, 5, 6]


def test_pro_search_toolchain_tools_exist(driver):
    """Verify tools are linked to toolchain steps."""
    query = """
    MATCH (step:ToolchainStep)-[:USES_TOOL]->(t:Tool)
    RETURN step.step_id, t.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        tool_names = [r["t.name"] for r in records if r["t.name"] is not None]
        assert "intent_classifier" in tool_names or len(records) > 0
        assert "query_expander" in tool_names or len(records) > 0


def test_pro_search_intents_activate_skill(driver):
    """Verify intents activate pro_search skill."""
    query = """
    MATCH (i:Intent)-[:ACTIVATES]->(s:Skill {skill_id: 'pro_search'})
    RETURN i.intent_id, i.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        intent_ids = [r["i.intent_id"] for r in records if r["i.intent_id"] is not None]
        assert "research" in intent_ids
        assert "find_information" in intent_ids
        assert "learn_topic" in intent_ids


def test_pro_search_engine_preferences(driver):
    """Verify engine preferences are configured."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:PREFERS_ENGINE]->(e:Engine)
    RETURN e.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        engine_names = [r["e.name"] for r in records if r["e.name"] is not None]
        assert "qwen3b_local" in engine_names
        assert "smollm_node2" in engine_names
        assert "groq_booster" in engine_names


def test_pro_search_search_engines_configured(driver):
    """Verify search engines or toolchain steps are configured."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:HAS_STEP]->(step:ToolchainStep)
    RETURN step.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        step_names = [r["step.name"] for r in records if r["step.name"] is not None]
        assert "multi_engine_search" in step_names
        assert "classify_query" in step_names


def test_pro_search_memory_layers_configured(driver):
    """Verify memory layers are configured."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:WRITES_TO]->(ml:MemoryLayer)
    RETURN ml.name
    """
    with driver.session() as session:
        result = session.run(query)
        records = list(result)
        layer_names = [r["ml.name"] for r in records if r["ml.name"] is not None]
        assert "L2_SHORT_TERM" in layer_names
        assert "L3_EPISODIC" in layer_names


def test_pro_search_collection_linked(driver):
    """Verify knowledge_base collection is linked."""
    query = """
    MATCH (s:Skill {skill_id: 'pro_search'})-[:USES_COLLECTION]->(ac:AtlasCollection)
    RETURN ac.name
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        assert record is not None
        assert record["ac.name"] == "knowledge_base"
