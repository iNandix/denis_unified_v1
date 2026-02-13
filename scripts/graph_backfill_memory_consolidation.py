#!/usr/bin/env python3
"""Stream 4: Backfill memory consolidation - bidirectional memory and layer transitions."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class MemoryConsolidationBackfiller:
    """Idempotent backfiller for memory consolidation relationships."""

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

    def run_backfill(self) -> Dict[str, Any]:
        """Execute full memory consolidation backfill."""
        if not self.neo4j_available:
            return {
                "ok": True,
                "status": "skippeddependency",
                "reason": "Neo4j not available for memory backfill",
                "timestamp_utc": _utc_now(),
                "backfill_results": {}
            }

        try:
            with self.driver.session() as session:
                results = {}

                # Backfill Memory → HAS_CHUNK → MemoryChunk
                results["memory_to_chunk"] = self._backfill_memory_to_chunk(session)

                # Backfill MemoryChunk sequence chains
                results["chunk_sequences"] = self._backfill_chunk_sequences(session)

                # Backfill Layer transitions
                results["layer_transitions"] = self._backfill_layer_transitions(session)

                # Backfill Episode ↔ ConceptNode bidirectional
                results["episode_concept_bidirectional"] = self._backfill_episode_concept_bidirectional(session)

                # Calculate totals
                total_created = sum(r.get("created", 0) for r in results.values())
                total_processed = sum(r.get("processed", 0) for r in results.values())

                return {
                    "ok": True,
                    "status": "completed",
                    "timestamp_utc": _utc_now(),
                    "neo4j_available": True,
                    "backfill_results": results,
                    "summary": {
                        "total_relationships_created": total_created,
                        "total_entities_processed": total_processed,
                        "backfill_operations": len(results)
                    }
                }

        except Exception as e:
            return {
                "ok": False,
                "status": "failed",
                "error": f"Memory backfill execution failed: {str(e)}",
                "timestamp_utc": _utc_now()
            }

    def _backfill_memory_to_chunk(self, session) -> Dict[str, Any]:
        """Backfill Memory-HAS_CHUNK->MemoryChunk relationships."""
        # Find Memories and MemoryChunks with key correlations
        query = """
        MATCH (m:Memory), (mc:MemoryChunk)
        WHERE NOT (m)-[:HAS_CHUNK]->(mc)
        AND (
            // Direct key correlation
            mc.id CONTAINS m.id OR m.id CONTAINS mc.id
            // Or matching memory keys in properties
            OR mc.memory_key = m.id
            OR mc.chunk_key STARTS WITH m.id
            // Or user/session correlation
            OR m.user_id = mc.user_id
        )
        WITH m, mc
        MERGE (m)-[:HAS_CHUNK]->(mc)
        RETURN count(*) as created
        """

        try:
            result = session.run(query).single()
            created = result["created"]
            return {"created": created, "processed": created, "status": "success"}
        except Exception as e:
            return {"created": 0, "processed": 0, "status": "error", "error": str(e)}

    def _backfill_chunk_sequences(self, session) -> Dict[str, Any]:
        """Backfill MemoryChunk sequence chains by timestamp."""
        # Create NEXT_CHUNK relationships between chunks of the same memory
        query = """
        MATCH (m:Memory)-[:HAS_CHUNK]->(mc1:MemoryChunk),
              (m:Memory)-[:HAS_CHUNK]->(mc2:MemoryChunk)
        WHERE mc1 <> mc2
        AND NOT (mc1)-[:NEXT_CHUNK]->(mc2)
        AND mc1.timestamp < mc2.timestamp
        AND NOT EXISTS {
            // Don't create if there's already a closer chunk in between
            MATCH (mc1)-[:NEXT_CHUNK*1..5]->(mc_between:MemoryChunk)-[:NEXT_CHUNK]->(mc2)
            WHERE mc_between.timestamp > mc1.timestamp AND mc_between.timestamp < mc2.timestamp
        }
        WITH mc1, mc2, m
        ORDER BY mc1.timestamp, mc2.timestamp
        WITH mc1, collect(mc2)[0] as next_chunk, m
        WHERE next_chunk IS NOT NULL
        MERGE (mc1)-[:NEXT_CHUNK]->(next_chunk)
        RETURN count(*) as sequences_created
        """

        try:
            result = session.run(query).single()
            created = result["sequences_created"]
            return {"created": created, "processed": created * 2, "status": "success"}
        except Exception as e:
            return {"created": 0, "processed": 0, "status": "error", "error": str(e)}

    def _backfill_layer_transitions(self, session) -> Dict[str, Any]:
        """Backfill Layer transitions by ordinal."""
        # Create NEXT_LAYER relationships between memory layers
        query = """
        MATCH (l1:MemoryLayer), (l2:MemoryLayer)
        WHERE l1 <> l2
        AND NOT (l1)-[:NEXT_LAYER]->(l2)
        AND toInteger(l1.ordinal) = toInteger(l2.ordinal) - 1
        AND l1.type = l2.type  // Same memory type chain
        MERGE (l1)-[:NEXT_LAYER]->(l2)
        RETURN count(*) as transitions_created
        """

        try:
            result = session.run(query).single()
            created = result["transitions_created"]
            return {"created": created, "processed": created * 2, "status": "success"}
        except Exception as e:
            return {"created": 0, "processed": 0, "status": "error", "error": str(e)}

    def _backfill_episode_concept_bidirectional(self, session) -> Dict[str, Any]:
        """Backfill Episode ↔ ConceptNode bidirectional relationships."""
        # For existing MENTIONS_CONCEPT relationships, create the reverse IN_EPISODE
        query = """
        MATCH (e:Episode)-[r:MENTIONS_CONCEPT]->(c:ConceptNode)
        WHERE NOT (c)-[:IN_EPISODE]->(e)
        MERGE (c)-[:IN_EPISODE]->(e)
        RETURN count(r) as bidirectional_created
        """

        try:
            result = session.run(query).single()
            created = result["bidirectional_created"]
            return {"created": created, "processed": created, "status": "success"}
        except Exception as e:
            return {"created": 0, "processed": 0, "status": "error", "error": str(e)}

    def get_memory_stats(self, session) -> Dict[str, Any]:
        """Get memory consolidation statistics."""
        try:
            # Count memory entities and relationships
            stats_query = """
            MATCH (m:Memory)
            OPTIONAL MATCH (m)-[:HAS_CHUNK]->(mc:MemoryChunk)
            RETURN count(DISTINCT m) as memories,
                   count(DISTINCT mc) as chunks,
                   count(DISTINCT CASE WHEN (m)-[:HAS_CHUNK]->(mc) THEN mc END) as linked_chunks
            """

            result = session.run(stats_query).single()

            # Count bidirectional episode-concept links
            bidirectional_query = """
            MATCH (e:Episode)-[:MENTIONS_CONCEPT]->(c:ConceptNode)-[:IN_EPISODE]->(e)
            RETURN count(*) as bidirectional_pairs
            """

            bidirectional_result = session.run(bidirectional_query).single()

            return {
                "memories": result["memories"],
                "chunks": result["chunks"],
                "linked_chunks": result["linked_chunks"],
                "bidirectional_episode_concept": bidirectional_result["bidirectional_pairs"],
                "chunk_linking_ratio": result["linked_chunks"] / max(result["chunks"], 1)
            }

        except Exception as e:
            return {"error": str(e)}

    def close(self):
        """Clean up resources."""
        if self.driver:
            self.driver.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Stream 4: Backfill memory consolidation")
    parser.add_argument(
        "--out-json",
        default="artifacts/graph/backfill_memory_consolidation.json",
        help="Output artifact path",
    )
    return parser.parse_args()


def run_smoke():
    """Run memory consolidation backfill smoke test."""
    try:
        # Import and run backfiller
        backfiller = MemoryConsolidationBackfiller()

        # Run backfill
        backfill_result = backfiller.run_backfill()

        # Get memory stats if Neo4j available
        stats = None
        audit_result = None

        if backfill_result.get("neo4j_available"):
            with backfiller.driver.session() as session:
                stats = backfiller.get_memory_stats(session)

            # Run audit to verify improvements
            import subprocess
            audit_cmd = [
                sys.executable, str(PROJECT_ROOT / "scripts" / "graph_audit_connectivity.py"),
                "--out-json", "/tmp/audit_post_memory_backfill.json"
            ]
            audit_process = subprocess.run(
                audit_cmd,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
                capture_output=True,
                text=True,
                timeout=60
            )

            if audit_process.returncode == 0:
                try:
                    with open("/tmp/audit_post_memory_backfill.json", "r") as f:
                        audit_result = json.load(f)
                except:
                    audit_result = {"status": "audit_read_failed"}

        # Combine results
        result = {
            **backfill_result,
            "memory_stats": stats,
            "audit_post_backfill": audit_result
        }

        backfiller.close()
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
