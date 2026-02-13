#!/usr/bin/env python3
"""Graph Relationships Smoke - Verify critical graph relationships exist.

This smoke test verifies that key graph relationships are properly connected:
- Turn → CognitiveTrace → ReasoningTrace → GraphRoute
- NeuroLayer transitions (L1 → L2 → L3)
- Memory tier promotion
- Voice ↔ Cognitive components
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args():
    parser = argparse.ArgumentParser(description="Graph relationships smoke test")
    parser.add_argument(
        "--out-json",
        default="artifacts/graph/relationships_smoke.json",
        help="Output artifact path",
    )
    return parser.parse_args()


def check_neo4j_connection():
    """Check if Neo4j is available."""
    import os

    try:
        from neo4j import GraphDatabase

        uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        if not password:
            return None, "NEO4J_PASSWORD not set"

        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver, None
    except Exception as e:
        return None, str(e)


def verify_relationships(driver) -> dict:
    """Verify key graph relationships exist."""

    results = {}

    # 1. Check Turn → CognitiveTrace relationship
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Turn)-[r:HAS_COGNITIVE_TRACE]->(ct:CognitiveTrace)
                RETURN count(r) as count
            """)
            count = result.single()["count"]
            results["turn_to_cognitive_trace"] = {"exists": count > 0, "count": count}
    except Exception as e:
        results["turn_to_cognitive_trace"] = {"error": str(e)}

    # 2. Check CognitiveTrace → ReasoningTrace
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (ct:CognitiveTrace)-[r:HAS_REASONING_TRACE]->(rt:ReasoningTrace)
                RETURN count(r) as count
            """)
            count = result.single()["count"]
            results["cognitive_to_reasoning"] = {"exists": count > 0, "count": count}
    except Exception as e:
        results["cognitive_to_reasoning"] = {"error": str(e)}

    # 3. Check ReasoningTrace → GraphRoute
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (rt:ReasoningTrace)-[r:USED_GRAPH_ROUTE]->(gr:GraphRoute)
                RETURN count(r) as count
            """)
            count = result.single()["count"]
            results["reasoning_to_graph_route"] = {"exists": count > 0, "count": count}
    except Exception as e:
        results["reasoning_to_graph_route"] = {"error": str(e)}

    # 4. Check NeuroLayer relationships (FEEDS/FEEDBACKS)
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH ()-[r:FEEDS]->(:NeuroLayer)
                RETURN count(r) as count
            """)
            feeds_count = result.single()["count"]

            result = session.run("""
                MATCH ()-[r:FEEDBACKS]->(:NeuroLayer)
                RETURN count(r) as count
            """)
            feedbacks_count = result.single()["count"]

            results["neurolayer_relationships"] = {
                "exists": feeds_count > 0 or feedbacks_count > 0,
                "feeds_count": feeds_count,
                "feedbacks_count": feedbacks_count,
            }
    except Exception as e:
        results["neurolayer_relationships"] = {"error": str(e)}

    # 5. Check NeuroLayer NEXT chain
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (nl1:NeuroLayer)-[r:NEXT]->(nl2:NeuroLayer)
                RETURN count(r) as count
            """)
            count = result.single()["count"]
            results["neurolayer_chain"] = {"exists": count > 0, "count": count}
    except Exception as e:
        results["neurolayer_chain"] = {"error": str(e)}

    # 6. Check Memory relationships
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (m:Memory)-[r:HAS_CHUNK]->(mc:MemoryChunk)
                RETURN count(r) as count
            """)
            count = result.single()["count"]
            results["memory_chunks"] = {"exists": count > 0, "count": count}
    except Exception as e:
        results["memory_chunks"] = {"error": str(e)}

    # 7. Check Voice → Cognitive connections
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (vc:VoiceComponent)-[r]->(t:Turn)
                RETURN count(r) as count
            """)
            voice_turn = result.single()["count"]

            result = session.run("""
                MATCH (vc:VoiceComponent)-[r]->(llm:LLMModel)
                RETURN count(r) as count
            """)
            voice_llm = result.single()["count"]

            results["voice_connections"] = {
                "exists": voice_turn > 0 or voice_llm > 0,
                "voice_to_turn": voice_turn,
                "voice_to_llm": voice_llm,
            }
    except Exception as e:
        results["voice_connections"] = {"error": str(e)}

    # 8. Check isolated nodes
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (n)
                WHERE NOT (n)--()
                RETURN count(n) as count
            """)
            count = result.single()["count"]
            results["isolated_nodes"] = {"count": count, "warning": count > 100}
    except Exception as e:
        results["isolated_nodes"] = {"error": str(e)}

    return results


def run_smoke():
    """Run graph relationships smoke test."""
    try:
        # Check Neo4j connection
        driver, error = check_neo4j_connection()

        if error:
            return {
                "ok": False,
                "neo4j_available": False,
                "error": error,
                "timestamp_utc": _utc_now(),
            }

        # Verify relationships
        relationships = verify_relationships(driver)

        driver.close()

        # Determine overall status
        critical_chains = [
            relationships.get("turn_to_cognitive_trace", {}).get("exists", False),
            relationships.get("cognitive_to_reasoning", {}).get("exists", False),
            relationships.get("reasoning_to_graph_route", {}).get("exists", False),
        ]

        cognition_flow_working = all(critical_chains)

        neurolayers_connected = relationships.get("neurolayer_relationships", {}).get(
            "exists", False
        )

        isolated_count = relationships.get("isolated_nodes", {}).get("count", 0)

        ok = cognition_flow_working and isolated_count < 1000

        return {
            "ok": ok,
            "neo4j_available": True,
            "cognition_flow_working": cognition_flow_working,
            "neurolayers_connected": neurolayers_connected,
            "isolated_nodes": isolated_count,
            "relationships": relationships,
            "timestamp_utc": _utc_now(),
        }

    except Exception as e:
        import traceback

        return {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
            "timestamp_utc": _utc_now(),
        }


def main():
    args = parse_args()
    result = run_smoke()

    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
