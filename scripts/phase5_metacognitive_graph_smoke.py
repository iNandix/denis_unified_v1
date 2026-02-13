#!/usr/bin/env python3
"""Smoke test: verifica que el grafo metacognitivo L0/L1/L2 funciona."""

import asyncio
import json
import sys
import time
from typing import Dict, Any, List
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Leon1234$"


def test_graph_structure() -> Dict[str, Any]:
    """Verifica estructura L0/L1/L2 en Neo4j."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    results: Dict[str, Any] = {}

    try:
        with driver.session() as session:
            # 1) Verificar nodos básicos
            l0_count = session.run(
                "MATCH (n:Tool {layer: 'L0'}) RETURN count(n) as c"
            ).single()["c"]
            l1_count = session.run("MATCH (n:Pattern) RETURN count(n) as c").single()[
                "c"
            ]
            l2_count = session.run("MATCH (n:Principle) RETURN count(n) as c").single()[
                "c"
            ]

            # 2) Contar relaciones
            governance_count = (
                session.run("MATCH ()-[r:GOVERNS]->() RETURN count(r) as c").single()[
                    "c"
                ]
                or 0
            )
            applies_count = (
                session.run(
                    "MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as c"
                ).single()["c"]
                or 0
            )

            # 3) Obtener un camino completo L2->L1->L0
            sample_path = session.run("""
                MATCH path = (pr:Principle)-[:GOVERNS]->(pa:Pattern)-[:APPLIES_TO]->(t:Tool)
                RETURN pr.id as principle_id, pa.id as pattern_id, t.name as tool_name
                LIMIT 1
            """).single()

            results = {
                "l0_tools": l0_count,
                "l1_patterns": l1_count,
                "l2_principles": l2_count,
                "governance_relations": governance_count,
                "applies_to_relations": applies_count,
                "sample_path": dict(sample_path) if sample_path else None,
                "graph_status": "pass"
                if l0_count >= 6 and l1_count >= 3 and l2_count >= 3
                else "fail",
                "message": "Grafo metacognitivo correctamente estructurado",
            }

    except Exception as e:
        results = {
            "error": str(e),
            "graph_status": "error",
            "message": "Error al verificar grafo",
        }
    finally:
        driver.close()

    return results


async def test_cognitive_router() -> Dict[str, Any]:
    """Verifica que Cognitive Router use el grafo metacognitivo."""
    # Añadir el directorio del proyecto al path
    import sys
    sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

    try:
        from denis_unified_v1.orchestration.cognitive_router import CognitiveRouter
    except ImportError as e:
        return {
            "router_status": "error",
            "error": f"ImportError: {str(e)}",
            "message": "No se pudo importar CognitiveRouter",
        }

    router = CognitiveRouter()
    test_requests = [
        {
            "text": "hola",
            "intent": "greet",
        },  # Debería usar routing_fast_path -> smx_fast_check
        {
            "text": "reinicia tailscale",
            "intent": "ops",
        },  # Debería usar safety_gate_parallel
        {
            "text": "escribe una función en python",
            "intent": "code",
        },  # macro_code_intent
    ]

    results = []
    for i, request in enumerate(test_requests, 1):
        try:
            result = await router.route(request)
            results.append(
                {
                    "request": request,
                    "result": {
                        "tool_used": result["meta"].get("tool_used"),
                        "confidence": result["meta"].get("confidence"),
                        "reasoning": result["meta"].get("reasoning", ""),
                        "patterns_used": "pattern"
                        in result["meta"].get("reasoning", "").lower(),
                    },
                    "status": "success",
                }
            )
        except Exception as e:
            results.append({"request": request, "error": str(e), "status": "error"})

    return {
        "router_status": "pass"
        if all(r["status"] == "success" for r in results)
        else "partial",
        "test_results": results,
        "uses_graph_patterns": any(
            r.get("result", {}).get("patterns_used", False)
            for r in results
            if "result" in r
        ),
    }


async def main():
    print("\n=== INICIANDO SMOKE TEST METACOGNITIVO ===")
    print("Verificando estructura del grafo Neo4j...")

    graph_results = test_graph_structure()
    print("Resultados del grafo:")
    print(json.dumps(graph_results, indent=2))

    print("\nProbando Cognitive Router con tráfico real...")
    router_results = await test_cognitive_router()
    print("Resultados del router:")
    print(json.dumps(router_results, indent=2))

    # Guardar resultados completos
    full_results = {
        "graph_audit": graph_results,
        "router_tests": router_results,
        "overall_status": "pass"
        if graph_results.get("graph_status") == "pass"
        and router_results.get("router_status") == "pass"
        else "fail",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open("phase5_metacognitive_graph_smoke.json", "w") as f:
        json.dump(full_results, f, indent=2)

    print("\n=== RESUMEN ===")
    print(f"Estado del grafo: {graph_results.get('graph_status')}")
    print(f"Estado del router: {router_results.get('router_status')}")
    print(
        f"Usando patrones del grafo: {router_results.get('uses_graph_patterns', False)}"
    )

    if full_results["overall_status"] == "pass":
        print("✅ Smoke test PASADO exitosamente")
    else:
        print("❌ Smoke test FALLIDO")
        if "sample_path" in graph_results:
            print(f"Camino de ejemplo: {graph_results['sample_path']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
