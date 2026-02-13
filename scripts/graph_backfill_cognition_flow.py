#!/usr/bin/env python3
"""Stream 3: Backfill cognition flow links - reconstruct Turn→Trace→Route→ToolExecution chains."""

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


class CognitionFlowBackfiller:
    """Idempotent backfiller for cognition flow relationships."""

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
        """Execute full cognition flow backfill."""
        if not self.neo4j_available:
            return {
                "ok": True,
                "status": "skippeddependency",
                "reason": "Neo4j not available for backfill",
                "timestamp_utc": _utc_now(),
                "backfill_results": {}
            }

        try:
            with self.driver.session() as session:
                results = {}

                # Backfill Turn → CognitiveTrace
                results["turn_to_cognitivetrace"] = self._backfill_turn_to_cognitivetrace(session)

                # Backfill CognitiveTrace → ReasoningTrace
                results["cognitivetrace_to_reasoningtrace"] = self._backfill_cognitivetrace_to_reasoningtrace(session)

                # Backfill ReasoningTrace → GraphRoute
                results["reasoningtrace_to_graphroute"] = self._backfill_reasoningtrace_to_graphroute(session)

                # Backfill GraphRoute → ToolExecution
                results["graphroute_to_toolexecution"] = self._backfill_graphroute_to_toolexecution(session)

                # Calculate totals
                total_created = sum(r.get("created", 0) for r in results.values())
                total_skipped = sum(r.get("skipped", 0) for r in results.values())

                return {
                    "ok": True,
                    "status": "completed",
                    "timestamp_utc": _utc_now(),
                    "neo4j_available": True,
                    "backfill_results": results,
                    "summary": {
                        "total_relationships_created": total_created,
                        "total_relationships_skipped": total_skipped,
                        "backfill_operations": len(results)
                    }
                }

        except Exception as e:
            return {
                "ok": False,
                "status": "failed",
                "error": f"Backfill execution failed: {str(e)}",
                "timestamp_utc": _utc_now()
            }

    def _backfill_turn_to_cognitivetrace(self, session) -> Dict[str, Any]:
        """Backfill Turn-HAS_COGNITIVE_TRACE->CognitiveTrace relationships."""
        # Find Turns and CognitiveTraces with matching correlation IDs
        query = """
        // Find pairs where Turn and CognitiveTrace have correlatable IDs
        MATCH (t:Turn), (ct:CognitiveTrace)
        WHERE NOT (t)-[:HAS_COGNITIVE_TRACE]->(ct)
        AND (
            // Direct ID correlation
            ct.id CONTAINS t.id OR t.id CONTAINS ct.id
            // Or matching request/session IDs in properties
            OR t.request_id = ct.request_id
            OR t.session_id = ct.session_id
            // Or temporal correlation (within 5 minutes)
            OR abs(duration.between(datetime(t.timestamp), datetime(ct.timestamp)).seconds) < 300
        )
        // Ensure not already connected
        WITH t, ct
        MERGE (t)-[:HAS_COGNITIVE_TRACE]->(ct)
        RETURN count(*) as created
        """

        try:
            result = session.run(query).single()
            created = result["created"]
            return {"created": created, "skipped": 0, "status": "success"}
        except Exception as e:
            return {"created": 0, "skipped": 0, "status": "error", "error": str(e)}

    def _backfill_cognitivetrace_to_reasoningtrace(self, session) -> Dict[str, Any]:
        """Backfill CognitiveTrace-HAS_REASONING_TRACE->ReasoningTrace relationships."""
        query = """
        // Find pairs where CognitiveTrace and ReasoningTrace have correlatable IDs
        MATCH (ct:CognitiveTrace), (rt:ReasoningTrace)
        WHERE NOT (ct)-[:HAS_REASONING_TRACE]->(rt)
        AND (
            // Direct ID correlation
            rt.id CONTAINS ct.id OR ct.id CONTAINS rt.id
            // Or matching trace IDs
            OR ct.trace_id = rt.trace_id
            OR ct.request_id = rt.request_id
            // Or temporal correlation (within 2 minutes)
            OR abs(duration.between(datetime(ct.timestamp), datetime(rt.timestamp)).seconds) < 120
        )
        WITH ct, rt
        MERGE (ct)-[:HAS_REASONING_TRACE]->(rt)
        RETURN count(*) as created
        """

        try:
            result = session.run(query).single()
            created = result["created"]
            return {"created": created, "skipped": 0, "status": "success"}
        except Exception as e:
            return {"created": 0, "skipped": 0, "status": "error", "error": str(e)}

    def _backfill_reasoningtrace_to_graphroute(self, session) -> Dict[str, Any]:
        """Backfill ReasoningTrace-USED_GRAPH_ROUTE->GraphRoute relationships."""
        query = """
        // Find pairs where ReasoningTrace and GraphRoute have correlatable IDs
        MATCH (rt:ReasoningTrace), (gr:GraphRoute)
        WHERE NOT (rt)-[:USED_GRAPH_ROUTE]->(gr)
        AND (
            // Direct ID correlation
            gr.id CONTAINS rt.id OR rt.id CONTAINS gr.id
            // Or matching route IDs
            OR rt.route_id = gr.id
            OR rt.trace_id = gr.trace_id
            // Or temporal correlation (within 1 minute)
            OR abs(duration.between(datetime(rt.timestamp), datetime(gr.timestamp)).seconds) < 60
        )
        WITH rt, gr
        MERGE (rt)-[:USED_GRAPH_ROUTE]->(gr)
        RETURN count(*) as created
        """

        try:
            result = session.run(query).single()
            created = result["created"]
            return {"created": created, "skipped": 0, "status": "success"}
        except Exception as e:
            return {"created": 0, "skipped": 0, "status": "error", "error": str(e)}

    def _backfill_graphroute_to_toolexecution(self, session) -> Dict[str, Any]:
        """Backfill GraphRoute-TRIGGERED_TOOL_EXECUTION->ToolExecution relationships."""
        query = """
        // Find pairs where GraphRoute and ToolExecution have correlatable IDs
        MATCH (gr:GraphRoute), (te:ToolExecution)
        WHERE NOT (gr)-[:TRIGGERED_TOOL_EXECUTION]->(te)
        AND (
            // Direct ID correlation
            te.id CONTAINS gr.id OR gr.id CONTAINS te.id
            // Or matching execution IDs
            OR te.route_id = gr.id
            OR te.trace_id = gr.trace_id
            // Or temporal correlation (within 30 seconds)
            OR abs(duration.between(datetime(gr.timestamp), datetime(te.timestamp)).seconds) < 30
        )
        WITH gr, te
        MERGE (gr)-[:TRIGGERED_TOOL_EXECUTION]->(te)
        RETURN count(*) as created
        """

        try:
            result = session.run(query).single()
            created = result["created"]
            return {"created": created, "skipped": 0, "status": "success"}
        except Exception as e:
            return {"created": 0, "skipped": 0, "status": "error", "error": str(e)}

    def close(self):
        """Clean up resources."""
        if self.driver:
            self.driver.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Stream 3: Backfill cognition flow links")
    parser.add_argument(
        "--out-json",
        default="artifacts/graph/backfill_cognition_flow.json",
        help="Output artifact path",
    )
    return parser.parse_args()


def run_smoke():
    """Run backfill smoke test with audit verification."""
    try:
        # Import and run backfiller
        backfiller = CognitionFlowBackfiller()

        # Run backfill
        backfill_result = backfiller.run_backfill()

        # If Neo4j available, run audit to verify improvements
        audit_result = None
        if backfill_result.get("neo4j_available"):
            # Import audit script functionality
            import subprocess
            audit_cmd = [
                sys.executable, str(PROJECT_ROOT / "scripts" / "graph_audit_connectivity.py"),
                "--out-json", "/tmp/audit_post_backfill.json"
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
                    with open("/tmp/audit_post_backfill.json", "r") as f:
                        audit_result = json.load(f)
                except:
                    audit_result = {"status": "audit_read_failed"}

        # Combine results
        result = {
            **backfill_result,
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
