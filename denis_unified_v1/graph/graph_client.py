"""Fail-open Neo4j graph client for SSoT materialization.

SSoT principle:
- Graph stores operational state only (entities, relationships, counters, timestamps).
- No long text/snippets/prompt content is stored here.

Fail-open:
- If Neo4j is unreachable or secrets missing, all operations no-op and return False.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.guardrails.graph_write_policy import sanitize_graph_props


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GraphStatus:
    enabled: bool
    up: bool | None  # best-effort; do not hard-probe
    last_ok_ts: str
    last_err_ts: str
    errors_window: int


class GraphClient:
    def __init__(self) -> None:
        self.enabled = (os.getenv("GRAPH_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        self._driver = None
        self._last_ok_ts = ""
        self._last_err_ts = ""
        self._errors_window = 0

    def status(self) -> GraphStatus:
        # Do not probe network in status; reflect only client-local state.
        return GraphStatus(
            enabled=bool(self.enabled),
            up=None,
            last_ok_ts=self._last_ok_ts,
            last_err_ts=self._last_err_ts,
            errors_window=int(self._errors_window),
        )

    def _get_driver(self):
        if not self.enabled:
            return None

        if self._driver is not None:
            return self._driver

        password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
        if not password:
            return None

        uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
        user = os.getenv("NEO4J_USER", "neo4j")

        try:
            from neo4j import GraphDatabase  # type: ignore

            connect_timeout_s = float(os.getenv("DENIS_GRAPH_WRITE_CONNECT_TIMEOUT_S", "0.5"))
            self._driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                connection_timeout=connect_timeout_s,
            )
            return self._driver
        except Exception:
            return None

    def run_write(self, cypher: str, params: dict[str, Any] | None = None) -> bool:
        driver = self._get_driver()
        if driver is None:
            return False
        try:
            timeout_s = float(os.getenv("DENIS_GRAPH_WRITE_TIMEOUT_S", "1.2"))
            with driver.session() as session:
                session.run(cypher, **(params or {}), timeout=timeout_s)
            self._last_ok_ts = _utc_now_iso()
            return True
        except Exception:
            self._last_err_ts = _utc_now_iso()
            self._errors_window += 1
            return False

    # --- Upserts (node state only, no long text) ---
    def upsert_component(self, *, component_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (c:Component {id: $id})
        SET c += $props
        """
        return self.run_write(cypher, {"id": component_id, "props": safe})

    def upsert_provider(self, *, provider_id: str, kind: str | None = None) -> bool:
        cypher = """
        MERGE (p:Provider {id: $id})
        SET p.kind = COALESCE($kind, p.kind)
        """
        return self.run_write(cypher, {"id": provider_id, "kind": kind})

    def upsert_feature_flag(self, *, flag_id: str, value: str) -> bool:
        safe_val = sanitize_graph_props({"value": value}).props.get("value", "")
        cypher = """
        MERGE (f:FeatureFlag {id: $id})
        SET f.value = $value,
            f.updated_ts = $ts
        """
        return self.run_write(
            cypher, {"id": flag_id, "value": safe_val, "ts": _utc_now_iso()}
        )

    def upsert_run(self, *, run_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (r:Run {id: $id})
        SET r += $props
        """
        return self.run_write(cypher, {"id": run_id, "props": safe})

    def upsert_step(self, *, step_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (s:Step {id: $id})
        SET s += $props
        """
        return self.run_write(cypher, {"id": step_id, "props": safe})

    def upsert_artifact(self, *, artifact_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (a:Artifact {id: $id})
        SET a += $props
        """
        return self.run_write(cypher, {"id": artifact_id, "props": safe})

    def upsert_source(self, *, source_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (s:Source {id: $id})
        SET s += $props
        """
        return self.run_write(cypher, {"id": source_id, "props": safe})

    def upsert_voice_session(self, *, session_id: str, props: dict[str, Any]) -> bool:
        """Upsert minimal VoiceSession node (no audio/text stored)."""
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (v:VoiceSession {id: $id})
        SET v += $props
        """
        return self.run_write(cypher, {"id": session_id, "props": safe})

    # --- WS21-G Compiler metadata nodes (no raw text, hashes+len only) ---
    def upsert_intent_detection(self, *, detection_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (i:IntentDetection {id: $id})
        SET i += $props
        """
        return self.run_write(cypher, {"id": detection_id, "props": safe})

    def upsert_prompt_compile(self, *, compile_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (p:PromptCompile {id: $id})
        SET p += $props
        """
        return self.run_write(cypher, {"id": compile_id, "props": safe})

    def increment_voice_session_error(self, *, session_id: str, ts: str) -> bool:
        """Increment VoiceSession error_count (fail-open) and touch last_event_ts."""
        cypher = """
        MERGE (v:VoiceSession {id: $id})
        SET v.last_event_ts = $ts,
            v.status = COALESCE(v.status, 'error'),
            v.error_count = COALESCE(v.error_count, 0) + 1
        """
        safe_ts = sanitize_graph_props({"ts": ts}).props.get("ts") or ts
        return self.run_write(cypher, {"id": session_id, "ts": safe_ts})

    def upsert_intent_detection(self, *, detection_id: str, props: dict[str, Any]) -> bool:
        """Upsert metadata-only IntentDetection node (never store raw text)."""
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (i:IntentDetection {id: $id})
        SET i += $props
        """
        return self.run_write(cypher, {"id": detection_id, "props": safe})

    def upsert_prompt_compile(self, *, compile_id: str, props: dict[str, Any]) -> bool:
        """Upsert metadata-only PromptCompile node (never store raw prompt)."""
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (p:PromptCompile {id: $id})
        SET p += $props
        """
        return self.run_write(cypher, {"id": compile_id, "props": safe})

    # --- Edges (idempotent MERGE) ---
    def link_run_step(self, *, run_id: str, step_id: str, order: int) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (s:Step {id: $step_id})
        MERGE (r)-[rel:HAS_STEP]->(s)
        SET rel.order = $order
        """
        return self.run_write(cypher, {"run_id": run_id, "step_id": step_id, "order": int(order)})

    def link_run_intent_detection(self, *, run_id: str, detection_id: str) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (i:IntentDetection {id: $intent_id})
        MERGE (r)-[:HAS_INTENT]->(i)
        """
        return self.run_write(cypher, {"run_id": run_id, "intent_id": detection_id})

    def link_run_prompt_compile(self, *, run_id: str, compile_id: str) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (p:PromptCompile {id: $compile_id})
        MERGE (r)-[:HAS_PROMPT]->(p)
        """
        return self.run_write(cypher, {"run_id": run_id, "compile_id": compile_id})

    def link_step_artifact(self, *, step_id: str, artifact_id: str) -> bool:
        cypher = """
        MATCH (s:Step {id: $step_id})
        MATCH (a:Artifact {id: $artifact_id})
        MERGE (s)-[:PRODUCED]->(a)
        """
        return self.run_write(cypher, {"step_id": step_id, "artifact_id": artifact_id})

    def link_artifact_source(self, *, artifact_id: str, source_id: str) -> bool:
        cypher = """
        MATCH (a:Artifact {id: $artifact_id})
        MATCH (s:Source {id: $source_id})
        MERGE (a)-[:FROM_SOURCE]->(s)
        """
        return self.run_write(cypher, {"artifact_id": artifact_id, "source_id": source_id})

    def link_run_provider(self, *, run_id: str, provider_id: str, role: str) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (p:Provider {id: $provider_id})
        MERGE (r)-[rel:USED_PROVIDER]->(p)
        SET rel.role = $role
        """
        return self.run_write(cypher, {"run_id": run_id, "provider_id": provider_id, "role": role})

    def link_component_flag(self, *, component_id: str, flag_id: str) -> bool:
        cypher = """
        MATCH (c:Component {id: $component_id})
        MATCH (f:FeatureFlag {id: $flag_id})
        MERGE (c)-[:GATED_BY]->(f)
        """
        return self.run_write(cypher, {"component_id": component_id, "flag_id": flag_id})

    def link_component_depends_on(self, *, component_id: str, depends_on_id: str) -> bool:
        cypher = """
        MATCH (a:Component {id: $a})
        MATCH (b:Component {id: $b})
        MERGE (a)-[:DEPENDS_ON]->(b)
        """
        return self.run_write(cypher, {"a": component_id, "b": depends_on_id})

    def link_run_intent_detection(self, *, run_id: str, detection_id: str) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (i:IntentDetection {id: $detection_id})
        MERGE (r)-[:HAS_INTENT_DETECTION]->(i)
        """
        return self.run_write(cypher, {"run_id": run_id, "detection_id": detection_id})

    def link_run_prompt_compile(self, *, run_id: str, compile_id: str) -> bool:
        cypher = """
        MATCH (r:Run {id: $run_id})
        MATCH (p:PromptCompile {id: $compile_id})
        MERGE (r)-[:HAS_PROMPT_COMPILE]->(p)
        """
        return self.run_write(cypher, {"run_id": run_id, "compile_id": compile_id})

    # --- Control Room node upserts ---
    def upsert_task(self, *, task_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (t:Task {id: $id})
        SET t += $props
        """
        return self.run_write(cypher, {"id": task_id, "props": safe})

    def upsert_approval(self, *, approval_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (a:Approval {id: $id})
        SET a += $props
        """
        return self.run_write(cypher, {"id": approval_id, "props": safe})

    def upsert_action(self, *, action_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (a:Action {id: $id})
        SET a += $props
        """
        return self.run_write(cypher, {"id": action_id, "props": safe})

    # --- Control Room edges ---
    def link_task_run(self, *, task_id: str, run_id: str) -> bool:
        cypher = """
        MATCH (t:Task {id: $task_id})
        MATCH (r:Run {id: $run_id})
        MERGE (t)-[:SPAWNS]->(r)
        """
        return self.run_write(cypher, {"task_id": task_id, "run_id": run_id})

    def link_task_approval(self, *, task_id: str, approval_id: str) -> bool:
        cypher = """
        MATCH (t:Task {id: $task_id})
        MATCH (a:Approval {id: $approval_id})
        MERGE (t)-[:REQUIRES_APPROVAL]->(a)
        """
        return self.run_write(cypher, {"task_id": task_id, "approval_id": approval_id})

    def link_approval_run(self, *, approval_id: str, run_id: str) -> bool:
        cypher = """
        MATCH (a:Approval {id: $approval_id})
        MATCH (r:Run {id: $run_id})
        MERGE (a)-[:GOVERNS]->(r)
        """
        return self.run_write(cypher, {"approval_id": approval_id, "run_id": run_id})

    def link_approval_step(self, *, approval_id: str, step_id: str) -> bool:
        cypher = """
        MATCH (a:Approval {id: $approval_id})
        MATCH (s:Step {id: $step_id})
        MERGE (a)-[:GOVERNS]->(s)
        """
        return self.run_write(cypher, {"approval_id": approval_id, "step_id": step_id})

    def link_step_action(self, *, step_id: str, action_id: str, order: int) -> bool:
        cypher = """
        MATCH (s:Step {id: $step_id})
        MATCH (a:Action {id: $action_id})
        MERGE (s)-[rel:HAS_ACTION]->(a)
        SET rel.order = $order
        """
        return self.run_write(cypher, {"step_id": step_id, "action_id": action_id, "order": int(order)})

    # --- Read (fail-open, returns []) ---
    def run_read(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            timeout_s = float(os.getenv("DENIS_GRAPH_READ_TIMEOUT_S", "1.5"))
            with driver.session() as session:
                result = session.run(cypher, **(params or {}), timeout=timeout_s)
                return [dict(r) for r in result]
        except Exception:
            self._last_err_ts = _utc_now_iso()
            self._errors_window += 1
            return []

    # --- WS23-G NeuroLayer + ConsciousnessState ---
    def upsert_neuro_layer(self, *, layer_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (n:NeuroLayer {id: $id})
        SET n += $props
        """
        return self.run_write(cypher, {"id": layer_id, "props": safe})

    def upsert_consciousness_state(self, *, state_id: str, props: dict[str, Any]) -> bool:
        safe = sanitize_graph_props(props).props
        cypher = """
        MERGE (c:ConsciousnessState {id: $id})
        SET c += $props
        """
        return self.run_write(cypher, {"id": state_id, "props": safe})

    def link_identity_neuro_layer(self, *, identity_id: str, layer_id: str) -> bool:
        cypher = """
        MERGE (i:Identity {id: $identity_id})
        MERGE (n:NeuroLayer {id: $layer_id})
        MERGE (i)-[:HAS_NEURO_LAYER]->(n)
        """
        return self.run_write(cypher, {"identity_id": identity_id, "layer_id": layer_id})

    def link_identity_consciousness(self, *, identity_id: str, state_id: str) -> bool:
        cypher = """
        MERGE (i:Identity {id: $identity_id})
        MERGE (c:ConsciousnessState {id: $state_id})
        MERGE (i)-[:HAS_CONSCIOUSNESS_STATE]->(c)
        """
        return self.run_write(cypher, {"identity_id": identity_id, "state_id": state_id})

    def link_consciousness_layer(self, *, state_id: str, layer_id: str) -> bool:
        cypher = """
        MATCH (c:ConsciousnessState {id: $state_id})
        MATCH (n:NeuroLayer {id: $layer_id})
        MERGE (c)-[:DERIVED_FROM]->(n)
        """
        return self.run_write(cypher, {"state_id": state_id, "layer_id": layer_id})

    def link_step_component(self, *, step_id: str, component_id: str) -> bool:
        cypher = """
        MATCH (s:Step {id: $step_id})
        MATCH (c:Component {id: $component_id})
        MERGE (s)-[:TOUCHED]->(c)
        """
        return self.run_write(cypher, {"step_id": step_id, "component_id": component_id})


_CLIENT: GraphClient | None = None


def get_graph_client() -> GraphClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = GraphClient()
    return _CLIENT
