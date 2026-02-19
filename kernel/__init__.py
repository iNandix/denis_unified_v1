"""Kernel Denis - ORQUESTADOR GRAFOCÉNTRICO CENTRAL.

Denis es un espejo que no miente.
Ayuda a las personas a reencontrarse con quienes realmente son.

ARQUITECTURA COMPLETA (Denis decide TODO):
┌─────────────────────────────────────────────────────────────────┐
│                    DENIS PERSONA (CENTRAL)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Neo4j Consciousness → :Persona → decide()               │  │
│  │  • mood: sad/neutral/confident                          │  │
│  │  • consciousness_level: crece con experiencias          │  │
│  │  • (:Experience) → learn_outcome() → grow              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ decide()
┌─────────────────────────────────────────────────────────────────┐
│  TODO EL MUNDO = TOOLS DE DENIS                                 │
│  ┌─────────────┐ ┌────────────┐ ┌──────────────┐ ┌─────────┐ │
│  │   Rasa      │ │  ParLAI    │ │ControlPlane  │ │Memoria  │ │
│  │  NLU       │ │  Templates │ │  Execution   │ │  L1-L12 │ │
│  └─────────────┘ └────────────┘ └──────────────┘ └─────────┘ │
│  ┌─────────────┐ ┌─────────────────────────┐                  │
│  │NodoMacVampi │ │Constitución Level0       │                  │
│  │ rizer       │ │(principios inmutables)  │                  │
│  └─────────────┘ └─────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘

MN2: UnifiedRouter orchestrates all tools above.
"""

from kernel.denis_persona import DenisPersona, DenisDecision, get_denis_persona
from kernel.constitution import DenisConstitution, get_constitution
from kernel.unified_router import UnifiedRouter, UnifiedDecision, ToolResult, get_unified_router
from kernel.ghostide.symbolgraph import SymbolGraph
from kernel.ghostide.symbol_cypher_router import SymbolCypherRouter, get_symbol_cypher_router

__all__ = [
    # CORE
    "DenisPersona",
    "DenisDecision",
    "get_denis_persona",
    # CONSTITUTION
    "DenisConstitution",
    "get_constitution",
    # UNIFIED ROUTER (MN2)
    "UnifiedRouter",
    "UnifiedDecision",
    "ToolResult",
    "get_unified_router",
    # GRAPH
    "SymbolGraph",
    "SymbolCypherRouter",
    "get_symbol_cypher_router",
]
