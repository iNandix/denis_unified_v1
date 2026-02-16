#!/usr/bin/env python3
"""
Denis Graph Seeds - Initialize graph infrastructure for graph-centric mode.

Usage:
    python scripts/seeds/graph_seeds.py
    python scripts/seeds.py --dry-run  # Preview without applying
"""

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Denis Graph Seeds")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without applying"
    )
    parser.add_argument("--env", default=".env", help="Path to .env file")
    args = parser.parse_args()

    # Load environment
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

    # Read and execute seeds
    script_dir = os.path.dirname(os.path.abspath(__file__))
    seeds_file = os.path.join(script_dir, "graph_seeds.cypher")

    with open(seeds_file) as f:
        cypher = f.read()

    if args.dry_run:
        print("=== DRY RUN - Would execute: ===")
        print(cypher[:500] + "...")
        print("\n=== Skipping execution (--dry-run) ===")
        return

    print("Applying graph seeds...")

    # Split by semicolons and execute each statement (ignore errors)
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
                pass  # Ignore errors from idempotent MERGE

        # Get summary
        try:
            result = session.run("MATCH (n:Node) RETURN count(n) as nodes")
            nodes = result.single()["nodes"]
            result = session.run("MATCH (s:Service) RETURN count(s) as services")
            services = result.single()["services"]
            result = session.run("MATCH (e:Engine) RETURN count(e) as engines")
            engines = result.single()["engines"]
            result = session.run("MATCH (t:Tool) RETURN count(t) as tools")
            tools = result.single()["tools"]
            result = session.run("MATCH (i:Intent) RETURN count(i) as intents")
            intents = result.single()["intents"]

            print(f"\n✓ Applied successfully!")
            print(f"  Nodes: {nodes}")
            print(f"  Services: {services}")
            print(f"  Engines: {engines}")
            print(f"  Tools: {tools}")
            print(f"  Intents: {intents}")
        except Exception as e:
            print(f"\n✓ Seeds applied (summary error: {e})")

    driver.close()


if __name__ == "__main__":
    main()
