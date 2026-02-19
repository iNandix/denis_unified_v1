#!/usr/bin/env python3
"""
IntentSystem Graph Seeds - Initialize IntentSystem in Neo4j.

Usage:
    python scripts/seeds/intent_system_seeds.py
    python scripts/seeds/intent_system_seeds.py --dry-run
"""

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="IntentSystem Graph Seeds")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without applying"
    )
    parser.add_argument("--env", default=".env", help="Path to .env file")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(args.env)

    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")

    if not password:
        print("ERROR: NEO4J_PASSWORD not set")
        sys.exit(1)

    driver = GraphDatabase.driver(uri, auth=(user, password))

    script_dir = os.path.dirname(os.path.abspath(__file__))
    seeds_file = os.path.join(script_dir, "intent_system_seeds.cypher")

    with open(seeds_file) as f:
        cypher = f.read()

    if args.dry_run:
        print("=== DRY RUN - Would execute: ===")
        print(cypher[:1000] + "...")
        print("\n=== Skipping execution (--dry-run) ===")
        return

    print("Applying IntentSystem graph seeds...")

    statements = [
        s.strip()
        for s in cypher.split(";")
        if s.strip() and not s.strip().startswith("//")
    ]

    with driver.session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
            except Exception as e:
                print(f"Warning: {e}")

        # Verify counts
        node_types = [
            "Intent",
            "PhasePolicy",
            "GatePolicy",
            "BudgetPolicy",
            "ToolPolicy",
            "JourneyState",
            "BotProfile",
            "FallbackPolicy",
        ]

        print("\n=== IntentSystem Graph Status ===")
        for nt in node_types:
            try:
                result = session.run(f"MATCH (n:{nt}) RETURN count(n) as cnt")
                cnt = result.single()["cnt"]
                print(f"  {nt}: {cnt}")
            except:
                print(f"  {nt}: 0")

        # Count relationships
        rel_types = [
            "USES_PHASE_POLICY",
            "USES_GATE_POLICY",
            "USES_BUDGET_POLICY",
            "ALLOWS_TOOL_POLICY",
            "DEFAULTS_TO",
        ]

        for rt in rel_types:
            try:
                result = session.run(f"MATCH ()-[r:{rt}]->() RETURN count(r) as cnt")
                cnt = result.single()["cnt"]
                print(f"  {rt}: {cnt}")
            except:
                print(f"  {rt}: 0")

    print("\n✓ IntentSystem seeds applied successfully")


if __name__ == "__main__":
    main()
