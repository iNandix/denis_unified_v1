"""
Active Metagraph - Meta-grafo activo con niveles L1/L2.

Implementa:
- L1PatternDetector: detecta patrones en L0
- L1Reorganizer: propone reorganizaciones
- L2PrincipleEngine: mantiene principios
- L2Governance: decide aprobar/rechazar propuestas

Depende de:
- metagraph/observer.py (existente)
- metacognitive/hooks.py (TICKET F0)
- contracts/level*.yaml (contratos existentes)

Contratos aplicados:
- L3.META.ONLY_OBSERVE_L0
- L3.META.NEVER_BLOCK
- L3.ROUTER.FALLBACK_LEGACY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
from collections import defaultdict

from neo4j import GraphDatabase

from denis_unified_v1.metagraph.observer import collect_graph_metrics
from denis_unified_v1.metacognitive.hooks import (
    get_hooks,
    emit_reflection,
    metacognitive_trace,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_neo4j_driver():
    uri = "bolt://10.10.10.1:7687"
    user = "neo4j"
    password = ""
    import os

    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or ""
    if password:
        return GraphDatabase.driver(uri, auth=(user, password))
    return None


@dataclass
class Pattern:
    """Patrón detectado en el grafo."""

    id: str
    type: str
    severity: str
    description: str
    entities: list[str]
    metrics: dict[str, Any]
    proposal: str | None
    timestamp_utc: str


@dataclass
class ReorganizationProposal:
    """Propuesta de reorganización del grafo."""

    id: str
    pattern_id: str
    type: str
    description: str
    cypher_query: str
    rollback_query: str
    risk_level: str
    expected_benefit: str
    status: str
    timestamp_utc: str


@dataclass
class Principle:
    """Principio del nivel L2."""

    id: str
    name: str
    category: str
    weight: float
    description: str
    contracts: list[str]
    violations: int


class PatternDetector:
    """Detecta patrones en el grafo L0."""

    PATTERN_TYPES = {
        "orphan": {
            "query": "MATCH (n) WHERE NOT (n)--() RETURN n LIMIT $limit",
            "severity": "medium",
            "description": "Nodos sin conexiones",
        },
        "cycle_2hop": {
            "query": "MATCH (a)-[]->(b)-[]->(a) RETURN a, b LIMIT $limit",
            "severity": "low",
            "description": "Ciclos de 2 saltos",
        },
        "hub": {
            "query": "MATCH (n) WITH n, COUNT { (n)--() } AS d ORDER BY d DESC LIMIT $limit RETURN n, d",
            "severity": "info",
            "description": "Hubs con alto grado",
        },
        "temporal_drift": {
            "query": "MATCH (n) WHERE n.timestamp < $threshold RETURN n LIMIT $limit",
            "severity": "medium",
            "description": "Nodos con timestamp antiguo",
        },
        "type_concentration": {
            "query": "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY c DESC LIMIT $limit",
            "severity": "info",
            "description": "Concentración por tipo",
        },
    }

    def __init__(self):
        self._detected_patterns: list[Pattern] = []

    @metacognitive_trace("pattern_detection")
    def detect_all(
        self,
        metrics: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[Pattern]:
        self._detected_patterns = []

        if metrics is None:
            try:
                metrics = collect_graph_metrics(
                    label_limit=20, hub_limit=20, sample_node_limit=100
                )
            except Exception:
                emit_reflection(
                    reflection_type="pattern_detection_skipped",
                    target="neo4j",
                    finding="No se pudo acceder a Neo4j",
                    confidence=0.5,
                    recommendation="Verificar conexión a Neo4j",
                )
                return []

        orphans_count = metrics.get("metrics", {}).get("orphan_nodes", 0)
        if orphans_count > 0:
            self._detected_patterns.append(
                Pattern(
                    id=f"pat_orphan_{_utc_now()[:10]}",
                    type="orphan",
                    severity=self.PATTERN_TYPES["orphan"]["severity"],
                    description=f"Encontrados {orphans_count} nodos huérfanos",
                    entities=[],
                    metrics={"count": orphans_count},
                    proposal="Crear aristas según tipo de nodo",
                    timestamp_utc=_utc_now(),
                )
            )

        cycles_count = metrics.get("metrics", {}).get("two_hop_cycles", 0)
        if cycles_count > 0:
            self._detected_patterns.append(
                Pattern(
                    id=f"pat_cycle_{_utc_now()[:10]}",
                    type="cycle_2hop",
                    severity=self.PATTERN_TYPES["cycle_2hop"]["severity"],
                    description=f"Encontrados {cycles_count} ciclos de 2 saltos",
                    entities=[],
                    metrics={"count": cycles_count},
                    proposal="Verificar si los ciclos son intencionales",
                    timestamp_utc=_utc_now(),
                )
            )

        top_hubs = metrics.get("top_hubs", [])[:5]
        if top_hubs:
            hub_ids = [h.get("node_ref", "unknown") for h in top_hubs]
            self._detected_patterns.append(
                Pattern(
                    id=f"pat_hub_{_utc_now()[:10]}",
                    type="hub",
                    severity=self.PATTERN_TYPES["hub"]["severity"],
                    description=f"Encontrados {len(top_hubs)} hubs principales",
                    entities=hub_ids,
                    metrics={"hubs": hub_ids},
                    proposal="Monitorear carga en hubs",
                    timestamp_utc=_utc_now(),
                )
            )

        missing_ts = metrics.get("metrics", {}).get("missing_timestamp_nodes", 0)
        if missing_ts > 0:
            self._detected_patterns.append(
                Pattern(
                    id=f"pat_temporal_{_utc_now()[:10]}",
                    type="temporal_drift",
                    severity=self.PATTERN_TYPES["temporal_drift"]["severity"],
                    description=f"{missing_ts} nodos sin timestamp",
                    entities=[],
                    metrics={"count": missing_ts},
                    proposal="Añadir timestamps a nodos pendientes",
                    timestamp_utc=_utc_now(),
                )
            )

        label_dist = metrics.get("label_distribution", [])
        if len(label_dist) > 10:
            self._detected_patterns.append(
                Pattern(
                    id=f"pat_type_{_utc_now()[:10]}",
                    type="type_concentration",
                    severity=self.PATTERN_TYPES["type_concentration"]["severity"],
                    description=f"{len(label_dist)} tipos de labels detectados",
                    entities=[l.get("label", "unknown") for l in label_dist[:10]],
                    metrics={"distribution": label_dist[:10]},
                    proposal="Revisar necesidad de tipos tan granulares",
                    timestamp_utc=_utc_now(),
                )
            )

        for pattern in self._detected_patterns:
            emit_reflection(
                reflection_type="pattern_detected",
                target=pattern.type,
                finding=pattern.description,
                confidence=1.0 if pattern.severity == "critical" else 0.7,
                recommendation=pattern.proposal,
            )

        return self._detected_patterns

    def get_patterns(self, severity: str | None = None) -> list[Pattern]:
        if severity:
            return [p for p in self._detected_patterns if p.severity == severity]
        return self._detected_patterns


class Reorganizer:
    """Genera propuestas de reorganización basadas en patrones."""

    def __init__(self):
        self._proposals: list[ReorganizationProposal] = []

    def generate_proposal(
        self,
        pattern: Pattern,
        context: dict[str, Any] | None = None,
    ) -> ReorganizationProposal | None:
        if pattern.type == "orphan":
            query, rollback = self._generate_orphan_proposal(pattern, context)
        elif pattern.type == "temporal_drift":
            query, rollback = self._generate_temporal_proposal(pattern, context)
        else:
            return None

        proposal = ReorganizationProposal(
            id=f"prop_{pattern.id}",
            pattern_id=pattern.id,
            type=pattern.type,
            description=pattern.description,
            cypher_query=query,
            rollback_query=rollback,
            risk_level=self._calculate_risk(pattern),
            expected_benefit=pattern.proposal or "Mejora de coherencia",
            status="pending",
            timestamp_utc=_utc_now(),
        )

        self._proposals.append(proposal)

        emit_reflection(
            reflection_type="reorganization_proposal",
            target=proposal.id,
            finding=proposal.description,
            confidence=0.8,
            recommendation=f"Riesgo: {proposal.risk_level}",
        )

        return proposal

    def _generate_orphan_proposal(
        self,
        pattern: Pattern,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        query = """
            MATCH (n WHERE NOT (n)--())
            WITH n LIMIT 100
            MATCH (m WHERE (n<>m) AND (m)--())
            WITH n, m, COUNT { (m)--() } AS connection_score
            ORDER BY connection_score DESC
            WITH n, m LIMIT 1
            MERGE (n)-[:CONNECTED {source: "auto_reorganize", timestamp: datetime()}]->(m)
            RETURN n.id, m.id
        """

        rollback = """
            MATCH (n)-[r:CONNECTED {source: "auto_reorganize"}]->(m)
            DELETE r
            RETURN count(r) AS removed
        """

        return query, rollback

    def _generate_temporal_proposal(
        self,
        pattern: Pattern,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        query = """
            MATCH (n WHERE n.timestamp IS NULL AND n.created_at IS NULL)
            WITH n LIMIT 100
            SET n.timestamp = datetime(),
                n.updated_at = datetime()
            RETURN count(n) AS updated
        """

        rollback = """
            MATCH (n WHERE n.updated_at >= datetime() - duration({seconds: 60}))
            SET n.timestamp = NULL,
                n.updated_at = NULL
            RETURN count(n) AS reverted
        """

        return query, rollback

    def _calculate_risk(self, pattern: Pattern) -> str:
        if pattern.severity == "critical":
            return "high"
        elif pattern.severity == "medium":
            return "medium"
        return "low"

    def get_proposals(self, status: str | None = None) -> list[ReorganizationProposal]:
        if status:
            return [p for p in self._proposals if p.status == status]
        return self._proposals


class PrincipleEngine:
    """Mantiene y aplica principios del nivel L2."""

    DEFAULT_PRINCIPLES = [
        {
            "id": "p_coherence",
            "name": "Coherencia",
            "category": "structural",
            "weight": 0.9,
            "description": "El grafo debe mantener coherencia estructural",
            "contracts": ["L1.COHERENCE.NO_STRONG_CONTRADICTION"],
        },
        {
            "id": "p_connectivity",
            "name": "Conectividad",
            "category": "structural",
            "weight": 0.8,
            "description": "Los nodos deben estar conectados cuando sea posible",
            "contracts": ["L1.TOPOLOGY.MIN_CONNECTIVITY"],
        },
        {
            "id": "p_freshness",
            "name": "Freshness",
            "category": "temporal",
            "weight": 0.7,
            "description": "La información debe estar actualizada",
            "contracts": [],
        },
        {
            "id": "p_safety",
            "name": "Seguridad",
            "category": "safety",
            "weight": 1.0,
            "description": "Nunca violar contratos de seguridad",
            "contracts": ["L0.SAFETY.NO_SECRET_LOGGING"],
        },
    ]

    def __init__(self):
        self._principles: list[Principle] = []
        self._violations: dict[str, int] = defaultdict(int)

        for p in self.DEFAULT_PRINCIPLES:
            self._principles.append(
                Principle(
                    id=p["id"],
                    name=p["name"],
                    category=p["category"],
                    weight=p["weight"],
                    description=p["description"],
                    contracts=p["contracts"],
                    violations=0,
                )
            )

    def evaluate_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        violations = []
        score = 1.0

        for principle in self._principles:
            if principle.category == "safety":
                if self._violates_safety(principle, params):
                    violations.append(f"Viola principio: {principle.name}")
                    self._violations[principle.id] += 1
                    principle.violations += 1
                    score *= 1 - principle.weight

        if violations:
            emit_reflection(
                reflection_type="principle_violation",
                target=action,
                finding=f"{len(violations)} violaciones detectadas",
                confidence=1.0 - score,
                recommendation="Revisar acción antes de ejecutar",
            )

        return len(violations) == 0, violations

    def _violates_safety(self, principle: Principle, params: dict[str, Any]) -> bool:
        if "secret" in str(params).lower():
            return True
        if "password" in str(params).lower():
            return True
        if "token" in str(params).lower():
            return True
        return False

    def get_principles(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "weight": p.weight,
                "description": p.description,
                "violations": p.violations,
            }
            for p in self._principles
        ]


class Governance:
    """Decide aprobar/rechazar propuestas del L1."""

    def __init__(self):
        self._principles = PrincipleEngine()
        self._reorganizer = Reorganizer()
        self._decisions: list[dict[str, Any]] = []

    def review_proposal(
        self,
        proposal: ReorganizationProposal,
    ) -> dict[str, Any]:
        approved = True
        reasons = []

        if proposal.risk_level == "high":
            approved = False
            reasons.append("Riesgo demasiado alto para aprobación automática")

        principle_check, violations = self._principles.evaluate_action(
            "proposal_review",
            {"proposal": proposal.id, "type": proposal.type},
        )

        if not principle_check:
            approved = False
            reasons.extend(violations)

        decision = {
            "proposal_id": proposal.id,
            "approved": approved,
            "reasons": reasons,
            "timestamp_utc": _utc_now(),
            "reviewer": "L2_Governance",
        }

        self._decisions.append(decision)

        proposal.status = "approved" if approved else "rejected"
        proposal.timestamp_utc = _utc_now()

        emit_reflection(
            reflection_type="governance_decision",
            target=proposal.id,
            finding=f"Decisión: {'APROBADO' if approved else 'RECHAZADO'}",
            confidence=1.0 if approved else 0.5,
            recommendation=", ".join(reasons) if reasons else "Sin recomendaciones",
        )

        return decision

    def get_decisions(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return [
                d for d in self._decisions if d["approved"] == (status == "approved")
            ]
        return self._decisions


class ActiveMetagraph:
    """Meta-grafo activo con niveles L1/L2."""

    def __init__(self):
        self._hooks = get_hooks()
        self._pattern_detector = PatternDetector()
        self._reorganizer = Reorganizer()
        self._governance = Governance()
        self._principles = PrincipleEngine()

    @metacognitive_trace("active_metagraph_scan")
    def scan_and_analyze(
        self,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        patterns = self._pattern_detector.detect_all(metrics)

        proposals = []
        for pattern in patterns:
            if pattern.severity in ["medium", "high"]:
                proposal = self._reorganizer.generate_proposal(pattern)
                if proposal:
                    proposals.append(proposal)

        return {
            "patterns_detected": len(patterns),
            "patterns": [
                {
                    "id": p.id,
                    "type": p.type,
                    "severity": p.severity,
                    "description": p.description,
                    "proposal": p.proposal,
                }
                for p in patterns
            ],
            "proposals_generated": len(proposals),
            "proposals": [
                {
                    "id": prop.id,
                    "type": prop.type,
                    "risk_level": prop.risk_level,
                    "status": prop.status,
                }
                for prop in proposals
            ],
            "timestamp_utc": _utc_now(),
        }

    def review_proposal(self, proposal: ReorganizationProposal) -> dict[str, Any]:
        return self._governance.review_proposal(proposal)

    def get_status(self) -> dict[str, Any]:
        return {
            "pattern_detector": "active",
            "reorganizer": "active",
            "governance": "active",
            "principles_count": len(self._principles.get_principles()),
            "patterns_detected": len(self._pattern_detector.get_patterns()),
            "proposals_pending": len(self._reorganizer.get_proposals("pending")),
        }

    def get_principles(self) -> list[dict[str, Any]]:
        return self._principles.get_principles()


def create_active_metagraph() -> ActiveMetagraph:
    return ActiveMetagraph()


if __name__ == "__main__":
    import json

    print("=== ACTIVE METAGRAPH ===")
    am = create_active_metagraph()
    print(json.dumps(am.get_status(), indent=2))

    print("\n=== SCAN AND ANALYZE ===")
    result = am.scan_and_analyze()
    print(
        json.dumps(
            {
                "patterns_detected": result["patterns_detected"],
                "proposals_generated": result["proposals_generated"],
            },
            indent=2,
        )
    )

    print("\n=== PATTERNS ===")
    for pattern in result["patterns"][:3]:
        print(f"- {pattern['type']}: {pattern['description']}")

    print("\n=== PRINCIPLES ===")
    for principle in am.get_principles():
        print(
            f"- {principle['name']}: weight={principle['weight']}, violations={principle['violations']}"
        )
