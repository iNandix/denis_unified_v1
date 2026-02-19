from __future__ import annotations

from datetime import datetime, timezone


def _iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def test_graph_layer_freshness_live_when_recent():
    from api.graph_freshness import get_graph_layer_freshness

    now_ms = 1_700_000_000_000
    stale_threshold_ms = 10_000

    def fetch(_ids: list[str]) -> dict[str, str | None]:
        return {"L1_SENSORY": _iso_from_ms(now_ms - 1_000)}

    block = get_graph_layer_freshness(
        layer_ids=["L1_SENSORY"],
        now_ms=now_ms,
        stale_threshold_ms=stale_threshold_ms,
        fetch_last_updates=fetch,
    )
    assert block["layers"][0]["status"] == "live"
    assert block["summary"]["live_count"] == 1
    assert block["summary"]["stale_count"] == 0
    assert block["summary"]["unknown_count"] == 0
    assert block["summary"]["integrity_degraded"] is False


def test_graph_layer_freshness_stale_when_old():
    from api.graph_freshness import get_graph_layer_freshness

    now_ms = 1_700_000_000_000
    stale_threshold_ms = 10_000

    def fetch(_ids: list[str]) -> dict[str, str | None]:
        return {"L1_SENSORY": _iso_from_ms(now_ms - 50_000)}

    block = get_graph_layer_freshness(
        layer_ids=["L1_SENSORY"],
        now_ms=now_ms,
        stale_threshold_ms=stale_threshold_ms,
        fetch_last_updates=fetch,
    )
    assert block["layers"][0]["status"] == "stale"
    assert block["summary"]["live_count"] == 0
    assert block["summary"]["stale_count"] == 1
    assert block["summary"]["unknown_count"] == 0
    assert block["summary"]["integrity_degraded"] is False


def test_graph_layer_freshness_unknown_when_graph_errors():
    from api.graph_freshness import get_graph_layer_freshness

    def fetch(_ids: list[str]) -> dict[str, str | None]:
        raise RuntimeError("boom")

    block = get_graph_layer_freshness(
        layer_ids=["L1_SENSORY", "L2_WORKING"],
        now_ms=1_700_000_000_000,
        stale_threshold_ms=10_000,
        fetch_last_updates=fetch,
    )
    assert [x["status"] for x in block["layers"]] == ["unknown", "unknown"]
    assert [x["last_update_ts"] for x in block["layers"]] == [None, None]
    assert block["summary"]["integrity_degraded"] is True
    assert block["summary"]["unknown_count"] == 2


def test_telemetry_contains_graph_block(monkeypatch):
    # Contract: /telemetry always includes graph.layers[] and graph.summary (fail-open).
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASS", raising=False)

    # Avoid any accidental Graph probing by forcing the internal fetch to fail fast.
    import api.graph_freshness as gf

    monkeypatch.setattr(
        gf,
        "_fetch_layer_last_updates_from_neo4j",
        lambda _ids: (_ for _ in ()).throw(RuntimeError("no_graph")),
    )

    from fastapi.testclient import TestClient
    from api.fastapi_server import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/telemetry")
    assert r.status_code == 200
    data = r.json()

    assert "graph" in data
    assert "layers" in data["graph"] and isinstance(data["graph"]["layers"], list)
    assert len(data["graph"]["layers"]) == 12
    assert "summary" in data["graph"] and isinstance(data["graph"]["summary"], dict)
    assert set(data["graph"]["summary"].keys()) >= {
        "live_count",
        "stale_count",
        "unknown_count",
        "integrity_degraded",
    }

