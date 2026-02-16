#!/usr/bin/env python3
"""Health sync for llama.cpp engines.

Reads engines from Neo4j, checks their /health endpoints,
and updates health_status in the graph.

Usage:
    python3 scripts/inference_health_sync.py [--interval SECONDS]
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Leon1234$")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

import neo4j


def get_engines_from_graph(driver):
    """Fetch all enabled engines from Neo4j."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (e:Engine)
            WHERE e.enabled = true
            RETURN e.name AS name, e.host AS host, e.port AS port,
                   e.paths.health AS health_path
            """
        )
        return [
            {
                "name": record["name"],
                "host": record["host"],
                "port": record["port"],
                "health_path": record["health_path"] or "/health",
            }
            for record in result
        ]


def check_engine_health(engine: dict) -> tuple[str, float]:
    """Check health of a single engine.

    Returns: (health_status, latency_ms)
    """
    url = f"http://{engine['host']}:{engine['port']}{engine['health_path']}"
    try:
        start = time.time()
        resp = requests.get(url, timeout=3)
        latency_ms = (time.time() - start) * 1000

        if resp.status_code == 200:
            return "OK", latency_ms
        else:
            return "DOWN", latency_ms

    except requests.Timeout:
        return "DOWN", 0.0
    except Exception:
        return "DOWN", 0.0


def update_engine_health(driver, name: str, status: str, latency_ms: float):
    """Update engine health status in Neo4j."""
    with driver.session() as session:
        session.run(
            """
            MATCH (e:Engine {name: $name})
            SET e.health_status = $status,
                e.last_health_ms = $latency,
                e.last_health_at = datetime()
            """,
            name=name,
            status=status,
            latency=latency_ms,
        )


def update_redis_snapshot(engines: list):
    """Write engine snapshot to Redis for fast access by router."""
    try:
        import redis

        r = redis.from_url(REDIS_URL)
        pipe = r.pipeline()

        for eng in engines:
            key = f"inference:engine:{eng['name']}"
            pipe.hset(
                key,
                mapping={
                    "host": eng["host"],
                    "port": eng["port"],
                    "health_status": eng["health_status"],
                    "last_health_ms": eng.get("last_health_ms", 0),
                    "task_tags": ",".join(eng.get("task_tags", [])),
                    "priority": eng.get("priority", 999),
                    "max_concurrency": eng.get("max_concurrency", 1),
                },
            )
            pipe.expire(key, 30)  # TTL 30s

        pipe.execute()
    except Exception as e:
        print(f"[health_sync] Redis update failed: {e}", file=sys.stderr)


def run_health_sync():
    """Main health sync loop."""
    print("[health_sync] Starting engine health sync...")

    driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        while True:
            engines = get_engines_from_graph(driver)

            if not engines:
                print("[health_sync] No enabled engines found")
                time.sleep(10)
                continue

            results = []
            for eng in engines:
                status, latency = check_engine_health(eng)
                update_engine_health(driver, eng["name"], status, latency)
                eng["health_status"] = status
                eng["last_health_ms"] = latency

                results.append(f"{eng['name']}:{status}")

                status_symbol = "✓" if status == "OK" else "✗"
                print(
                    f"  {status_symbol} {eng['name']} ({eng['host']}:{eng['port']}) - {latency:.1f}ms"
                )

            update_redis_snapshot(results)

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[health_sync] Stopped")
    finally:
        driver.close()


def main():
    parser = argparse.ArgumentParser(description="Inference engine health sync")
    parser.add_argument(
        "--once", action="store_true", help="Run health check once and exit"
    )
    args = parser.parse_args()

    driver = neo4j.GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        engines = get_engines_from_graph(driver)

        for eng in engines:
            status, latency = check_engine_health(eng)
            update_engine_health(driver, eng["name"], status, latency)

            status_symbol = "✓" if status == "OK" else "✗"
            print(
                f"{status_symbol} {eng['name']} ({eng['host']}:{eng['port']}) - {latency:.1f}ms"
            )

        if not args.once:
            print("\n[health_sync] Starting continuous sync (Ctrl+C to stop)...")
            run_health_sync()

    finally:
        driver.close()


if __name__ == "__main__":
    main()
