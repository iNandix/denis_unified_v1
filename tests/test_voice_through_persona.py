from __future__ import annotations


def _disable_neo4j_env(monkeypatch) -> None:
    # Avoid create_app attempting network connections during tests.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)


def test_voice_through_persona_stub_transcript_emits_voice_events_and_tts(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_VOICE_AUDIO_DIR", str(tmp_path / "voice_audio"))
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_ENFORCE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_BYPASS_MODE", "raise")

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    conv = "conv_voice_persona_1"
    r = client.post(
        "/persona/voice",
        json={
            "conversation_id": conv,
            "text": "hola",
            "language": "es",
            "tts_enabled": True,
        },
    )
    assert r.status_code == 200
    js = r.json()
    assert js["conversation_id"] == conv
    assert isinstance(js.get("voice_session_id"), str) and len(js["voice_session_id"]) == 64
    assert isinstance(js.get("assistant_text"), str) and js["assistant_text"].strip()
    assert js.get("tts") is not None
    assert isinstance(js["tts"].get("url"), str)

    # Audio fetch
    audio_url = js["tts"]["url"]
    ar = client.get(audio_url)
    assert ar.status_code == 200
    assert (ar.headers.get("content-type") or "").startswith("audio/wav")
    assert len(ar.content) > 44

    # Persisted events are all emitted by persona.
    evs = client.get(f"/v1/events?conversation_id={conv}&after=0").json()["events"]
    assert evs
    assert all(e.get("emitter") == "denis_persona" for e in evs)

    types = [e["type"] for e in evs]
    want = [
        "voice.session.started",
        "voice.asr.final",
        "chat.message",
        "chat.message",
        "voice.tts.requested",
        "voice.tts.audio.ready",
        "voice.tts.done",
    ]
    # Required subsequence in order (fail-open: extra events allowed).
    pos = 0
    for t in types:
        if pos < len(want) and t == want[pos]:
            pos += 1
    assert pos == len(want)


def test_voice_through_persona_pipecat_enabled_audio_base64_uses_bridge(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_VOICE_AUDIO_DIR", str(tmp_path / "voice_audio"))
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_ENFORCE", "1")
    monkeypatch.setenv("PERSONA_FRONTDOOR_BYPASS_MODE", "raise")
    monkeypatch.setenv("PIPECAT_ENABLED", "1")

    # Avoid real network calls; emulate Pipecat STT output.
    import voice.pipecat_bridge as pb

    async def _fake_pipecat_stt_transcribe(*, audio_base64: str, language: str, timeout_sec=None, base_url=None):
        _ = (audio_base64, language, timeout_sec, base_url)
        return {
            "text": "hola desde audio",
            "language": "es",
            "confidence": 1,
            "latency_ms": 1,
            "source": "whisper_fake",
        }

    monkeypatch.setattr(pb, "pipecat_stt_transcribe", _fake_pipecat_stt_transcribe)

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    conv = "conv_voice_persona_pipecat_1"
    r = client.post(
        "/persona/voice",
        json={
            "conversation_id": conv,
            "audio_base64": "ZmFrZV93YXY=",  # "fake_wav" (not decoded in this test)
            "language": "es",
            "tts_enabled": True,
        },
    )
    assert r.status_code == 200
    js = r.json()
    assert js["conversation_id"] == conv
    assert isinstance(js.get("voice_session_id"), str) and len(js["voice_session_id"]) == 64
    assert isinstance(js.get("assistant_text"), str) and js["assistant_text"].strip()

    evs = client.get(f"/v1/events?conversation_id={conv}&after=0").json()["events"]
    assert evs
    assert all(e.get("emitter") == "denis_persona" for e in evs)

    # Ensure ASR-final was produced from audio path (source from pipecat stub).
    asr = [e for e in evs if e.get("type") == "voice.asr.final"]
    assert asr and asr[0].get("payload", {}).get("source") == "whisper_fake"
