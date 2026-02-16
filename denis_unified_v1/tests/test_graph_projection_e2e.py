"""E2E verification of voice pipeline graph projection.

Non-interactive, idempotent, reutilizable.
Cleans up only what it creates (prefixed by test request_id).

Run:
    NEO4J_PASSWORD='Leon1234$' python3 -m denis_unified_v1.tests.test_graph_projection_e2e
"""

import os
import time
from datetime import datetime, timezone

from denis_unified_v1.delivery.graph_projection import get_voice_projection
from denis_unified_v1.connections import get_neo4j_driver


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    request_id = f"test_verify_{int(time.time())}"
    user_id = os.getenv("USER", "jotah")

    proj = get_voice_projection()

    # 0) Seed topology (idempotent)
    proj.seed_topology()
    print("0. Topology seeded (idempotent)")

    # 1) Project request start
    proj.project_voice_request(
        request_id=request_id,
        voice_enabled=True,
        user_id=user_id,
        started_at=now_iso(),
    )
    print("1. VoiceRequest projected")

    # 2) Project two TTS steps (segments)
    proj.project_tts_step(
        request_id=request_id,
        segment_id=f"{request_id}:s1",
        segment_idx=1,
        text="Hola. Esto es un test.",
        ttfc_ns=126_000_000,   # 126ms in ns
        bytes_sent=36864,
        cancelled=False,
    )

    proj.project_tts_step(
        request_id=request_id,
        segment_id=f"{request_id}:s2",
        segment_idx=2,
        text="Estoy funcionando correctamente.",
        ttfc_ns=95_000_000,    # 95ms in ns
        bytes_sent=40960,
        cancelled=False,
    )
    print("2. TTS steps projected (2 segments)")

    # 3) Project outcome
    voice_ttfc_ns = 126_000_000
    metrics = {
        "voice_ttfc_ns": voice_ttfc_ns,
        "voice_ttfc_ms": int(voice_ttfc_ns / 1_000_000),
        "bytes_streamed": 77824,
        "audio_duration_ms": 1760,
        "chunks_count": 12,
        "voice_cancelled": False,
        "cancel_latency_ms": 0,
        "tts_backend": "piper_stream",
    }
    proj.project_outcome(request_id=request_id, metrics=metrics)
    print("3. Outcome projected")

    # 4) Verify via Neo4j queries
    driver = get_neo4j_driver()
    with driver.session() as session:
        # VoiceRequest
        r = session.run(
            "MATCH (r:VoiceRequest {id:$rid}) "
            "RETURN r.id AS id, r.voice_enabled AS voice_enabled, "
            "r.user_id AS user_id, r.started_at AS started_at, r.completed_at AS completed_at",
            rid=request_id,
        ).single()
        assert r, "VoiceRequest not found"
        print(f"4. VoiceRequest OK: id={r['id']}, voice={r['voice_enabled']}, user={r['user_id']}")

        # Outcome
        o = session.run(
            "MATCH (r:VoiceRequest {id:$rid})-[:HAS_OUTCOME]->(o:VoiceOutcome) "
            "RETURN o.voice_ttfc_ns AS ttfc_ns, o.voice_ttfc_ms AS ttfc_ms, "
            "o.bytes_streamed AS bytes, o.tts_backend AS backend, o.cancelled AS cancelled",
            rid=request_id,
        ).single()
        assert o, "VoiceOutcome not found"
        print(f"5. Outcome OK: ttfc_ns={o['ttfc_ns']} ({o['ttfc_ms']}ms), bytes={o['bytes']}, backend={o['backend']}, cancelled={o['cancelled']}")

        # Steps executed on PiperTTS
        s = session.run(
            "MATCH (r:VoiceRequest {id:$rid})-[:HAS_STEP]->(s:ToolchainStep)-[:EXECUTED_ON]->(p:PipelineNode {name:'PiperTTS'}) "
            "RETURN count(s) AS steps, p.port AS port, p.node AS node",
            rid=request_id,
        ).single()
        assert s and s["steps"] >= 1, "No ToolchainStep linked to PiperTTS"
        print(f"6. Steps OK: steps={s['steps']} -> PiperTTS port={s['port']}, node={s['node']}")

        # Static pipeline exists
        topo = session.run(
            "MATCH (p:Service {name:'Persona'})-[:DELIVERS_VIA]->(d:PipelineNode {name:'DeliverySubgraph'}) "
            "MATCH (d)-[:RENDERS_WITH]->(pr:PipelineNode {name:'PipecatRenderer'}) "
            "MATCH (pr)-[:TTS_BY]->(t:PipelineNode {name:'PiperTTS'}) "
            "RETURN p.name AS p, d.name AS d, pr.name AS pr, t.name AS t, t.ip AS ip, t.port AS port",
        ).single()
        assert topo, "Static pipeline topology missing"
        print(f"7. Topology OK: {topo['p']} -> {topo['d']} -> {topo['pr']} -> {topo['t']} ({topo['ip']}:{topo['port']})")

        # 5) Cleanup (only this request + its outcome/steps)
        session.run("MATCH (r:VoiceRequest {id:$rid}) DETACH DELETE r", rid=request_id)
        session.run("MATCH (o:VoiceOutcome {id:$oid}) DETACH DELETE o", oid=f"vo_{request_id}")
        session.run(
            "MATCH (s:ToolchainStep) WHERE s.id STARTS WITH $prefix DETACH DELETE s",
            prefix=f"tts_{request_id}:",
        )
        print("8. Cleanup OK")

    print()
    print("=== FULL E2E GRAPH PROJECTION VERIFIED ===")


if __name__ == "__main__":
    main()
