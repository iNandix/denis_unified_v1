from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from denis_unified_v1.async_min.artifacts import save_artifact, build_artifact_path
from denis_unified_v1.async_min.celery_app import get_celery_app

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_hass_payload() -> dict[str, Any]:
    # P0 stub: stable shape, no secrets.
    return {
        "hass_connected": False,
        "entities": [
            {"entity_id": "sensor.living_room_temp", "state": "22.5", "domain": "sensor"},
            {"entity_id": "binary_sensor.motion_living", "state": "off", "domain": "binary_sensor"},
        ],
        "count": 2,
        "timestamp": _utc_now(),
    }


def snapshot_hass_sync(*, run_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    payload = _snapshot_hass_payload()
    idempotency_key = f"{run_id}:snapshot_hass"
    path = save_artifact(
        run_id=run_id,
        name="snapshot_hass",
        payload=payload,
        artifact_type="snapshot_hass",
        idempotency_key=idempotency_key,
    )
    try:
        from api.telemetry_store import get_telemetry_store

        get_telemetry_store().record_materialize(ok=True)
    except Exception:
        pass
    return {
        "ok": True,
        "mode": "sync",
        "artifact_path": str(path),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "timestamp": _utc_now(),
    }


def dispatch_snapshot_hass(*, run_id: str) -> dict[str, Any]:
    """Dispatch snapshot_hass async if possible; else run sync (fail-open)."""
    app = get_celery_app()
    if app is None:
        return snapshot_hass_sync(run_id=run_id)

    try:
        if (os.getenv("ASYNC_FORCE_FAIL") or "").strip() == "1":
            raise RuntimeError("async_forced_fail")

        # If this run already produced the artifact, avoid re-queuing work.
        existing = build_artifact_path(run_id=run_id, name="snapshot_hass", idempotency_key=f"{run_id}:snapshot_hass")
        if existing.exists():
            out = snapshot_hass_sync(run_id=run_id)
            out["mode"] = "sync_cached"
            return out

        # Broker preflight: avoid hanging on delay() when Redis is down.
        try:
            import redis  # type: ignore
            from denis_unified_v1.async_min.config import get_async_config

            cfg = get_async_config()
            r = redis.Redis.from_url(
                cfg.broker_url,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                retry_on_timeout=False,
            )
            r.ping()
        except Exception:
            raise RuntimeError("broker_unreachable")

        # Lazy-register task only when Celery is enabled.
        task = app.tasks.get("denis_unified_v1.async_min.tasks.snapshot_hass_task")
        if task is None:
            # Ensure registration by importing module-level task definition below.
            task = snapshot_hass_task  # type: ignore[name-defined]
        async_result = task.delay(run_id=run_id)  # type: ignore[union-attr]
        return {
            "ok": True,
            "mode": "async",
            "task_id": str(async_result.id),
            "timestamp": _utc_now(),
        }
    except Exception as exc:
        # Broker down / worker down / misconfig: run sync and mark async stale upstream.
        try:
            logger.warning("snapshot_hass_async_failed: %s", type(exc).__name__)
        except Exception:
            pass
        out = snapshot_hass_sync(run_id=run_id)
        out["async_error"] = {"code": "async_unavailable", "msg": type(exc).__name__}
        return out


# Celery task registration (optional)
_app = get_celery_app()
if _app is not None:

    @_app.task(  # type: ignore[misc]
        name="denis_unified_v1.async_min.tasks.snapshot_hass_task",
        bind=True,
        max_retries=2,
        default_retry_delay=1,
    )
    def snapshot_hass_task(self, run_id: str) -> dict[str, Any]:
        # Never log secrets. Payload is a stub.
        try:
            from api.telemetry_store import get_telemetry_store

            get_telemetry_store().set_worker_seen(True)
        except Exception:
            pass
        try:
            return snapshot_hass_sync(run_id=run_id)
        except Exception as exc:  # pragma: no cover
            try:
                raise self.retry(exc=exc, countdown=1)
            except Exception:
                raise
