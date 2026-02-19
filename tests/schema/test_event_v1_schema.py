import json
from pathlib import Path

import jsonschema


def _load_schema() -> dict:
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "docs" / "schema" / "event_v1.json").read_text(encoding="utf-8"))


def test_event_v1_schema_validates_examples():
    schema = _load_schema()
    base = {
        "event_id": 1,
        "ts": "2026-02-17T00:00:00Z",
        "conversation_id": "conv_test",
        "emitter": "denis_persona",
        "correlation_id": "corr_test",
        "turn_id": "turn_test",
        "channel": "text",
        "stored": True,
        "trace_id": "trace_test",
        "severity": "info",
        "schema_version": "1.0",
        "ui_hint": {"render": "x", "icon": "y", "collapsible": True},
        "payload": {},
    }

    examples = []
    examples.append({**base, "type": "chat.message", "payload": {"role": "user", "content_sha256": "0" * 64, "content_len": 4}})
    examples.append({**base, "type": "plan.created", "payload": {"intent_id": "i1", "plan_id": "p1", "task_count": 4}})
    examples.append({**base, "type": "plan.task.created", "payload": {"task_id": "t1", "plan_id": "p1"}})
    examples.append({**base, "type": "compiler.start", "channel": "compiler", "payload": {"input_text_sha256": "0" * 64, "input_text_len": 4, "mode": "makina_only", "compiler": "openai_chat"}})
    examples.append({**base, "type": "compiler.plan", "channel": "compiler", "payload": {"plan_redacted": "x", "confidence": 0.2, "assumptions": [], "risks": []}})
    examples.append({**base, "type": "retrieval.start", "channel": "compiler", "payload": {"query_sha256": "0" * 64, "query_len": 4, "policy": {"graph": True, "vectorstore": True, "max_chunks": 12}}})
    examples.append({**base, "type": "retrieval.result", "channel": "compiler", "payload": {"graph_count": 1, "chunk_ids_count": 2, "refs_hash": "0" * 64, "warning": None}})
    examples.append({**base, "type": "compiler.result", "channel": "compiler", "payload": {"pick": "implement_feature", "confidence": 0.9, "candidates_top3": [{"name": "implement_feature", "score": 0.9}], "prompt_hash_sha256": "0" * 64, "prompt_len": 120, "model": "gpt-4o-mini", "trace_hash": "1" * 64, "degraded": False}})
    examples.append({**base, "type": "compiler.error", "channel": "compiler", "severity": "warning", "payload": {"code": "openai_unavailable", "msg": "x", "detail": {"fallback": "local_v2"}}})
    examples.append({**base, "type": "voice.session.started", "payload": {"voice_session_id": "0" * 64, "status": "active", "ts_ms": 123}})
    examples.append({**base, "type": "voice.asr.partial", "payload": {"voice_session_id": "0" * 64, "text_sha256": "0" * 64, "text_len": 4, "language": "es", "source": "browser"}})
    examples.append({**base, "type": "voice.asr.final", "payload": {"voice_session_id": "0" * 64, "text_sha256": "0" * 64, "text_len": 4, "language": "es", "source": "stt"}})
    examples.append({**base, "type": "voice.tts.requested", "payload": {"voice_session_id": "0" * 64, "text_sha256": "0" * 64, "text_len": 10, "language": "es"}})
    examples.append({**base, "type": "voice.tts.audio.ready", "payload": {"voice_session_id": "0" * 64, "handle": "h1", "url": "/v1/voice/audio/h1.wav", "bytes_len": 12, "provider": "deterministic"}})
    examples.append({**base, "type": "voice.tts.done", "payload": {"voice_session_id": "0" * 64, "handle": "h1", "provider": "deterministic"}})
    examples.append({**base, "type": "voice.error", "severity": "warning", "payload": {"voice_session_id": "0" * 64, "code": "tts_failed", "msg": "x", "detail": {"k": "v"}}})
    examples.append({**base, "type": "agent.decision_trace_summary", "payload": {"blocked": False, "x_denis_hop": 0}})
    examples.append({**base, "type": "agent.reasoning.summary", "payload": {"adaptive_reasoning": {"tools_used": [], "retrieval": []}}})
    examples.append({**base, "type": "tool.call", "payload": {"tool_name": "t", "args_sha256": "0" * 64, "args_len": 2}})
    examples.append({**base, "type": "tool.result", "payload": {"tool_name": "t", "ok": True, "result_sha256": "0" * 64, "result_len": 3}})
    examples.append({**base, "type": "graph.mutation", "payload": {"layer_id": "L1_SENSORY", "entity_id": "e1", "op": "MERGE"}})
    examples.append({**base, "type": "ops.metric", "payload": {"name": "chat.latency_ms", "value": 12.0, "unit": "ms", "labels": {"endpoint": "/v1/chat/completions"}}})
    examples.append({**base, "type": "rag.search.start", "payload": {"query_sha256": "0" * 64, "query_len": 4, "k": 8, "filters": None}})
    examples.append({**base, "type": "rag.search.result", "payload": {"selected": [{"chunk_id": "c1", "score": 0.9}], "warning": None}})
    examples.append({**base, "type": "rag.context.compiled", "payload": {"chunks_count": 1, "citations": [{"chunk_id": "c1", "hash_sha256": "0" * 64}]}})
    examples.append({**base, "type": "indexing.upsert", "payload": {"kind": "decision_summary", "hash_sha256": "0" * 64, "status": "upserted"}})
    examples.append({**base, "type": "run.step", "payload": {"step_id": "chat_completions", "state": "SUCCESS"}})
    examples.append({**base, "type": "error", "severity": "warning", "payload": {"code": "degraded", "msg": "x"}})

    # WS23-G Neuro events
    neuro_base = {**base, "channel": "neuro"}
    examples.append({**neuro_base, "type": "neuro.wake.start", "payload": {"ts": "2026-02-17T00:00:00Z", "identity_id": "identity:denis"}})
    examples.append({**neuro_base, "type": "neuro.layer.snapshot", "stored": False, "event_id": 0, "payload": {"layer_index": 1, "layer_key": "sensory_io", "title": "Sensory/IO", "freshness_score": 0.8, "status": "ok", "signals_count": 0, "last_update_ts": "2026-02-17T00:00:00Z"}})
    examples.append({**neuro_base, "type": "neuro.consciousness.snapshot", "payload": {"mode": "awake", "fatigue_level": 0.1, "risk_level": 0.0, "confidence_level": 0.8, "guardrails_mode": "normal", "memory_mode": "balanced", "voice_mode": "off", "ops_mode": "normal", "last_wake_ts": "2026-02-17T00:00:00Z", "last_turn_ts": "2026-02-17T00:00:00Z", "ts": "2026-02-17T00:00:00Z"}})
    examples.append({**neuro_base, "type": "neuro.turn.update", "payload": {"layers_summary": [{"layer_index": 1, "layer_key": "sensory_io", "freshness_score": 1.0, "status": "ok", "signals_count": 1}], "ts": "2026-02-17T00:00:00Z"}})
    examples.append({**neuro_base, "type": "neuro.consciousness.update", "payload": {"mode": "focused", "fatigue_level": 0.2, "ts": "2026-02-17T00:00:00Z"}})
    examples.append({**neuro_base, "type": "persona.state.update", "stored": False, "event_id": 0, "payload": {"mode": "awake", "ts": "2026-02-17T00:00:00Z"}})

    for ev in examples:
        jsonschema.validate(ev, schema)
