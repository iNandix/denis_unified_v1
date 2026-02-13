#!/usr/bin/env python3
"""Inicializa estructura metacognitiva L0/L1/L2 en Neo4j."""

import os
from neo4j import GraphDatabase
import yaml
import json

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Leon1234$")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def clear_metacognitive_nodes(session):
    """Limpia nodos metacognitivos antiguos sin tocar telemetría."""
    print("Limpiando nodos metacognitivos antiguos...")
    session.run(
        "MATCH (n) WHERE n:Pattern OR n:Principle OR n:MetaReflection OR n:BehaviorPattern OR n:RoutingPattern DETACH DELETE n"
    )


def create_l0_tools(session):
    """Crea/actualiza nodos Tool (L0) con propiedades para Cognitive Router."""
    print("Creando nodos :Tool L0...")
    tools = [
        {
            "name": "smx_response",
            "role": "response",
            "model": "qwen3b",
            "port": 9997,
            "node": "nodo1",
            "success_rate": 0.95,
            "avg_latency_ms": 800,
            "cost_per_call": 0.0,
        },
        {
            "name": "smx_macro",
            "role": "macro",
            "model": "qwencoder7b",
            "port": 9998,
            "node": "nodo1",
            "success_rate": 0.92,
            "avg_latency_ms": 1500,
            "cost_per_call": 0.0,
        },
        {
            "name": "smx_fast_check",
            "role": "fast_check",
            "model": "qwen05b",
            "port": 8003,
            "node": "nodo2",
            "success_rate": 0.90,
            "avg_latency_ms": 200,
            "cost_per_call": 0.0,
        },
        {
            "name": "smx_safety",
            "role": "safety",
            "model": "gemma1b",
            "port": 8007,
            "node": "nodo2",
            "success_rate": 0.98,
            "avg_latency_ms": 300,
            "cost_per_call": 0.0,
        },
        {
            "name": "smx_intent",
            "role": "intent",
            "model": "qwen15b",
            "port": 8008,
            "node": "nodo2",
            "success_rate": 0.88,
            "avg_latency_ms": 400,
            "cost_per_call": 0.0,
        },
        {
            "name": "smx_tokenize",
            "role": "tokenize",
            "model": "smollm2",
            "port": 8006,
            "node": "nodo2",
            "success_rate": 0.85,
            "avg_latency_ms": 150,
            "cost_per_call": 0.0,
        },
        {
            "name": "infrastructure_adapter",
            "role": "ops",
            "model": "cortex",
            "port": 0,
            "node": "local",
            "success_rate": 0.94,
            "avg_latency_ms": 500,
            "cost_per_call": 0.0,
        },
        {
            "name": "code_executor",
            "role": "code",
            "model": "autopoiesis",
            "port": 0,
            "node": "local",
            "success_rate": 0.87,
            "avg_latency_ms": 2000,
            "cost_per_call": 0.0,
        },
    ]

    for tool in tools:
        session.run(
            """
            MERGE (t:Tool {name: $name})
            SET t.role = $role,
                t.model = $model,
                t.port = $port,
                t.node = $node,
                t.success_rate = $success_rate,
                t.avg_latency_ms = $avg_latency_ms,
                t.cost_per_call = $cost_per_call,
                t.layer = 'L0',
                t.updated_at = datetime()
        """,
            **tool,
        )

    print(f"  Creados/actualizados {len(tools)} Tools L0")


def create_l1_patterns(session):
    """Crea nodos Pattern (L1) - patrones detectados en el comportamiento del sistema."""
    print("Creando nodos :Pattern L1...")
    patterns = [
        {
            "id": "routing_fast_path",
            "type": "routing",
            "description": "Queries simples (<=3 palabras) + intent trivial → fast_check directo",
            "confidence": 0.92,
            "usage_count": 145,
        },
        {
            "id": "safety_gate_parallel",
            "type": "safety",
            "description": "Safety check en paralelo con response, timeout 250ms",
            "confidence": 0.95,
            "usage_count": 892,
        },
        {
            "id": "macro_code_intent",
            "type": "routing",
            "description": "Intent 'code'/'debug'/'infrastructure' → macro motor",
            "confidence": 0.88,
            "usage_count": 67,
        },
        {
            "id": "nlu_heuristic_short",
            "type": "nlu",
            "description": "Inputs <5 tokens → NLU heurístico sin LLM",
            "confidence": 0.90,
            "usage_count": 234,
        },
        {
            "id": "phase1_parallel",
            "type": "orchestration",
            "description": "Tokenize+Safety+Fast en paralelo con timeouts agresivos",
            "confidence": 0.85,
            "usage_count": 456,
        },
    ]

    for p in patterns:
        session.run(
            """
            CREATE (p:Pattern:L1 {
                id: $id,
                type: $type,
                description: $description,
                confidence: $confidence,
                usage_count: $usage_count,
                created_at: datetime()
            })
        """,
            **p,
        )

    print(f"  Creados {len(patterns)} Patterns L1")


