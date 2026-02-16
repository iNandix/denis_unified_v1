"""Graph projection for voice pipeline events.

Projects voice pipeline execution to Neo4j.
Uses connections.py (not GraphWriter) to avoid transitive dependency issues.

Canonical time unit: nanoseconds (ttfc_ns). Derive ms via int(ns / 1_000_000).

Graph topology:
  (Persona)-[:DELIVERS_VIA]->(DeliverySubgraph)-[:RENDERS_WITH]->(PipecatRenderer)
  (PipecatRenderer)-[:TTS_BY]->(PiperTTS {node: nodo2, port: 8005})
  (PipecatRenderer)-[:OUTPUT_TO]->(HomeAssistant)
  (VoiceRequest)-[:USED_PIPELINE]->(DeliverySubgraph)
  (VoiceRequest)-[:HAS_OUTCOME]->(VoiceOutcome {ttfc_ns, bytes, cancelled})
  (VoiceRequest)-[:HAS_STEP]->(ToolchainStep)-[:EXECUTED_ON]->(PiperTTS)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _neo4j_write(query: str, params: Dict[str, Any]) -> bool:
    """Execute a Neo4j write query using connections.py. Fail-open."""
    try:
        from denis_unified_v1.connections import get_neo4j_driver
        driver = get_neo4j_driver()
        if not driver:
            return False
        with driver.session() as session:
            session.run(query, params)
        return True
    except Exception as e:
        logger.warning(f"Neo4j write failed (fail-open): {e}")
        return False


class VoiceGraphProjection:
    """Projects voice pipeline events to Neo4j."""

    def __init__(self):
        self._topology_seeded = False

    def seed_topology(self):
        """Seed static voice pipeline topology (idempotent, run once at startup)."""
        if self._topology_seeded:
            return

        ok = _neo4j_write("""
        MATCH (persona:Service {name: 'Persona'})
        SET persona:PipelineNode, persona.updated_at = datetime()

        MERGE (delivery:PipelineNode {name: 'DeliverySubgraph'})
        SET delivery.module = 'delivery.subgraph', delivery.node = 'nodo1',
            delivery.updated_at = datetime()

        MERGE (renderer:PipelineNode {name: 'PipecatRenderer'})
        SET renderer.module = 'delivery.pipecat_renderer', renderer.node = 'nodo1',
            renderer.updated_at = datetime()

        MERGE (piper:PipelineNode:VoiceService {name: 'PiperTTS'})
        SET piper.port = 8005, piper.node = 'nodo2', piper.ip = '10.10.10.2',
            piper.type = 'TTS', piper.encoding = 'pcm_s16le',
            piper.sample_rate = 22050, piper.status = 'active',
            piper.updated_at = datetime()

        MERGE (hass:PipelineNode {name: 'HomeAssistant'})
        SET hass.port = 8123, hass.node = 'nodo1', hass.type = 'output_device',
            hass.updated_at = datetime()

        MERGE (persona)-[:DELIVERS_VIA]->(delivery)
        MERGE (delivery)-[:RENDERS_WITH]->(renderer)
        MERGE (renderer)-[:TTS_BY]->(piper)
        MERGE (renderer)-[:OUTPUT_TO]->(hass)
        """, {})

        if ok:
            self._topology_seeded = True
            logger.info("Voice pipeline topology seeded in graph")

    def project_voice_request(
        self,
        request_id: str,
        voice_enabled: bool,
        user_id: str = "default",
        started_at: str = "",
    ):
        """Project a voice request start to the graph."""
        _neo4j_write("""
        MERGE (req:VoiceRequest {id: $request_id})
        SET req.voice_enabled = $voice_enabled,
            req.user_id = $user_id,
            req.started_at = CASE WHEN $started_at <> '' THEN datetime($started_at) ELSE datetime() END,
            req.updated_at = datetime()

        WITH req
        MATCH (pipeline:PipelineNode {name: 'DeliverySubgraph'})
        MERGE (req)-[:USED_PIPELINE]->(pipeline)
        """, {
            "request_id": request_id,
            "voice_enabled": voice_enabled,
            "user_id": user_id,
            "started_at": started_at,
        })

    # Keep backward compat alias
    project_request = project_voice_request

    def project_outcome(
        self,
        request_id: str,
        metrics: Dict[str, Any],
    ):
        """Project voice outcome to the graph.

        Canonical metric: voice_ttfc_ns (nanoseconds).
        Falls back to voice_ttfc_ms * 1_000_000 if ns not provided.
        """
        ttfc_ns = metrics.get("voice_ttfc_ns", 0)
        if not ttfc_ns:
            ttfc_ns = metrics.get("voice_ttfc_ms", 0) * 1_000_000

        _neo4j_write("""
        MERGE (req:VoiceRequest {id: $request_id})
        SET req.completed_at = datetime()

        MERGE (outcome:VoiceOutcome {id: $outcome_id})
        SET outcome.voice_ttfc_ns = $ttfc_ns,
            outcome.voice_ttfc_ms = $ttfc_ms,
            outcome.bytes_streamed = $bytes_streamed,
            outcome.audio_duration_ms = $audio_duration_ms,
            outcome.chunks_count = $chunks_count,
            outcome.cancelled = $cancelled,
            outcome.cancel_latency_ms = $cancel_latency_ms,
            outcome.tts_backend = $tts_backend,
            outcome.created_at = datetime()

        MERGE (req)-[:HAS_OUTCOME]->(outcome)
        """, {
            "request_id": request_id,
            "outcome_id": f"vo_{request_id}",
            "ttfc_ns": ttfc_ns,
            "ttfc_ms": int(ttfc_ns / 1_000_000),
            "bytes_streamed": metrics.get("bytes_streamed", 0),
            "audio_duration_ms": metrics.get("audio_duration_ms", 0),
            "chunks_count": metrics.get("chunks_count", 0),
            "cancelled": metrics.get("voice_cancelled", False),
            "cancel_latency_ms": metrics.get("cancel_latency_ms", 0),
            "tts_backend": metrics.get("tts_backend", "none"),
        })

    def project_tts_step(
        self,
        request_id: str,
        segment_id: str,
        text: str,
        segment_idx: int = 0,
        ttfc_ns: int = 0,
        bytes_sent: int = 0,
        cancelled: bool = False,
    ):
        """Project a TTS step (per-segment) to the graph.

        ttfc_ns: time-to-first-chunk in nanoseconds (canonical).
        """
        _neo4j_write("""
        MERGE (req:VoiceRequest {id: $request_id})

        MERGE (step:ToolchainStep {id: $step_id})
        SET step.type = 'tts',
            step.segment_id = $segment_id,
            step.segment_idx = $segment_idx,
            step.text_length = $text_length,
            step.ttfc_ns = $ttfc_ns,
            step.ttfc_ms = $ttfc_ms,
            step.bytes_sent = $bytes_sent,
            step.cancelled = $cancelled,
            step.created_at = datetime()

        MERGE (req)-[:HAS_STEP]->(step)

        WITH step
        MATCH (piper:PipelineNode {name: 'PiperTTS'})
        MERGE (step)-[:EXECUTED_ON]->(piper)
        """, {
            "request_id": request_id,
            "step_id": f"tts_{segment_id}",
            "segment_id": segment_id,
            "segment_idx": segment_idx,
            "text_length": len(text),
            "ttfc_ns": ttfc_ns,
            "ttfc_ms": int(ttfc_ns / 1_000_000),
            "bytes_sent": bytes_sent,
            "cancelled": cancelled,
        })


# Singleton
_projection: Optional[VoiceGraphProjection] = None


def get_voice_projection() -> VoiceGraphProjection:
    global _projection
    if _projection is None:
        _projection = VoiceGraphProjection()
    return _projection
