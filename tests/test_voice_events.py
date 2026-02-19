from __future__ import annotations


def _disable_neo4j_env(monkeypatch) -> None:
    # Avoid create_app attempting network connections during tests.
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)


def test_voice_session_and_tts_events(tmp_path, monkeypatch):
    _disable_neo4j_env(monkeypatch)
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("DENIS_VOICE_AUDIO_DIR", str(tmp_path / "voice_audio"))
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DENIS_CONTRACT_TEST_MODE", "1")

    from api.event_bus import reset_event_bus_for_tests
    from api.fastapi_server import create_app
    from fastapi.testclient import TestClient

    reset_event_bus_for_tests()
    app = create_app()
    client = TestClient(app)

    conv = "conv_voice_1"

    # Start voice session
    r = client.post("/v1/voice/session/start", json={"conversation_id": conv})
    assert r.status_code == 200
    js = r.json()
    assert js["conversation_id"] == conv
    assert isinstance(js["voice_session_id"], str)
    assert len(js["voice_session_id"]) == 64

    voice_session_id = js["voice_session_id"]

    # Voice chat via text fallback (no STT)
    r2 = client.post(
        "/v1/voice/chat",
        json={
            "conversation_id": conv,
            "voice_session_id": voice_session_id,
            "text": "hola",
            "language": "es",
            "tts_enabled": True,
        },
    )
    assert r2.status_code == 200
    js2 = r2.json()
    assert js2["conversation_id"] == conv
    assert js2["voice_session_id"] == voice_session_id
    assert isinstance(js2.get("assistant_text"), str)
    assert js2.get("tts") is not None
    assert isinstance(js2["tts"].get("url"), str)

    # Audio fetch
    audio_url = js2["tts"]["url"]
    ar = client.get(audio_url)
    assert ar.status_code == 200
    assert (ar.headers.get("content-type") or "").startswith("audio/wav")
    assert len(ar.content) > 44  # WAV header + payload

    # Persisted events include voice.* and tts ready
    evs = client.get(f"/v1/events?conversation_id={conv}&after=0").json()["events"]
    types = [e["type"] for e in evs]
    assert "voice.session.started" in types
    assert "voice.asr.final" in types
    assert "voice.tts.requested" in types
    assert "voice.tts.audio.ready" in types
    assert "voice.tts.done" in types

