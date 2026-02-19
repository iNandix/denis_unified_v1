"""Intent Queue — FastAPI app replacing blocking zenity.
Run: uvicorn control_plane.intent_queue_app:app --host 0.0.0.0 --port 8765
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from denis_unified_v1.graph.intent_writer import (
    create_intent,
    resolve_intent,
    get_pending_intents,
    get_last_n_decisions,
)
from denis_unified_v1.graph.db import neo4j_ping

app = FastAPI(title="Denis Intent Queue", version="1.0.0")


class IntentCreate(BaseModel):
    agent_id: str
    session_id: str
    semantic_delta: dict
    risk_score: int
    source_node: str = "nodo1"


class IntentResolve(BaseModel):
    human_id: str
    decision: str
    notes: str = ""
    consult_source: Optional[str] = None
    corrected_delta: Optional[dict] = None


@app.get("/health")
def health():
    return {"status": "ok", "neo4j": neo4j_ping()}


@app.post("/intent", status_code=201)
def post_intent(body: IntentCreate):
    intent_id = create_intent(
        agent_id=body.agent_id,
        session_id=body.session_id,
        semantic_delta=body.semantic_delta,
        risk_score=body.risk_score,
        source_node=body.source_node,
    )
    return {"intent_id": intent_id, "status": "pending"}


@app.post("/intent/{intent_id}/resolve")
def post_resolve(intent_id: str, body: IntentResolve):
    if body.decision not in ("approved", "rejected", "corrected"):
        raise HTTPException(status_code=400, detail=f"Invalid decision: {body.decision}")
    resolve_intent(
        intent_id=intent_id,
        human_id=body.human_id,
        decision=body.decision,
        notes=body.notes,
        consult_source=body.consult_source,
        corrected_delta=body.corrected_delta,
    )
    return {"intent_id": intent_id, "status": body.decision}


@app.get("/intent/pending")
def list_pending(limit: int = 20):
    return get_pending_intents(limit=limit)


@app.get("/intent/decisions")
def list_decisions(n: int = 20):
    return get_last_n_decisions(n=n)
