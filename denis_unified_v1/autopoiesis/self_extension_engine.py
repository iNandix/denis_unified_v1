"""Self-Extension Engine - Fase 4 del roadmap metacognitivo."""

import os
import sys
from pathlib import Path

from denis_unified_v1.autopoiesis.capability_detector import (
    CapabilityGapDetector,
    ExtensionProposer,
)
from denis_unified_v1.autopoiesis.approval_engine import ApprovalEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREFLIGHT_PY = PROJECT_ROOT / ".venv_preflight" / "bin" / "python3"

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


def create_self_extension_engine(*args, **kwargs) -> SelfExtensionEngine:
    """Factory helper usado por scripts legacy (fail-open)."""
    engine = SelfExtensionEngine(*args, **kwargs)

    sandbox_env = os.getenv("DENIS_SANDBOX_PYTHON")
    if sandbox_env:
        sandbox_python = sandbox_env
    elif DEFAULT_PREFLIGHT_PY.exists():
        sandbox_python = str(DEFAULT_PREFLIGHT_PY)
    else:
        sandbox_python = sys.executable

    strict_env = os.getenv("DENIS_STRICT_TOOLING")
    strict_default = True if strict_env is None else strict_env.lower() in {
        "1",
        "true",
        "yes",
    }

    defaults = {
        "_sandbox_python": sandbox_python,
        "_sandbox_timeout_seconds": int(
            os.getenv("DENIS_SANDBOX_TIMEOUT_SECONDS", "30")
        ),
        "_strict_tooling": strict_default,
    }

    for attr, value in defaults.items():
        if not hasattr(engine, attr):
            setattr(engine, attr, value)

    return engine
