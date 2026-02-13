"""
Active Metagraph (Fase 3).
Detecta patrones L1 en el grafo L0 y propone reorganizaciones.
"""
from neo4j import GraphDatabase
import os
from typing import List, Dict


class L1PatternDetector:
    """Detecta patrones emergentes en L0."""
    
    def __init__(self):
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD", "Leon1234$")
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    
    def detect_patterns(self) -> List[Dict]:
        """
        Detecta patrones en L0:
        - Bucles de conversación
        - Nodos huérfanos
        - Clusters de herramientas
        - Drift de métricas
        """
        patterns = []
        
        with self.driver.session() as session:
            # Patrón 1: Herramientas con baja success_rate
            low_success = session.run("""
                MATCH (t:Tool)
                WHERE t.success_rate < 0.85
                RETURN t.name as tool, t.success_rate as rate
            """)
            for record in low_success:
                patterns.append({
                    "type": "low_success_rate",
                    "tool": record["tool"],
                    "metric": record["rate"],
                    "severity": "medium",
                    "proposal": f"Investigar por qué {record['tool']} tiene success_rate bajo",
                })
            
            # Patrón 2: Herramientas con latencia alta
            high_latency = session.run("""
                MATCH (t:Tool)
                WHERE t.avg_latency_ms > 1000
                RETURN t.name as tool, t.avg_latency_ms as latency
            """)
            for record in high_latency:
                patterns.append({
                    "type": "high_latency",
                    "tool": record["tool"],
                    "metric": record["latency"],
                    "severity": "medium",
                    "proposal": f"Optimizar {record['tool']} para reducir latencia",
                })
            
            # Patrón 3: Patterns L1 con baja confidence
            low_conf_patterns = session.run("""
                MATCH (p:Pattern)
                WHERE p.confidence < 0.85
                RETURN p.id as pattern, p.confidence as conf
            """)
            for record in low_conf_patterns:
                patterns.append({
                    "type": "low_confidence_pattern",
                    "pattern": record["pattern"],
                    "metric": record["conf"],
                    "severity": "low",
                    "proposal": f"Revisar pattern {record['pattern']} - puede no ser válido",
                })
        
        return patterns


class L1Reorganizer:
    """Propone reorganizaciones basadas en patrones detectados."""
    
    def propose_reorganizations(self, patterns: List[Dict]) -> List[Dict]:
        """Genera propuestas concretas de reorganización."""
        proposals = []
        
        for pattern in patterns:
            if pattern["type"] == "low_success_rate":
                proposals.append({
                    "action": "disable_tool",
                    "target": pattern["tool"],
                    "reason": f"Success rate {pattern['metric']:.2f} < threshold",
                    "priority": "medium",
                })
            
            elif pattern["type"] == "high_latency":
                proposals.append({
                    "action": "add_timeout",
                    "target": pattern["tool"],
                    "timeout_ms": 500,
                    "reason": f"Latency {pattern['metric']:.0f}ms > 1000ms",
                    "priority": "high",
                })
            
            elif pattern["type"] == "low_confidence_pattern":
                proposals.append({
                    "action": "review_pattern",
                    "target": pattern["pattern"],
                    "reason": f"Confidence {pattern['metric']:.2f} < 0.85",
                    "priority": "low",
                })
        
        return proposals