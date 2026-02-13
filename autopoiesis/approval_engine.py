"""Motor de aprobación de extensiones (respeta contrato L3.METACOGNITION.HUMAN_APPROVAL_FOR_GROWTH)."""
import json
import time
from typing import Dict, List
from neo4j import GraphDatabase
import os

class ApprovalEngine:
    """Gestiona aprobaciones de extensiones propuestas."""
    
    def __init__(self):
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD", "Leon1234$")
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    
    def submit_proposal(self, proposal: Dict) -> str:
        """Guarda propuesta en Neo4j para aprobación humana."""
        with self.driver.session() as session:
            result = session.run("""
                CREATE (p:Proposal {
                    id: $id,
                    type: $type,
                    target: $target,
                    priority: $priority,
                    estimated_impact: $estimated_impact,
                    status: 'pending',
                    created_at: datetime(),
                    approved_by: null,
                    approved_at: null
                })
                RETURN p.id as proposal_id
            """, 
                id=proposal["id"],
                type=proposal["type"],
                target=proposal["target"],
                priority=proposal["priority"],
                estimated_impact=proposal["estimated_impact"]
            )
            
            return result.single()["proposal_id"]
    
    def get_pending_proposals(self) -> List[Dict]:
        """Obtiene propuestas pendientes de aprobación."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Proposal)
                WHERE p.status = 'pending'
                RETURN p.id, p.type, p.target, p.priority, p.estimated_impact
                ORDER BY p.created_at DESC
            """)
            
            return [dict(record) for record in result]
    
    def approve_proposal(self, proposal_id: str, approved_by: str) -> bool:
        """Aprueba propuesta (simula decisión humana)."""
        with self.driver.session() as session:
            session.run("""
                MATCH (p:Proposal {id: $id})
                SET p.status = 'approved',
                    p.approved_by = $approved_by,
                    p.approved_at = datetime()
            """, id=proposal_id, approved_by=approved_by)
            
            return True
    
    def reject_proposal(self, proposal_id: str, reason: str) -> bool:
        """Rechaza propuesta."""
        with self.driver.session() as session:
            session.run("""
                MATCH (p:Proposal {id: $id})
                SET p.status = 'rejected',
                    p.rejection_reason = $reason,
                    p.rejected_at = datetime()
            """, id=proposal_id, reason=reason)
            
            return True