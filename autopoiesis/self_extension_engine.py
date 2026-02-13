"""Self-Extension Engine - Fase 4 del roadmap metacognitivo."""
from denis_unified_v1.autopoiesis.capability_detector import CapabilityGapDetector, ExtensionProposer
from denis_unified_v1.autopoiesis.approval_engine import ApprovalEngine

class SelfExtensionEngine:
    """Motor de auto-extensión supervisada."""
    
    def __init__(self):
        self.gap_detector = CapabilityGapDetector()
        self.extension_proposer = ExtensionProposer()
        self.approval_engine = ApprovalEngine()
    
    async def run_cycle(self) -> dict:
        """
        Ciclo completo de auto-extensión:
        1. Detectar gaps
        2. Proponer extensiones
        3. Enviar a aprobación humana
        """
        # 1) Detectar gaps
        gaps = self.gap_detector.detect_gaps()
        
        # 2) Proponer extensiones
        proposals = self.extension_proposer.propose_extensions(gaps)
        
        # 3) Enviar a aprobación (respeta contrato L3)
        submitted = []
        for proposal in proposals:
            proposal_id = self.approval_engine.submit_proposal(proposal)
            submitted.append(proposal_id)
        
        return {
            "gaps_detected": len(gaps),
            "proposals_generated": len(proposals),
            "proposals_submitted": submitted,
            "status": "awaiting_approval",
        }
