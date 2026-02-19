"""Graph Materialization Layer (GML) from `event_v1` (fail-open).

Consumes WS/SQLite events and materializes operational state into Graph (SSoT).

Idempotency:
- mutation_id = sha256(event_id + mutation_kind + stable_key)
- stored in a local SQLite dedupe table so reprocessing doesn't reapply.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from denis_unified_v1.graph.graph_client import GraphClient, get_graph_client
from denis_unified_v1.graph.materializers.mappings_v1 import SUPPORTED_EVENT_TYPES_V1, MappingResult


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _gml_db_path() -> str:
    return os.getenv("DENIS_GML_DB_PATH", "./var/denis_gml.db")


def _ensure_dir(path: str) -> None:
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
    except Exception:
        return


def _db() -> sqlite3.Connection:
    path = _gml_db_path()
    _ensure_dir(path)
    conn = sqlite3.connect(path, timeout=0.2)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gml_mutations (
          mutation_id TEXT PRIMARY KEY,
          ts TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


@dataclass
class MaterializerStats:
    last_mutation_ts: str = ""
    last_event_ts: str = ""
    last_lag_ms: int = 0
    errors_window: int = 0


_STATS = MaterializerStats()


def get_materializer_stats() -> dict[str, Any]:
    return {
        "last_mutation_ts": _STATS.last_mutation_ts or "",
        "last_event_ts": _STATS.last_event_ts or "",
        "lag_ms": int(_STATS.last_lag_ms),
        "errors_window": int(_STATS.errors_window),
        "graph_up": None,  # best-effort; no hard probe
    }


def _event_ts_to_ms(ts: str) -> int | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _compute_lag_ms(event_ts: str) -> int:
    ems = _event_ts_to_ms(event_ts) or 0
    if ems <= 0:
        return 0
    return max(0, int(time.time() * 1000) - int(ems))


def _try_acquire_mutation(mutation_id: str) -> bool:
    try:
        conn = _db()
        try:
            conn.execute("INSERT INTO gml_mutations (mutation_id, ts) VALUES (?, ?)", (mutation_id, _utc_now_iso()))
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.IntegrityError:
        return False
    except Exception:
        # Fail-open: if dedupe store fails, allow mutation but keep graph ops MERGE-idempotent.
        return True


def _run_id(conversation_id: str, turn_id: str) -> str:
    return _sha256(f"{conversation_id}:{turn_id}")


def _stable_mutation_id(*, event_id: int, mutation_kind: str, stable_key: str) -> str:
    return _sha256(f"{event_id}:{mutation_kind}:{stable_key}")


def _materialize_flags(graph: GraphClient) -> None:
    # Minimal gating representation.
    flags = [
        "VECTORSTORE_ENABLED",
        "RAG_ENABLED",
        "INDEXING_ENABLED",
        "PRO_SEARCH_ENABLED",
        "SCRAPING_ENABLED",
        "MULTIVERSE_MODE",
    ]
    components = {
        "vectorstore_qdrant": ["VECTORSTORE_ENABLED"],
        "pro_search": ["PRO_SEARCH_ENABLED", "VECTORSTORE_ENABLED"],
        "rag_context_builder": ["RAG_ENABLED", "PRO_SEARCH_ENABLED"],
        "advanced_scraping": ["SCRAPING_ENABLED"],
        "ws_event_bus": [],
        "chunker": [],
        "redaction_gate": [],
        "control_room": [],
    }

    for fid in flags:
        val = (os.getenv(fid) or "").strip()
        graph.upsert_feature_flag(flag_id=fid, value=val)

    for cid, gating in components.items():
        graph.upsert_component(
            component_id=cid,
            props={"freshness_ts": _utc_now_iso(), "status": "unknown"},
        )
        for fid in gating:
            graph.link_component_flag(component_id=cid, flag_id=fid)

    # Minimal dependency graph
    graph.link_component_depends_on(component_id="rag_context_builder", depends_on_id="pro_search")
    graph.link_component_depends_on(component_id="pro_search", depends_on_id="vectorstore_qdrant")
    graph.link_component_depends_on(component_id="pro_search", depends_on_id="redaction_gate")
    graph.link_component_depends_on(component_id="pro_search", depends_on_id="chunker")
    graph.link_component_depends_on(component_id="ws_event_bus", depends_on_id="control_room")


def materialize_event(event: dict[str, Any], *, graph: GraphClient | None = None) -> MappingResult:
    """Materialize a single `event_v1` dict into Graph. Never raises."""
    g = graph or get_graph_client()
    if not g.enabled:
        return MappingResult(handled=False)

    try:
        etype = str(event.get("type") or "")
        if not etype:
            return MappingResult(handled=False)

        # Update materializer stats (best-effort).
        _STATS.last_event_ts = str(event.get("ts") or "")
        _STATS.last_lag_ms = _compute_lag_ms(_STATS.last_event_ts)

        # Seed minimal component/flag graph (idempotent MERGE).
        try:
            seed_mid = _stable_mutation_id(event_id=0, mutation_kind="seed_flags", stable_key="v1")
            if _try_acquire_mutation(seed_mid):
                _materialize_flags(g)
        except Exception:
            pass

        if etype not in SUPPORTED_EVENT_TYPES_V1:
            # Unknown events are not materialized; mark ws_event_bus freshness and return.
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="unknown_event",
                stable_key=etype,
            )
            if _try_acquire_mutation(mid):
                g.upsert_component(
                    component_id="ws_event_bus",
                    props={"freshness_ts": _utc_now_iso(), "status": "ok"},
                )
            return MappingResult(handled=False, component_id="ws_event_bus", mutation_kinds=["unknown_event"])

        conv = str(event.get("conversation_id") or "default")
        trace_id = event.get("trace_id")
        # Prefer envelope turn_id when available (WS16). Fall back to trace_id for legacy emitters.
        turn_id = str(event.get("turn_id") or trace_id or f"event_{event.get('event_id')}")
        ts = str(event.get("ts") or _utc_now_iso())
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

        # Prefer explicit SSoT run_id when the event provides one (e.g. Control Room, explicit run.step).
        # Fallback to envelope-derived run id for generic pipeline events.
        rid = str(payload.get("run_id") or "") or _run_id(conv, turn_id)

        # Always upsert the Run (operational transaction envelope).
        mid_run = _stable_mutation_id(
            event_id=int(event.get("event_id") or 0),
            mutation_kind="upsert_run",
            stable_key=rid,
        )
        if _try_acquire_mutation(mid_run):
            g.upsert_run(
                run_id=rid,
                props={
                    "conversation_id": conv,
                    "turn_id": turn_id,
                    "trace_id": trace_id,
                    "ts": ts,
                    "status": "running",
                },
            )

        # Event-specific mappings.
        if etype == "run.step":
            step_id = str(payload.get("step_id") or "")
            if not step_id:
                return MappingResult(handled=False)
            state = str(payload.get("state") or payload.get("status") or "").strip().upper()
            name = str(payload.get("name") or payload.get("step_name") or "")
            tool = str(payload.get("tool") or "")
            order = int(payload.get("order") or 0)
            component_id = str(payload.get("component_id") or "")
            artifact_id = str(payload.get("artifact_id") or "")
            artifact_kind = str(payload.get("artifact_kind") or "step_outcome")
            counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}

            status_map = {
                "QUEUED": "queued",
                "RUNNING": "running",
                "SUCCESS": "success",
                "FAILED": "failed",
                "STALE": "stale",
            }
            step_status = status_map.get(state, "running" if state else "running")

            stable_key = f"{rid}:{step_id}:{state}:{order}"
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="run_step",
                stable_key=stable_key,
            )
            if _try_acquire_mutation(mid):
                g.upsert_step(
                    step_id=step_id,
                    props={
                        "run_id": rid,
                        "name": name,
                        "tool": tool,
                        "order": int(order),
                        "status": step_status,
                        "ts": ts,
                    },
                )
                g.link_run_step(run_id=rid, step_id=step_id, order=int(order))

                if component_id:
                    g.upsert_component(component_id=component_id, props={"freshness_ts": ts, "status": "ok"})
                    g.link_step_component(step_id=step_id, component_id=component_id)

                if artifact_id:
                    try:
                        counts_json = json.dumps(counts, ensure_ascii=True, sort_keys=True)[:8000]
                    except Exception:
                        counts_json = json.dumps({"fields": len(counts or {})}, ensure_ascii=True)
                    g.upsert_artifact(
                        artifact_id=artifact_id,
                        props={
                            "kind": artifact_kind,
                            "ts": ts,
                            "hash_sha256": artifact_id,
                            "counts_json": counts_json,
                        },
                    )
                    g.link_step_artifact(step_id=step_id, artifact_id=artifact_id)

                g.upsert_component(component_id="ws_event_bus", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="ws_event_bus", mutation_kinds=["run_step"])

        if etype == "rag.search.start":
            step_name = "pro_search"
            sid = _sha256(f"{rid}:{step_name}")
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="step_pro_search_start", stable_key=sid)
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="pro_search", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_step(
                    step_id=sid,
                    props={"run_id": rid, "name": step_name, "status": "running", "ts": ts, "order": 1},
                )
                g.link_run_step(run_id=rid, step_id=sid, order=1)
            return MappingResult(handled=True, component_id="pro_search", mutation_kinds=["step_pro_search_start"])

        if etype == "rag.search.result":
            step_name = "pro_search"
            sid = _sha256(f"{rid}:{step_name}")
            selected = payload.get("selected") if isinstance(payload, dict) else None
            selected_list = selected if isinstance(selected, list) else []
            counts = {"selected_count": int(len(selected_list))}
            # artifact id from selected evidence (hash only)
            art_hash = _sha256(json.dumps(selected_list, sort_keys=True, ensure_ascii=True)[:8000])
            aid = art_hash
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="step_pro_search_result", stable_key=f"{sid}:{aid}")
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="pro_search", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_step(
                    step_id=sid,
                    props={"run_id": rid, "name": step_name, "status": "success", "ts": ts, "order": 1},
                )
                g.link_run_step(run_id=rid, step_id=sid, order=1)
                if counts["selected_count"] > 0:
                    g.upsert_artifact(
                        artifact_id=aid,
                        props={
                            "kind": "evidence_pack",
                            "ts": ts,
                            "hash_sha256": art_hash,
                            "counts_json": json.dumps(counts, ensure_ascii=True),
                        },
                    )
                    g.link_step_artifact(step_id=sid, artifact_id=aid)
                    # Minimal provenance: source ids in selected list (if present)
                    for item in selected_list[:20]:
                        if not isinstance(item, dict):
                            continue
                        src = item.get("source")
                        if not src:
                            continue
                        g.upsert_source(source_id=str(src), props={"kind": "domain", "last_seen_ts": ts})
                        g.link_artifact_source(artifact_id=aid, source_id=str(src))
            return MappingResult(handled=True, component_id="pro_search", mutation_kinds=["step_pro_search_result"])

        if etype == "rag.context.compiled":
            step_name = "rag_build"
            sid = _sha256(f"{rid}:{step_name}")
            citations = payload.get("citations") if isinstance(payload, dict) else []
            chunks_count = int(payload.get("chunks_count") or 0) if isinstance(payload, dict) else 0
            counts = {"chunks_count": chunks_count, "citations_count": int(len(citations) if isinstance(citations, list) else 0)}
            aid = _sha256(json.dumps(counts, sort_keys=True, ensure_ascii=True))
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="rag_context_compiled", stable_key=f"{sid}:{aid}")
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="rag_context_builder", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_step(
                    step_id=sid,
                    props={"run_id": rid, "name": step_name, "status": "success", "ts": ts, "order": 2},
                )
                g.link_run_step(run_id=rid, step_id=sid, order=2)
                g.upsert_artifact(
                    artifact_id=aid,
                    props={
                        "kind": "context_pack",
                        "ts": ts,
                        "hash_sha256": aid,
                        "counts_json": json.dumps(counts, ensure_ascii=True),
                    },
                )
                g.link_step_artifact(step_id=sid, artifact_id=aid)
                g.upsert_run(run_id=rid, props={"status": "ok"})
            return MappingResult(handled=True, component_id="rag_context_builder", mutation_kinds=["rag_context_compiled"])

        if etype.startswith("scraping."):
            step_name = "scrape"
            sid = _sha256(f"{rid}:{step_name}")
            url = str(payload.get("url") or "")
            host = ""
            try:
                host = (urlparse(url).hostname or "").strip()
            except Exception:
                host = ""
            source_id = host or "unknown"
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="scrape_event", stable_key=f"{sid}:{etype}:{source_id}")
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="advanced_scraping", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_step(step_id=sid, props={"run_id": rid, "name": step_name, "status": "running" if etype == "scraping.page" else "success", "ts": ts, "order": 1})
                g.link_run_step(run_id=rid, step_id=sid, order=1)
                if source_id:
                    g.upsert_source(source_id=source_id, props={"kind": "host", "last_seen_ts": ts})
            return MappingResult(handled=True, component_id="advanced_scraping", mutation_kinds=["scrape_event"])

        if etype == "agent.decision_trace_summary":
            # Artifact: decision_summary (metadata only).
            aid = _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True)[:8000])
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="decision_summary", stable_key=aid)
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_artifact(
                    artifact_id=aid,
                    props={
                        "kind": "decision_summary",
                        "ts": ts,
                        "hash_sha256": aid,
                        "counts_json": json.dumps({"fields": len(payload or {})}, ensure_ascii=True),
                    },
                )
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["decision_summary"])

        if etype == "agent.reasoning.summary":
            # Step: adaptive_reasoning. Artifact: decision_summary with safe metadata.
            step_name = "adaptive_reasoning"
            sid = _sha256(f"{rid}:{step_name}")
            ar = payload.get("adaptive_reasoning") if isinstance(payload, dict) else {}
            if not isinstance(ar, dict):
                ar = {}
            safe_meta = {
                "goal_sha256": str(ar.get("goal_sha256") or ""),
                "goal_len": int(ar.get("goal_len") or 0),
                "tools_used": list(ar.get("tools_used") or []),
                "constraints_hit": list(ar.get("constraints_hit") or []),
                "retrieval_count": len(ar.get("retrieval", {}).get("chunk_ids") or []) if isinstance(ar.get("retrieval"), dict) else 0,
            }
            aid = _sha256(json.dumps(safe_meta, sort_keys=True, ensure_ascii=True))
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="adaptive_reasoning", stable_key=f"{sid}:{aid}")
            if _try_acquire_mutation(mid):
                g.upsert_step(
                    step_id=sid,
                    props={"run_id": rid, "name": step_name, "status": "success", "ts": ts, "order": 3},
                )
                g.link_run_step(run_id=rid, step_id=sid, order=3)
                g.upsert_artifact(
                    artifact_id=aid,
                    props={
                        "kind": "decision_summary",
                        "ts": ts,
                        "hash_sha256": aid,
                        "counts_json": json.dumps(safe_meta, ensure_ascii=True),
                    },
                )
                g.link_step_artifact(step_id=sid, artifact_id=aid)
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["adaptive_reasoning"])

        if etype == "indexing.upsert":
            step_name = "index_upsert"
            sid = _sha256(f"{rid}:{step_name}")
            idx_hash = str(payload.get("hash_sha256") or "") if isinstance(payload, dict) else ""
            idx_kind = str(payload.get("kind") or "") if isinstance(payload, dict) else ""
            aid = idx_hash or _sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True)[:4000])
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="index_upsert", stable_key=f"{sid}:{aid}")
            if _try_acquire_mutation(mid):
                g.upsert_component(component_id="vectorstore_qdrant", props={"freshness_ts": ts, "status": "ok"})
                g.upsert_step(
                    step_id=sid,
                    props={"run_id": rid, "name": step_name, "status": "success", "ts": ts, "order": 4},
                )
                g.link_run_step(run_id=rid, step_id=sid, order=4)
                g.upsert_artifact(
                    artifact_id=aid,
                    props={"kind": "chunk", "ts": ts, "hash_sha256": idx_hash, "index_kind": idx_kind},
                )
                g.link_step_artifact(step_id=sid, artifact_id=aid)
            return MappingResult(handled=True, component_id="vectorstore_qdrant", mutation_kinds=["index_upsert"])

        if etype == "error":
            mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="run_error", stable_key=rid)
            if _try_acquire_mutation(mid):
                g.upsert_run(run_id=rid, props={"status": "degraded", "last_err_ts": ts})
                g.upsert_component(component_id="ws_event_bus", props={"freshness_ts": ts, "status": "degraded", "last_err_ts": ts})
            return MappingResult(handled=True, component_id="ws_event_bus", mutation_kinds=["run_error"])

        # ─── Control Room event handlers ───

        if etype == "control_room.task.created":
            task_id = str(payload.get("task_id") or "")
            if not task_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_task_created",
                stable_key=task_id,
            )
            if _try_acquire_mutation(mid):
                task_type = str(payload.get("type") or payload.get("task_type") or "")
                task_props = {
                    "status": "queued",
                    "type": task_type,
                    "priority": str(payload.get("priority") or "normal"),
                    "requester": str(payload.get("requester") or ""),
                    "conversation_id": conv,
                    "trace_id": str(trace_id or ""),
                    "payload_redacted_hash": str(
                        payload.get("payload_redacted_hash")
                        or payload.get("payload_hash")
                        or ""
                    ),
                    "reason_safe": str(payload.get("reason_safe") or ""),
                    "created_ts": ts,
                    "specialty": str(payload.get("specialty") or ""),
                    "no_overlap_contract_hash": str(payload.get("no_overlap_contract_hash") or ""),
                    "requested_paths": payload.get("requested_paths") if isinstance(payload.get("requested_paths"), list) else [],
                }
                g.upsert_task(task_id=task_id, props=task_props)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_task_created"])

        if etype == "control_room.task.updated":
            task_id = str(payload.get("task_id") or "")
            if not task_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_task_updated",
                stable_key=task_id,
            )
            if _try_acquire_mutation(mid):
                patch_props: dict[str, Any] = {}
                for field in ("status", "retries", "started_ts", "ended_ts"):
                    val = payload.get(field)
                    if val is not None:
                        patch_props[field] = val if isinstance(val, int) else str(val)
                patch_props["updated_ts"] = ts
                g.upsert_task(task_id=task_id, props=patch_props)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_task_updated"])

        if etype == "control_room.run.spawned":
            cr_task_id = str(payload.get("task_id") or "")
            cr_run_id = str(payload.get("run_id") or "")
            if not cr_task_id or not cr_run_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_run_spawned",
                stable_key=f"{cr_task_id}:{cr_run_id}",
            )
            if _try_acquire_mutation(mid):
                g.upsert_run(run_id=cr_run_id, props={"kind": "control_room", "ts": ts, "status": "running"})
                g.link_task_run(task_id=cr_task_id, run_id=cr_run_id)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_run_spawned"])

        if etype == "control_room.approval.requested":
            approval_id = str(payload.get("approval_id") or "")
            cr_task_id = str(payload.get("task_id") or "")
            if not approval_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_approval_requested",
                stable_key=approval_id,
            )
            if _try_acquire_mutation(mid):
                approval_props = {
                    "status": "pending",
                    "policy_id": str(payload.get("policy_id") or ""),
                    "scope": str(payload.get("scope") or ""),
                    "requested_ts": ts,
                }
                g.upsert_approval(approval_id=approval_id, props=approval_props)
                if cr_task_id:
                    g.link_task_approval(task_id=cr_task_id, approval_id=approval_id)
                governs_run_id = str(payload.get("run_id") or "")
                governs_step_id = str(payload.get("step_id") or "")
                if governs_run_id:
                    g.link_approval_run(approval_id=approval_id, run_id=governs_run_id)
                if governs_step_id:
                    g.link_approval_step(approval_id=approval_id, step_id=governs_step_id)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_approval_requested"])

        if etype == "control_room.approval.resolved":
            approval_id = str(payload.get("approval_id") or "")
            if not approval_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_approval_resolved",
                stable_key=approval_id,
            )
            if _try_acquire_mutation(mid):
                resolve_props = {
                    "status": str(payload.get("status") or "resolved"),
                    "resolved_by": str(payload.get("resolved_by") or ""),
                    "resolved_ts": str(payload.get("resolved_ts") or ts),
                    "reason_safe": str(payload.get("reason_safe") or ""),
                }
                g.upsert_approval(approval_id=approval_id, props=resolve_props)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_approval_resolved"])

        if etype == "control_room.action.updated":
            action_id = str(payload.get("action_id") or "")
            if not action_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="cr_action_updated",
                stable_key=action_id,
            )
            if _try_acquire_mutation(mid):
                action_props = {
                    "name": str(payload.get("name") or ""),
                    "tool": str(payload.get("tool") or ""),
                    "status": str(payload.get("status") or ""),
                    "args_redacted_hash": str(payload.get("args_redacted_hash") or ""),
                    "result_redacted_hash": str(payload.get("result_redacted_hash") or ""),
                    "updated_ts": ts,
                }
                g.upsert_action(action_id=action_id, props=action_props)
                cr_step_id = str(payload.get("step_id") or "")
                if cr_step_id:
                    order = int(payload.get("order") or 0)
                    g.link_step_action(step_id=cr_step_id, action_id=action_id, order=order)
                g.upsert_component(component_id="control_room", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="control_room", mutation_kinds=["cr_action_updated"])

        # --- Compiler metadata (WS21-G) ---
        if etype in {"compiler.result", "compiler.fallback_result"}:
            corr_id = str(event.get("correlation_id") or "").strip()
            if not corr_id:
                return MappingResult(handled=False)

            pick = str(payload.get("pick") or "")
            confidence = float(payload.get("confidence") or 0.0)
            candidates_top3 = payload.get("candidates_top3") if isinstance(payload.get("candidates_top3"), list) else []
            compiler_id = str(payload.get("compiler") or "")
            model = str(payload.get("model") or "")
            degraded = bool(payload.get("degraded") or False)

            input_sha = str(payload.get("input_text_sha256") or "")
            input_len = int(payload.get("input_text_len") or 0)
            prompt_sha = str(payload.get("prompt_hash_sha256") or "")
            prompt_len = int(payload.get("prompt_len") or 0)
            retrieval_refs_hash = str(payload.get("retrieval_refs_hash") or "")

            det_id = _sha256(f"{corr_id}:intent")
            comp_id = _sha256(f"{corr_id}:compile")
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="compiler_metadata",
                stable_key=f"{rid}:{corr_id}:{prompt_sha}",
            )
            if _try_acquire_mutation(mid):
                try:
                    candidates_json = json.dumps(candidates_top3[:3], ensure_ascii=True, sort_keys=True)[:4000]
                except Exception:
                    candidates_json = "[]"

                g.upsert_intent_detection(
                    detection_id=det_id,
                    props={
                        "correlation_id": corr_id,
                        "pick": pick,
                        "confidence": float(confidence),
                        "candidates_top3_json": candidates_json,
                        "input_text_sha256": input_sha,
                        "input_text_len": int(input_len),
                        "ts": ts,
                        "compiler": compiler_id or "openai_chat",
                    },
                )
                g.link_run_intent_detection(run_id=rid, detection_id=det_id)

                g.upsert_prompt_compile(
                    compile_id=comp_id,
                    props={
                        "correlation_id": corr_id,
                        "makina_prompt_sha256": prompt_sha,
                        "makina_prompt_len": int(prompt_len),
                        "model": model or None,
                        "template_id": str(payload.get("template_id") or "") or None,
                        "retrieval_refs_hash": retrieval_refs_hash,
                        "ts": ts,
                    },
                )
                g.link_run_prompt_compile(run_id=rid, compile_id=comp_id)

                g.upsert_component(
                    component_id="compiler",
                    props={"freshness_ts": ts, "status": "degraded" if degraded else "ok"},
                )
            return MappingResult(handled=True, component_id="compiler", mutation_kinds=["compiler_metadata"])

        # --- VoiceSession (WS12-G) ---
        if etype == "voice.session.started":
            voice_session_id = str(payload.get("voice_session_id") or "")
            if not voice_session_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="voice_session_started",
                stable_key=voice_session_id,
            )
            if _try_acquire_mutation(mid):
                g.upsert_voice_session(
                    session_id=voice_session_id,
                    props={
                        "conversation_id": conv,
                        "status": str(payload.get("status") or "active"),
                        "ts": ts,
                        "last_event_ts": ts,
                        "error_count": int(payload.get("error_count") or 0),
                    },
                )
                g.upsert_component(component_id="voice", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="voice", mutation_kinds=["voice_session_started"])

        if etype.startswith("voice."):
            voice_session_id = str(payload.get("voice_session_id") or "")
            if not voice_session_id:
                return MappingResult(handled=False)
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="voice_event",
                stable_key=f"{voice_session_id}:{etype}",
            )
            if _try_acquire_mutation(mid):
                # Touch last_event_ts always; increment error_count only for voice.error.
                if etype == "voice.error":
                    g.increment_voice_session_error(session_id=voice_session_id, ts=ts)
                    g.upsert_voice_session(session_id=voice_session_id, props={"status": "error"})
                else:
                    g.upsert_voice_session(session_id=voice_session_id, props={"last_event_ts": ts})
                g.upsert_component(component_id="voice", props={"freshness_ts": ts, "status": "ok"})
            return MappingResult(handled=True, component_id="voice", mutation_kinds=["voice_event"])

        # --- WS23-G Neuroplasticity ---
        if etype == "neuro.wake.start":
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="neuro_wake_start",
                stable_key=f"{rid}:wake",
            )
            if _try_acquire_mutation(mid):
                # Ensure Identity node exists (bootstrap)
                identity_id = str(payload.get("identity_id") or "identity:denis")
                g.run_write(
                    "MERGE (i:Identity {id: $id}) SET i.last_wake_ts = $ts",
                    {"id": identity_id, "ts": ts},
                )
                g.upsert_component(
                    component_id="neuro_layers",
                    props={"freshness_ts": ts, "status": "ok"},
                )
            return MappingResult(handled=True, component_id="neuro_layers", mutation_kinds=["neuro_wake_start"])

        if etype == "neuro.layer.snapshot":
            layer_index = int(payload.get("layer_index") or 0)
            layer_key = str(payload.get("layer_key") or "")
            layer_id = f"neuro:layer:{layer_index}"
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="neuro_layer_snapshot",
                stable_key=layer_id,
            )
            if _try_acquire_mutation(mid):
                g.upsert_neuro_layer(
                    layer_id=layer_id,
                    props={
                        "layer_index": layer_index,
                        "layer_key": layer_key,
                        "title": str(payload.get("title") or ""),
                        "freshness_score": float(payload.get("freshness_score") or 0.5),
                        "status": str(payload.get("status") or "ok"),
                        "signals_count": int(payload.get("signals_count") or 0),
                        "last_update_ts": str(payload.get("last_update_ts") or ts),
                    },
                )
            return MappingResult(handled=True, component_id="neuro_layers", mutation_kinds=["neuro_layer_snapshot"])

        if etype == "neuro.consciousness.snapshot":
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="neuro_consciousness_snapshot",
                stable_key="denis:consciousness",
            )
            if _try_acquire_mutation(mid):
                cs_props = {}
                for k in ("mode", "fatigue_level", "risk_level", "confidence_level",
                           "guardrails_mode", "memory_mode", "voice_mode", "ops_mode",
                           "last_wake_ts", "last_turn_ts"):
                    v = payload.get(k)
                    if v is not None:
                        cs_props[k] = float(v) if isinstance(v, (int, float)) and k.endswith("_level") else str(v)
                cs_props["updated_ts"] = ts
                g.upsert_consciousness_state(state_id="denis:consciousness", props=cs_props)
                # Link Identity -> ConsciousnessState
                g.link_identity_consciousness(
                    identity_id="identity:denis", state_id="denis:consciousness",
                )
            return MappingResult(handled=True, component_id="neuro_layers", mutation_kinds=["neuro_consciousness_snapshot"])

        if etype == "neuro.turn.update":
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="neuro_turn_update",
                stable_key=f"{rid}:turn",
            )
            if _try_acquire_mutation(mid):
                layers_summary = payload.get("layers_summary")
                if isinstance(layers_summary, list):
                    for ls in layers_summary[:12]:
                        if not isinstance(ls, dict):
                            continue
                        li = int(ls.get("layer_index") or 0)
                        if li < 1 or li > 12:
                            continue
                        lid = f"neuro:layer:{li}"
                        g.upsert_neuro_layer(
                            layer_id=lid,
                            props={
                                "freshness_score": float(ls.get("freshness_score") or 0.5),
                                "status": str(ls.get("status") or "ok"),
                                "signals_count": int(ls.get("signals_count") or 0),
                                "last_update_ts": ts,
                            },
                        )
                g.upsert_component(
                    component_id="neuro_layers",
                    props={"freshness_ts": ts, "status": "ok"},
                )
            return MappingResult(handled=True, component_id="neuro_layers", mutation_kinds=["neuro_turn_update"])

        if etype == "neuro.consciousness.update":
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="neuro_consciousness_update",
                stable_key=f"denis:consciousness:{rid}",
            )
            if _try_acquire_mutation(mid):
                cs_props = {}
                for k in ("mode", "fatigue_level", "risk_level", "confidence_level",
                           "guardrails_mode", "memory_mode", "voice_mode", "ops_mode",
                           "last_turn_ts"):
                    v = payload.get(k)
                    if v is not None:
                        cs_props[k] = float(v) if isinstance(v, (int, float)) and k.endswith("_level") else str(v)
                cs_props["updated_ts"] = ts
                g.upsert_consciousness_state(state_id="denis:consciousness", props=cs_props)
            return MappingResult(handled=True, component_id="neuro_layers", mutation_kinds=["neuro_consciousness_update"])

        if etype == "persona.state.update":
            mid = _stable_mutation_id(
                event_id=int(event.get("event_id") or 0),
                mutation_kind="persona_state_update",
                stable_key=f"persona:{rid}",
            )
            if _try_acquire_mutation(mid):
                g.upsert_component(
                    component_id="persona",
                    props={
                        "freshness_ts": ts,
                        "status": str(payload.get("mode") or "ok"),
                    },
                )
            return MappingResult(handled=True, component_id="persona", mutation_kinds=["persona_state_update"])

        # Supported but not explicitly materialized events: still touch ws_event_bus freshness
        # but report handled=False (no event-specific graph mutation).
        mid = _stable_mutation_id(event_id=int(event.get("event_id") or 0), mutation_kind="component_freshness", stable_key=etype)
        if _try_acquire_mutation(mid):
            g.upsert_component(component_id="ws_event_bus", props={"freshness_ts": ts, "status": "ok"})
        return MappingResult(handled=False, component_id="ws_event_bus", mutation_kinds=["component_freshness"])
    except Exception:
        _STATS.errors_window += 1
        return MappingResult(handled=False)
    finally:
        _STATS.last_mutation_ts = _utc_now_iso()


def maybe_materialize_event(event: dict[str, Any], *, graph: GraphClient | None = None) -> None:
    """Fail-open wrapper for use in HTTP handlers."""
    try:
        materialize_event(event, graph=graph)
    except Exception:
        # Never break /chat.
        return