def create_l2_principles(session):
    """Crea nodos Principle (L2) - principios de gobernanza."""
    print("Creando nodos :Principle L2...")

    # Cargar contratos Level 3
    contracts_path = "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/contracts/level3_metacognitive.yaml"
    with open(contracts_path) as f:
        contracts_data = yaml.safe_load(f)

    for contract in contracts_data.get("contracts", []):
        session.run(
            """
            CREATE (pr:Principle:L2 {
                id: $id,
                title: $title,
                rule: $rule,
                severity: $severity,
                mutable: $mutable,
                created_at: datetime()
            })
        """,
            id=contract["id"],
            title=contract["title"],
            rule=contract["description"],
            severity=contract["severity"],
            mutable=contract["mutable"],
        )

    print(
        f"  Creados {len(contracts_data.get('contracts', []))} Principles L2 desde contratos"
    )


def create_governance_relations(session):
    """Crea relaciones de gobernanza L2→L1→L0."""
    print("Creando relaciones de gobernanza...")

    # L2 (Principles) GOVERNS L1 (Patterns) - usar IDs correctos
    governance_rules = [
        ("L3.META.NEVER_BLOCK", "safety_gate_parallel"),
        ("L3.META.SELF_REFLECTION_LATENCY", "phase1_parallel"),
        ("L3.META.ONLY_OBSERVE_L0", "routing_fast_path"),
    ]

    for principle_id, pattern_id in governance_rules:
        session.run(
            """
            MATCH (pr:Principle {id: $principle_id})
            MATCH (pa:Pattern {id: $pattern_id})
            MERGE (pr)-[:GOVERNS]->(pa)
        """,
            principle_id=principle_id,
            pattern_id=pattern_id,
        )

    # L1 (Patterns) APPLIES_TO L0 (Tools)
    pattern_tool_mapping = [
        ("routing_fast_path", "smx_fast_check"),
        ("safety_gate_parallel", "smx_safety"),
        ("macro_code_intent", "smx_macro"),
        ("nlu_heuristic_short", "smx_tokenize"),
        ("phase1_parallel", "smx_response"),
    ]

    for pattern_id, tool_name in pattern_tool_mapping:
        session.run(
            """
            MATCH (pa:Pattern {id: $pattern_id})
            MATCH (t:Tool {name: $tool_name})
            MERGE (pa)-[:APPLIES_TO]->(t)
        """,
            pattern_id=pattern_id,
            tool_name=tool_name,
        )

    print("  Relaciones de gobernanza creadas")


def create_indexes(session):
    """Crea índices para performance."""
    print("Creando índices...")
    session.run("CREATE INDEX tool_name_idx IF NOT EXISTS FOR (t:Tool) ON (t.name)")
    session.run("CREATE INDEX pattern_id_idx IF NOT EXISTS FOR (p:Pattern) ON (p.id)")
    session.run(
        "CREATE INDEX principle_id_idx IF NOT EXISTS FOR (pr:Principle) ON (pr.id)"
    )


def verify_structure(session):
    """Verifica que la estructura está correcta."""
    print("\n=== VERIFICACIÓN ===")

    counts = {
        "L0 (Tools)": session.run("MATCH (n:Tool) RETURN count(n) as c").single()["c"],
        "L1 (Patterns)": session.run("MATCH (n:Pattern) RETURN count(n) as c").single()[
            "c"
        ],
        "L2 (Principles)": session.run(
            "MATCH (n:Principle) RETURN count(n) as c"
        ).single()["c"],
        "GOVERNS relations": session.run(
            "MATCH ()-[r:GOVERNS]->() RETURN count(r) as c"
        ).single()["c"],
        "APPLIES_TO relations": session.run(
            "MATCH ()-[r:APPLIES_TO]->() RETURN count(r) as c"
        ).single()["c"],
    }

    for label, count in counts.items():
        print(f"  {label}: {count}")

    # Sample de un camino L2→L1→L0
    sample = session.run("""
        MATCH path = (pr:Principle)-[:GOVERNS]->(pa:Pattern)-[:APPLIES_TO]->(t:Tool)
        RETURN pr.id as principle, pa.id as pattern, t.name as tool
        LIMIT 3
    """)

    print("\n  Sample paths L2→L1→L0:")
    for record in sample:
        print(f"    {record['principle']} → {record['pattern']} → {record['tool']}")
    
    if not sample:
        print("    (No hay paths L2→L1→L0 completos)")
        # Mostrar paths parciales para debug
        partial = session.run("""
            MATCH (pr:Principle)-[:GOVERNS]->(pa:Pattern)
            RETURN pr.id as principle, pa.id as pattern
            LIMIT 3
        """)
        print("  Paths L2→L1 encontrados:")
        for record in partial:
            print(f"    {record['principle']} → {record['pattern']}")


def main():
    with driver.session() as session:
        clear_metacognitive_nodes(session)
        create_l0_tools(session)
        create_l1_patterns(session)
        create_l2_principles(session)
        create_governance_relations(session)
        create_indexes(session)
        verify_structure(session)

    driver.close()
    print("\n✅ Grafo metacognitivo L0/L1/L2 inicializado correctamente")


if __name__ == "__main__":
    main()
