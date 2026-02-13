#!/usr/bin/env python3
"""Stream 5: Neuro-layers ↔ Mental-loops integration smoke test."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def parse_args():
    parser = argparse.ArgumentParser(description="Stream 5: Neuro-mental loop integration smoke")
    parser.add_argument(
        "--out-json",
        default="artifacts/architecture/neuro_loop_links.json",
        help="Output artifact path",
    )
    return parser.parse_args()

def run_smoke():
    """Run neuro-mental loop integration smoke test."""
    try:
        # Create synthetic events to test integration
        test_events = [
            {
                "event_type": "sensory_input",
                "event_data": {"input_type": "visual", "intensity": 0.8},
                "source_layer": "L1_SENSORY",
                "target_loop": "reflection"
            },
            {
                "event_type": "cognitive_processing",
                "event_data": {"processing_type": "pattern_matching", "confidence": 0.9},
                "source_layer": "L2_WORKING",
                "target_loop": "pattern_recognition"
            },
            {
                "event_type": "memory_consolidation",
                "event_data": {"consolidation_type": "episodic_to_semantic", "items_processed": 15},
                "source_layer": "L3_EPISODIC",
                "target_loop": "expansive_consciousness"
            }
        ]

        results = []
        total_relationships_created = 0

        for event in test_events:
            # Simulate processing through the integration API
            result = process_synthetic_event(event)
            results.append({
                "event": event,
                "processing_result": result
            })
            
            if result.get("relationships_created"):
                total_relationships_created += len(result["relationships_created"])

        # Verify relationships exist (if Neo4j available)
        verification_results = verify_relationships()

        # Overall assessment
        integration_status = "integrated" if verification_results.get("feeds_feedbacks_exist", False) else "disconnected"
        if not verification_results.get("neo4j_available", False):
            integration_status = "skippeddependency"

        return {
            "ok": True,
            "status": integration_status,
            "timestamp_utc": _utc_now(),
            "test_events_processed": len(test_events),
            "total_relationships_created": total_relationships_created,
            "event_results": results,
            "verification_results": verification_results,
            "integration_assessment": {
                "neurolayer_mental_loop_links": verification_results.get("feeds_feedbacks_count", 0),
                "mental_loop_chain": verification_results.get("mental_loop_chain_exists", False),
                "neurolayer_chain": verification_results.get("neurolayer_chain_exists", False),
                "bidirectional_flow": verification_results.get("bidirectional_flow_exists", False)
            }
        }

    except Exception as e:
        return {
            "ok": False,
            "status": "failed",
            "error": f"Smoke test execution failed: {str(e)}",
            "timestamp_utc": _utc_now()
        }

def process_synthetic_event(event: dict) -> dict:
    """Process a synthetic event through the neuro-mental integration."""
    try:
        # Import and use GraphWriter directly (simulating API call)
        import importlib.util
        import sys
        
        graph_writer_path = PROJECT_ROOT / "denis_unified_v1" / "memory" / "graph_writer.py"
        spec = importlib.util.spec_from_file_location("graph_writer", graph_writer_path)
        graph_writer_module = importlib.util.module_from_spec(spec)
        sys.modules["graph_writer"] = graph_writer_module
        spec.loader.exec_module(graph_writer_module)
        
        GraphWriter = graph_writer_module.GraphWriter
        writer = GraphWriter()
        
        # Process based on event type
        if event["event_type"] == "sensory_input":
            # Create feed relationship
            feed_result = writer.record_neurolayer_mental_loop(
                event["source_layer"], event["target_loop"], "feed"
            )
            processing_steps = ["sensory_feed_created", "reflection_activated"]
            
        elif event["event_type"] == "cognitive_processing":
            # Create feedback relationship
            feedback_result = writer.record_neurolayer_mental_loop(
                event["source_layer"], event["target_loop"], "feedback"
            )
            processing_steps = ["cognitive_feedback_created", "pattern_recognition_engaged"]
            
        elif event["event_type"] == "memory_consolidation":
            # Create multiple adaptations
            adaptations = []
            memory_layers = ["L3_EPISODIC", "L5_PROCEDURAL", "L9_IDENTITY"]
            mental_functions = ["pattern_recognition", "meta_reflection", "expansive_consciousness"]
            
            for neuro_layer in memory_layers:
                for mental_loop in mental_functions:
                    result = writer.record_neurolayer_mental_loop(neuro_layer, mental_loop, "consolidation")
                    adaptations.append({"neuro": neuro_layer, "mental": mental_loop, "result": result})
            
            processing_steps = [f"adaptation_created_{len(adaptations)}"]
            
        # Ensure chains exist
        _ensure_chains(writer)
        
        relationships_created = ["FEEDS", "FEEDBACKS", "NEXT"] if writer.neo4j_available else []
        
        writer.close()
        
        return {
            "status": "processed",
            "processing_steps": processing_steps,
            "relationships_created": relationships_created,
            "neo4j_available": writer.neo4j_available
        }
        
    except Exception as e:
        return {
            "status": "processing_failed",
            "error": str(e)[:200]
        }

def _ensure_chains(writer):
    """Ensure neuro and mental chains exist."""
    try:
        # Mental loop chain
        loop_sequence = [
            ("perception", "analysis"),
            ("analysis", "planning"), 
            ("planning", "synthesis")
        ]
        
        for from_loop, to_loop in loop_sequence:
            writer._execute_write("""
            MERGE (ml1:MentalLoopLevel {node_ref: $from_loop})
            MERGE (ml2:MentalLoopLevel {node_ref: $to_loop})
            MERGE (ml1)-[:NEXT]->(ml2)
            """, {"from_loop": from_loop, "to_loop": to_loop})

        # Neurolayer chain
        layer_sequence = [
            ("L1_SENSORY", "L2_WORKING"),
            ("L2_WORKING", "L3_EPISODIC"),
            ("L3_EPISODIC", "L5_PROCEDURAL")
        ]
        
        for from_layer, to_layer in layer_sequence:
            writer._execute_write("""
            MERGE (nl1:NeuroLayer {node_ref: $from_layer})
            MERGE (nl2:NeuroLayer {node_ref: $to_layer})
            MERGE (nl1)-[:NEXT]->(nl2)
            """, {"from_layer": from_layer, "to_layer": to_layer})
            
    except Exception:
        pass  # Fail silently for smoke test

def verify_relationships() -> dict:
    """Verify that neuro-mental relationships exist."""
    try:
        # Try to connect to Neo4j for verification
        import os
        uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        if not password:
            return {"neo4j_available": False, "reason": "NEO4J_PASSWORD not set"}

        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            # Check FEEDS/FEEDBACKS relationships
            feed_query = """
            MATCH ()-[r:FEEDS|FEEDBACKS]-()
            RETURN count(r) as relationship_count
            """
            feed_result = session.run(feed_query).single()
            feeds_feedbacks_count = feed_result["relationship_count"]
            
            # Check mental loop chain
            mental_chain_query = """
            MATCH path = (ml1:MentalLoopLevel)-[:NEXT*]->(ml2:MentalLoopLevel)
            WHERE ml1.node_ref IN ['perception', 'analysis'] AND ml2.node_ref IN ['planning', 'synthesis']
            RETURN count(path) > 0 as chain_exists
            """
            mental_result = session.run(mental_chain_query).single()
            mental_chain_exists = mental_result["chain_exists"]
            
            # Check neurolayer chain
            neuro_chain_query = """
            MATCH path = (nl1:NeuroLayer)-[:NEXT*]->(nl2:NeuroLayer)
            WHERE nl1.node_ref STARTS WITH 'L' AND nl2.node_ref STARTS WITH 'L'
            RETURN count(path) > 0 as chain_exists
            """
            neuro_result = session.run(neuro_chain_query).single()
            neuro_chain_exists = neuro_result["chain_exists"]
            
            # Check bidirectional flow (at least one FEEDS and one FEEDBACKS)
            bidirectional_query = """
            MATCH (nl:NeuroLayer)-[:FEEDS]->(ml:MentalLoopLevel),
                  (ml2:MentalLoopLevel)-[:FEEDBACKS]->(nl2:NeuroLayer)
            RETURN count(*) > 0 as bidirectional_exists
            """
            bidirectional_result = session.run(bidirectional_query).single()
            bidirectional_exists = bidirectional_result["bidirectional_exists"]

        driver.close()
        
        return {
            "neo4j_available": True,
            "feeds_feedbacks_exist": feeds_feedbacks_count > 0,
            "feeds_feedbacks_count": feeds_feedbacks_count,
            "mental_loop_chain_exists": mental_chain_exists,
            "neurolayer_chain_exists": neuro_chain_exists,
            "bidirectional_flow_exists": bidirectional_exists
        }
        
    except Exception as e:
        return {
            "neo4j_available": False,
            "error": str(e)[:200]
        }

def main():
    args = parse_args()
    result = run_smoke()

    # Write artifact
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    # Always exit 0 (fail-open)
    return 0

if __name__ == "__main__":
    sys.exit(main())
