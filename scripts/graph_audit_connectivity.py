#!/usr/bin/env python3
"""Stream 1: Graph Connectivity Contract Audit - Reproducible diagnosis with connectivity metrics."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class GraphConnectivityAuditor:
    """Fail-open auditor for graph connectivity contracts."""

    def __init__(self):
        self.neo4j_available = False
        self.driver = None
        self._init_neo4j()

    def _init_neo4j(self):
        """Initialize Neo4j connection with fail-open."""
        try:
            uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")

            if not password:
                raise ValueError("NEO4J_PASSWORD not set")

            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1").single()
            self.neo4j_available = True

        except Exception as e:
            self.neo4j_available = False
            self.connection_error = str(e)

    def run_audit(self) -> Dict[str, Any]:
        """Execute full connectivity audit."""
        if not self.neo4j_available:
            return {
                "ok": True,
                "status": "skippeddependency",
                "reason": f"Neo4j not available: {getattr(self, 'connection_error', 'connection failed')}",
                "timestamp_utc": _utc_now(),
                "graph_available": False
            }

        try:
            with self.driver.session() as session:
                # Core connectivity metrics
                counters = self._measure_counters(session)
                missing_links = self._measure_missing_links(session)
                path_checks = self._verify_paths(session)

                return {
                    "ok": True,
                    "status": "completed",
                    "timestamp_utc": _utc_now(),
                    "graph_available": True,
                    "counters": counters,
                    "missing_links": missing_links,
                    "path_checks": path_checks,
                    "audit_summary": {
                        "total_nodes": counters["total_nodes"],
                        "isolated_nodes": sum(counters["isolated_by_label"].values()),
                        "missing_core_relations": len(missing_links["core_missing_counts"]),
                        "path_completeness": sum(1 for p in path_checks.values() if p.get("exists", False)) / len(path_checks) if path_checks else 0
                    }
                }

        except Exception as e:
            return {
                "ok": False,
                "status": "failed",
                "error": f"Audit execution failed: {str(e)}",
                "timestamp_utc": _utc_now(),
                "graph_available": True
            }

    def _measure_counters(self, session) -> Dict[str, Any]:
        """Count nodes, isolated nodes, and relation statistics."""
        # Total nodes
        total_result = session.run("MATCH (n) RETURN count(n) as total")
        total_nodes = total_result.single()["total"]

        # Nodes by label
        label_result = session.run("CALL db.labels() YIELD label RETURN label, count(*) as count ORDER BY count DESC")
        nodes_by_label = {record["label"]: record["count"] for record in label_result}

        # Isolated nodes (no relationships) by label
        isolated_query = """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN labels(n)[0] as label, count(n) as isolated_count
        """
        isolated_result = session.run(isolated_query)
        isolated_by_label = {record["label"]: record["isolated_count"] for record in isolated_result if record["isolated_count"] > 0}

        # Relation type counts
        rel_result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType, count(*) as count ORDER BY count DESC")
        relations_by_type = {record["relationshipType"]: record["count"] for record in rel_result}

        return {
            "total_nodes": total_nodes,
            "nodes_by_label": nodes_by_label,
            "isolated_by_label": isolated_by_label,
            "relations_by_type": relations_by_type
        }

    def _measure_missing_links(self, session) -> Dict[str, Any]:
        """Measure missing core relationships."""
        core_missing_counts = {}

        # Turn → CognitiveTrace
        turn_trace_query = """
        MATCH (t:Turn)
        WHERE NOT (t)-[:HAS_COGNITIVE_TRACE]->(:CognitiveTrace)
        RETURN count(t) as missing_turn_trace
        """
        result = session.run(turn_trace_query).single()
        core_missing_counts["turn_to_cognitivetrace"] = result["missing_turn_trace"]

        # CognitiveTrace → ReasoningTrace
        trace_reasoning_query = """
        MATCH (ct:CognitiveTrace)
        WHERE NOT (ct)-[:HAS_REASONING_TRACE]->(:ReasoningTrace)
        RETURN count(ct) as missing_trace_reasoning
        """
        result = session.run(trace_reasoning_query).single()
        core_missing_counts["cognitivetrace_to_reasoningtrace"] = result["missing_trace_reasoning"]

        # ReasoningTrace → GraphRoute
        reasoning_route_query = """
        MATCH (rt:ReasoningTrace)
        WHERE NOT (rt)-[:USED_GRAPH_ROUTE]->(:GraphRoute)
        RETURN count(rt) as missing_reasoning_route
        """
        result = session.run(reasoning_route_query).single()
        core_missing_counts["reasoningtrace_to_graphroute"] = result["missing_reasoning_route"]

        # GraphRoute → ToolExecution
        route_tool_query = """
        MATCH (gr:GraphRoute)
        WHERE NOT (gr)-[:TRIGGERED_TOOL_EXECUTION]->(:ToolExecution)
        RETURN count(gr) as missing_route_tool
        """
        result = session.run(route_tool_query).single()
        core_missing_counts["graphroute_to_toolexecution"] = result["missing_route_tool"]

        # Memory → HAS_CHUNK → MemoryChunk
        memory_chunk_query = """
        MATCH (m:Memory)
        WHERE NOT (m)-[:HAS_CHUNK]->(:MemoryChunk)
        RETURN count(m) as missing_memory_chunk
        """
        result = session.run(memory_chunk_query).single()
        core_missing_counts["memory_to_memorychunk"] = result["missing_memory_chunk"]

        # Episode ↔ ConceptNode (bidirectional check)
        episode_concept_query = """
        MATCH (e:Episode)
        WHERE NOT (e)-[:MENTIONS_CONCEPT]->(:ConceptNode)
        RETURN count(e) as missing_episode_concept
        """
        result = session.run(episode_concept_query).single()
        core_missing_counts["episode_to_conceptnode"] = result["missing_episode_concept"]

        concept_episode_query = """
        MATCH (c:ConceptNode)
        WHERE NOT (c)-[:IN_EPISODE]->(:Episode)
        RETURN count(c) as missing_concept_episode
        """
        result = session.run(concept_episode_query).single()
        core_missing_counts["conceptnode_to_episode"] = result["missing_concept_episode"]

        return {
            "core_missing_counts": core_missing_counts,
            "total_missing_core_links": sum(core_missing_counts.values())
        }

    def _verify_paths(self, session) -> Dict[str, Any]:
        """Verify existence of core path chains."""
        path_checks = {}

        # 1. Turn → CognitiveTrace → ReasoningTrace → GraphRoute → ToolExecution
        cognition_flow_query = """
        MATCH path = (t:Turn)-[:HAS_COGNITIVE_TRACE]->(ct:CognitiveTrace)-[:HAS_REASONING_TRACE]->(rt:ReasoningTrace)-[:USED_GRAPH_ROUTE]->(gr:GraphRoute)-[:TRIGGERED_TOOL_EXECUTION]->(te:ToolExecution)
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(cognition_flow_query).single()
        path_checks["cognition_flow_complete"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "Turn→CognitiveTrace→ReasoningTrace→GraphRoute→ToolExecution"
        }

        # 2. Memory → HAS_CHUNK → MemoryChunk
        memory_chunk_query = """
        MATCH path = (m:Memory)-[:HAS_CHUNK]->(mc:MemoryChunk)
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(memory_chunk_query).single()
        path_checks["memory_chunk_chain"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "Memory→HAS_CHUNK→MemoryChunk"
        }

        # 3. Episode ↔ ConceptNode (bidirectional)
        episode_concept_bidirectional_query = """
        MATCH (e:Episode)-[:MENTIONS_CONCEPT]->(c:ConceptNode)-[:IN_EPISODE]->(e2:Episode)
        WHERE e = e2
        RETURN count(*) > 0 as exists, count(*) as path_count
        """
        result = session.run(episode_concept_bidirectional_query).single()
        path_checks["episode_concept_bidirectional"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "Episode↔ConceptNode (bidirectional)"
        }

        # 4. NeuroLayer chain (L1→L2→… or equivalent relations)
        neuro_chain_query = """
        MATCH path = (n1:NeuroLayer)-[:NEXT_LAYER*]->(n2:NeuroLayer)
        WHERE n1.node_ref STARTS WITH 'L' AND n2.node_ref STARTS WITH 'L'
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(neuro_chain_query).single()
        path_checks["neurolayer_chain"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "NeuroLayer chain (L1→L2→…→L12)"
        }

        # 5. MentalLoop chain (Perception→Cognition→Planning→Execution)
        mental_chain_query = """
        MATCH path = (m1:MentalLoopLevel)-[:NEXT_LOOP*]->(m2:MentalLoopLevel)
        WHERE m1.node_ref IN ['perception', 'analysis'] AND m2.node_ref IN ['planning', 'synthesis']
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(mental_chain_query).single()
        path_checks["mentalloop_chain"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "MentalLoop chain (Perception→Cognition→Planning→Execution)"
        }

        # 6. NeuroLayer ↔ MentalLoop couplings
        neuro_mental_coupling_query = """
        MATCH path = (n:NeuroLayer)-[:FEEDS|:FEEDBACKS]-(m:MentalLoopLevel)
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(neuro_mental_coupling_query).single()
        path_checks["neuro_mental_coupling"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "NeuroLayer ↔ MentalLoop couplings (FEEDS/FEEDBACKS)"
        }

        # 7. VoiceComponent ↔ ToolExecution / Trace
        voice_connectivity_query = """
        MATCH path = (v:VoiceComponent)-[:PRODUCED|:USED_IN]-(t:Turn)-[:HAS_COGNITIVE_TRACE|:TRIGGERED_TOOL_EXECUTION]-(target)
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(voice_connectivity_query).single()
        path_checks["voice_component_connectivity"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "VoiceComponent ↔ ToolExecution / Trace"
        }

        # 8. LLMModel ↔ GraphRoute / InferenceDecision
        llm_connectivity_query = """
        MATCH path = (llm:LLMModel)-[:USED_IN|:INFLUENCED]-(gr:GraphRoute)
        RETURN count(path) > 0 as exists, count(path) as path_count
        """
        result = session.run(llm_connectivity_query).single()
        path_checks["llm_model_connectivity"] = {
            "exists": result["exists"],
            "path_count": result["path_count"],
            "description": "LLMModel ↔ GraphRoute / InferenceDecision"
        }

        return path_checks

    def close(self):
        """Clean up resources."""
        if self.driver:
            self.driver.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Stream 1: Graph connectivity contract audit")
    parser.add_argument(
        "--out-json",
        default="artifacts/graph/audit_connectivity.json",
        help="Output artifact path",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    auditor = GraphConnectivityAuditor()
    try:
        result = auditor.run_audit()

        # Write artifact
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        print(json.dumps(result, indent=2))

        # Always exit 0 (fail-open)
        return 0

    finally:
        auditor.close()


if __name__ == "__main__":
    sys.exit(main())
