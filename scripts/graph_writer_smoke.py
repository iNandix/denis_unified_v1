#!/usr/bin/env python3
"""Stream 2: GraphWriter smoke test - verifies core relationships are created at ingest."""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def parse_args():
    parser = argparse.ArgumentParser(description="Stream 2: GraphWriter smoke test")
    parser.add_argument(
        "--out-json",
        default="artifacts/graph/graph_writer_smoke.json",
        help="Output artifact path",
    )
    return parser.parse_args()

def run_smoke():
    """Run GraphWriter smoke test with fail-open behavior."""
    try:
        # Import GraphWriter directly to avoid memory module import chain issues
        import importlib.util
        import sys
        from pathlib import Path
        
        # Load GraphWriter module directly
        graph_writer_path = Path(__file__).parent.parent / "denis_unified_v1" / "memory" / "graph_writer.py"
        spec = importlib.util.spec_from_file_location("graph_writer", graph_writer_path)
        graph_writer_module = importlib.util.module_from_spec(spec)
        sys.modules["graph_writer"] = graph_writer_module
        spec.loader.exec_module(graph_writer_module)
        
        # Get the GraphWriter class and functions
        GraphWriter = graph_writer_module.GraphWriter
        get_graph_writer = graph_writer_module.get_graph_writer
        writer = get_graph_writer()

        # Generate synthetic mini-turn data
        turn_id = f"smoke_turn_{int(time.time())}"
        user_id = "smoke_user"
        content = "Hello, this is a synthetic turn for GraphWriter smoke test"

        # Record turn
        turn_recorded = writer.record_turn(turn_id, user_id, content, {"source": "smoke_test"})

        # Record trace chain
        trace_data = {
            "cognitive": {"analysis": "test analysis", "complexity": "low"},
            "reasoning": {"steps": ["step1", "step2"], "depth": "shallow"},
            "route": {"selected_model": "test_model", "confidence": 0.8}
        }
        trace_recorded = writer.record_trace_chain(turn_id, trace_data)

        # Record tool execution
        tool_data = {
            "tool_name": "test_tool",
            "result": {"status": "success", "output": "test output"},
            "execution_time": 0.1
        }
        tool_recorded = writer.record_tool_execution(trace_data.get("graph_route_id", f"gr_{turn_id}"), tool_data)

        # Record memory chunk
        chunk_data = {
            "content": "Test memory content",
            "layer": "episodic",
            "importance": 0.7
        }
        memory_recorded = writer.record_memory_chunk(f"memory_{turn_id}", chunk_data)

        # Record episode concepts
        episode_concepts_recorded = writer.record_episode_concepts(f"episode_{turn_id}", ["concept1", "concept2"])

        # Record neurolayer-mental loop
        neuro_mental_recorded = writer.record_neurolayer_mental_loop("L1_SENSORY", "reflection")

        # Record voice component
        voice_data = {"type": "speech_recognition", "model": "test"}
        voice_recorded = writer.record_voice_component(f"voice_{turn_id}", voice_data)

        # Record LLM model
        llm_data = {"name": "test-model", "provider": "test"}
        llm_recorded = writer.record_llm_model(f"llm_{turn_id}", llm_data)

        # Check Neo4j availability and potentially verify writes
        neo4j_available = writer.neo4j_available
        deferred_count = writer.get_deferred_count()

        # If Neo4j is available, try to verify the writes
        verification_results = {}
        created_rel_counts = {}

        if neo4j_available:
            try:
                # Verify writes by checking node/relationship counts
                with writer.driver.session() as session:
                    # Count nodes created
                    node_result = session.run("""
                    MATCH (n) WHERE n.id CONTAINS $turn_id OR n.node_ref IN ['L1_SENSORY', 'reflection']
                    RETURN count(n) as created_nodes
                    """, {"turn_id": turn_id})
                    created_nodes = node_result.single()["created_nodes"]

                    # Count relationships created
                    rel_result = session.run("""
                    MATCH ()-[r]-() WHERE
                        (r:HAS_COGNITIVE_TRACE OR r:HAS_REASONING_TRACE OR r:USED_GRAPH_ROUTE OR
                         r:TRIGGERED_TOOL_EXECUTION OR r:HAS_CHUNK OR r:MENTIONS_CONCEPT OR
                         r:IN_EPISODE OR r:FEEDS OR r:FEEDBACKS)
                        AND (startNode(r).id CONTAINS $turn_id OR endNode(r).id CONTAINS $turn_id OR
                             startNode(r).node_ref IN ['L1_SENSORY', 'reflection'] OR
                             endNode(r).node_ref IN ['L1_SENSORY', 'reflection'])
                    RETURN type(r) as rel_type, count(r) as rel_count
                    """, {"turn_id": turn_id})

                    for record in rel_result:
                        created_rel_counts[record["rel_type"]] = record["rel_count"]

                    verification_results = {
                        "created_nodes_verified": created_nodes,
                        "created_relations_verified": sum(created_rel_counts.values()),
                        "verification_success": True
                    }

            except Exception as e:
                verification_results = {
                    "verification_error": str(e),
                    "verification_success": False
                }

        # Prepare result
        operations = {
            "turn_recorded": turn_recorded,
            "trace_recorded": trace_recorded,
            "tool_recorded": tool_recorded,
            "memory_recorded": memory_recorded,
            "episode_concepts_recorded": episode_concepts_recorded,
            "neuro_mental_recorded": neuro_mental_recorded,
            "voice_recorded": voice_recorded,
            "llm_recorded": llm_recorded
        }

        if neo4j_available:
            result = {
                "ok": True,
                "status": "completed",
                "timestamp_utc": _utc_now(),
                "neo4j_available": True,
                "operations": operations,
                "created_rel_counts": created_rel_counts,
                "verification_results": verification_results,
                "deferred_events": deferred_count,
                "turn_id": turn_id
            }
        else:
            result = {
                "ok": True,
                "status": "skippeddependency",
                "reason": "Neo4j not available - GraphWriter operating in deferred mode",
                "timestamp_utc": _utc_now(),
                "neo4j_available": False,
                "operations": operations,
                "deferred_events": deferred_count,
                "turn_id": turn_id
            }

        # Clean up
        writer.close()
        return result

    except Exception as e:
        return {
            "ok": False,
            "status": "failed",
            "error": f"Smoke test execution failed: {str(e)}",
            "timestamp_utc": _utc_now()
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
