"""WS21-G compiler/router schemas (makina pipeline).

Establece el contrato entre Persona/Opencode → compiler → Makina executor.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# =============================================================================
# A) compiler.request (entrada desde Persona/Opencode)
# =============================================================================
class CompilerRequest(BaseModel):
    trace_id: str
    run_id: str
    actor_id: str | None = None

    text: str = Field(min_length=1)
    workspace: dict[str, Any] | None = None
    consciousness: dict[str, Any] | None = None

    hop_count: int = 0
    headers: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# B) retrieval.request (derivado del request)
# =============================================================================
class RetrievalRequest(BaseModel):
    trace_id: str
    run_id: str
    query: str

    sources: list[Literal["graph", "qdrant"]] = Field(default_factory=lambda: ["graph", "qdrant"])
    max_chunks: int = 12
    max_graph_entities: int = 40


# =============================================================================
# C) retrieval.result (desde graph + qdrant retrievers)
# =============================================================================
class GraphHit(BaseModel):
    node_ids: list[str] = Field(default_factory=list)
    edge_paths: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)


class VectorHit(BaseModel):
    chunk_ids: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    trace_id: str
    run_id: str

    graph_hits: GraphHit = Field(default_factory=GraphHit)
    vector_hits: VectorHit = Field(default_factory=VectorHit)

    graph_entity_count: int = 0
    chunk_count: int = 0

    graph_hash: str = ""
    chunks_hash: str = ""
    combined_hash: str = ""

    redactions_applied: bool = False
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# D) compiler.plan (del LLM, opcional para timeline UX)
# =============================================================================
class CompilerPlan(BaseModel):
    trace_id: str
    run_id: str
    plan: str = ""
    confidence: float = 0.0
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


# =============================================================================
# E) Makina DSL (contrato de salida)
# =============================================================================
class MakinaTask(BaseModel):
    id: str
    title: str
    intent: str | None = None
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    implicit_tasks: list[str] = Field(default_factory=list)


class MakinaStep(BaseModel):
    id: str
    kind: Literal["read", "write", "exec", "http_fallback", "ws_emit", "guard"]
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    guards: dict[str, Any] = Field(default_factory=dict)


class MakinaProgram(BaseModel):
    task: MakinaTask
    steps: list[MakinaStep] = Field(default_factory=list)
    observability: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# F) compiler.result (salida final, siempre emitido como evento)
# =============================================================================
class CompilerResult(BaseModel):
    trace_id: str
    run_id: str

    makina: str | MakinaProgram = ""

    compiler: Literal["chatroom", "fallback_local"] = "chatroom"
    degraded: bool = False

    model: str | None = None
    confidence: float = 0.0

    artifacts_expected: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    tool_policy: dict[str, Any] = Field(default_factory=dict)

    plan: str | None = None


# =============================================================================
# G) run.request (para executor downstream)
# =============================================================================
class RunRequest(BaseModel):
    trace_id: str
    run_id: str
    makina: str | MakinaProgram
    policy: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# H) políticas de retrieval
# =============================================================================
class RetrievalPolicy(BaseModel):
    graph: bool = True
    vectorstore: bool = True
    max_chunks: int = 12
    max_graph_entities: int = 40
