#!/usr/bin/env python3
"""Graph Backfill - Cognition Flow.

This script creates missing relationships for the cognition flow:
- Turn → HAS_COGNITIVE_TRACE → CognitiveTrace
- CognitiveTrace → HAS_REASONING_TRACE → ReasoningTrace
- ReasoningTrace → USED_GRAPH_ROUTE → GraphRoute

Run this to fix broken cognition chains in the graph.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_neo4j_driver():
    """Get Neo4j driver."""
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    if not password:
        print("ERROR: NEO4J_PASSWORD not set")
        sys.exit(1)

    return GraphDatabase.driver(uri, auth=(user, password))


def backfill_turn_to_cognitive_trace(driver):
    """Create Turn → HAS_COGNITIVE_TRACE → CognitiveTrace relationships."""
    query = """
    MATCH (t:Turn)
    MATCH (ct:CognitiveTrace)
    WHERE t.id CONTAINS SUBSTRING(ct.id, 4) 
       OR t.id = SUBSTRING(ct.id, 4)
       OR t.trace_id = ct.trace_id
    WHERE NOT (t)-[:HAS_COGNITIVE_TRACE]->(ct)
    MERGE (t)-[:HAS_COGNITIVE_TRACE]->(ct)
    RETURN count(*) as created
    """

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created"]
        print(f"  Created {count} Turn → CognitiveTrace relationships")
        return count


def backfill_cognitive_to_reasoning(driver):
    """Create CognitiveTrace → HAS_REASONING_TRACE → ReasoningTrace relationships."""
    query = """
    MATCH (ct:CognitiveTrace)
    MATCH (rt:ReasoningTrace)
    WHERE ct.id CONTAINS SUBSTRING(rt.id, 4)
       OR ct.trace_id = rt.trace_id
    WHERE NOT (ct)-[:HAS_REASONING_TRACE]->(rt)
    MERGE (ct)-[:HAS_REASONING_TRACE]->(rt)
    RETURN count(*) as created
    """

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created"]
        print(f"  Created {count} CognitiveTrace → ReasoningTrace relationships")
        return count


def backfill_reasoning_to_graph_route(driver):
    """Create ReasoningTrace → USED_GRAPH_ROUTE → GraphRoute relationships."""
    query = """
    MATCH (rt:ReasoningTrace)
    MATCH (gr:GraphRoute)
    WHERE rt.id CONTAINS SUBSTRING(gr.id, 4)
       OR rt.trace_id = gr.trace_id
    WHERE NOT (rt)-[:USED_GRAPH_ROUTE]->(gr)
    MERGE (rt)-[:USED_GRAPH_ROUTE]->(gr)
    RETURN count(*) as created
    """

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created"]
        print(f"  Created {count} ReasoningTrace → GraphRoute relationships")
        return count


def backfill_neurolayer_chain(driver):
    """Create NeuroLayer → NEXT → NeuroLayer chain."""
    layer_order = [
        ("sensory", "working"),
        ("working", "episodic"),
        ("episodic", "semantic"),
        ("semantic", "procedural"),
        ("procedural", "identity"),
        ("identity", "relational"),
        ("relational", "metacog"),
    ]

    total = 0
    for from_layer, to_layer in layer_order:
        query = """
        MATCH (nl1:NeuroLayer {layer: $from_layer})
        MATCH (nl2:NeuroLayer {layer: $to_layer})
        WHERE NOT (nl1)-[:NEXT]->(nl2)
        MERGE (nl1)-[:NEXT {threshold: 0.7}]->(nl2)
        RETURN count(*) as created
        """
        with driver.session() as session:
            result = session.run(query, from_layer=from_layer, to_layer=to_layer)
            count = result.single()["created"]
            if count > 0:
                print(f"  Created {count} {from_layer} → {to_layer} NEXT relationships")
                total += count

    return total


def backfill_neurolayer_feeds_feedbacks(driver):
    """Create NeuroLayer ↔ MentalLoop FEEDS/FEEDBACKS relationships."""

    mappings = [
        ("sensory", "reflection", "FEEDS"),
        ("working", "reflection", "FEEDS"),
        ("episodic", "pattern_recognition", "FEEDS"),
        ("procedural", "meta_reflection", "FEEDS"),
        ("social", "pattern_recognition", "FEEDS"),
        ("identity", "expansive_consciousness", "FEEDS"),
        ("relational", "pattern_recognition", "FEEDS"),
        ("metacog", "expansive_consciousness", "FEEDS"),
    ]

    total = 0
    for layer, loop, rel_type in mappings:
        query = f"""
        MATCH (nl:NeuroLayer {{layer: $layer}})
        MATCH (ml:MentalLoopLevel {{node_ref: $loop}})
        WHERE NOT (nl)-[:{rel_type}]->(ml)
        MERGE (nl)-[:{rel_type}]->(ml)
        RETURN count(*) as created
        """
        with driver.session() as session:
            result = session.run(query, layer=layer, loop=loop)
            count = result.single()["created"]
            if count > 0:
                print(f"  Created {count} {layer} → {loop} {rel_type}")
                total += count

    return total


def get_current_counts(driver):
    """Get current relationship counts."""
    queries = {
        "Turn → CognitiveTrace": "MATCH (t:Turn)-[:HAS_COGNITIVE_TRACE]->(ct:CognitiveTrace) RETURN count(*) as c",
        "CognitiveTrace → ReasoningTrace": "MATCH (ct:CognitiveTrace)-[:HAS_REASONING_TRACE]->(rt:ReasoningTrace) RETURN count(*) as c",
        "ReasoningTrace → GraphRoute": "MATCH (rt:ReasoningTrace)-[:USED_GRAPH_ROUTE]->(gr:GraphRoute) RETURN count(*) as c",
        "NeuroLayer NEXT": "MATCH (nl1:NeuroLayer)-[:NEXT]->(nl2:NeuroLayer) RETURN count(*) as c",
        "FEEDS relationships": "MATCH ()-[r:FEEDS]->(:NeuroLayer) RETURN count(*) as c",
        "FEEDBACKS relationships": "MATCH ()-[r:FEEDBACKS]->(:NeuroLayer) RETURN count(*) as c",
    }

    print("\n=== Current Relationship Counts ===")
    with driver.session() as session:
        for name, query in queries.items():
            result = session.run(query)
            count = result.single()["c"]
            print(f"  {name}: {count}")


def main():
    print("=== Graph Backfill - Cognition Flow ===")
    print(f"Started: {_utc_now()}\n")

    driver = get_neo4j_driver()

    try:
        # Show current state
        get_current_counts(driver)

        print("\n=== Running Backfills ===")

        # Backfill cognition flow
        print("\n1. Cognition Flow:")
        c1 = backfill_turn_to_cognitive_trace(driver)
        c2 = backfill_cognitive_to_reasoning(driver)
        c3 = backfill_reasoning_to_graph_route(driver)

        # Backfill NeuroLayers
        print("\n2. NeuroLayer Chain:")
        n1 = backfill_neurolayer_chain(driver)

        print("\n3. NeuroLayer ↔ MentalLoop:")
        n2 = backfill_neurolayer_feeds_feedbacks(driver)

        # Show final state
        print("\n=== After Backfill ===")
        get_current_counts(driver)

        total = c1 + c2 + c3 + n1 + n2
        print(f"\n✓ Total relationships created: {total}")
        print(f"Completed: {_utc_now()}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
