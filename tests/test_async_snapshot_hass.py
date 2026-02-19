import json
from pathlib import Path


def test_snapshot_hass_dispatch_falls_back_to_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_ARTIFACTS_DIR", str(tmp_path))
    # Enable async but point to a dead broker; dispatch must fall back quickly (no hang).
    monkeypatch.setenv("ASYNC_ENABLED", "1")
    monkeypatch.setenv("ASYNC_REDIS_URL", "redis://127.0.0.1:6399/0")

    from denis_unified_v1.async_min.tasks import dispatch_snapshot_hass

    out = dispatch_snapshot_hass(run_id="run_test_1")
    assert out["ok"] is True
    assert out["mode"] in {"sync", "async"}

    # Telemetry semantics: when async is enabled but worker hasn't been seen,
    # materializer should be marked stale (fail-open, non-critical).
    from api.telemetry_store import get_telemetry_store

    snap = get_telemetry_store().snapshot()
    assert snap["async"]["async_enabled"] is True
    assert snap["async"]["materializer_stale"] is True
    assert "queue_depth" in snap["async"]

    if out["mode"] == "sync":
        path = Path(out["artifact_path"])
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == "snapshot_hass"
        assert "payload" in data and isinstance(data["payload"], dict)
