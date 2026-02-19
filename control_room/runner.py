from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from denis_unified_v1.async_min.tasks import dispatch_snapshot_hass
from denis_unified_v1.async_min.artifacts import save_artifact, build_artifact_path


@dataclass(frozen=True)
class StepResult:
    step_id: str
    ok: bool
    output: dict[str, Any]


def _utc_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _idem(run_id: str, step_id: str) -> str:
    raw = f"{run_id}:{step_id}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


class ControlRoomRunner:
    """Runs a small set of steps and persists artifacts (fail-open)."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, Callable[[str], dict[str, Any]]]] = [
            ("snapshot_hass", lambda run_id: dispatch_snapshot_hass(run_id=run_id)),
        ]

    def execute(self, *, run_id: str | None = None) -> dict[str, Any]:
        rid = run_id or f"run_{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()
        results: list[StepResult] = []
        for step_name, fn in self.steps:
            step_id = step_name  # stable step id
            idem = _idem(rid, step_id)
            queued_at = _utc_now()
            started_at = _utc_now()

            step_artifact_path = build_artifact_path(
                run_id=rid, name=f"step_{step_id}", idempotency_key=idem
            )
            if step_artifact_path.exists():
                results.append(
                    StepResult(
                        step_id=step_id,
                        ok=True,
                        output={
                            "state": "SUCCESS",
                            "queued_at": queued_at,
                            "started_at": started_at,
                            "finished_at": _utc_now(),
                            "idempotency_key": idem,
                            "artifact_path": str(step_artifact_path),
                            "artifact_deduped": True,
                        },
                    )
                )
                continue
            try:
                out = fn(rid) or {}
                finished_at = _utc_now()
                ok = bool(out.get("ok", True))
                mode = str(out.get("mode") or "")
                state = "SUCCESS" if ok else "FAILED"
                if mode in {"sync", "sync_cached"} and (
                    (os.getenv("ASYNC_ENABLED") or "").strip().lower()
                    in {"1", "true", "yes"}
                ):
                    state = "STALE"

                step_payload = {
                    "state": state,
                    "queued_at": queued_at,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "idempotency_key": idem,
                    "output": dict(out),
                }
                step_path = save_artifact(
                    run_id=rid,
                    name=f"step_{step_id}",
                    payload=step_payload,
                    artifact_type="control_room_step",
                    idempotency_key=idem,
                )
                step_payload["artifact_path"] = str(step_path)
                results.append(StepResult(step_id=step_id, ok=ok, output=step_payload))
            except Exception as exc:
                finished_at = _utc_now()
                results.append(
                    StepResult(
                        step_id=step_id,
                        ok=False,
                        output={
                            "state": "FAILED",
                            "queued_at": queued_at,
                            "started_at": started_at,
                            "finished_at": finished_at,
                            "idempotency_key": idem,
                            "error": {"code": "degraded", "msg": type(exc).__name__},
                        },
                    )
                )

        report = {
            "run_id": rid,
            "ok": all(r.ok for r in results),
            "steps": [
                {"step_id": r.step_id, "ok": r.ok, "output": r.output} for r in results
            ],
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "started_at": _utc_now(),
            "finished_at": _utc_now(),
            "state": "SUCCESS" if all(r.ok for r in results) else "FAILED",
        }
        save_artifact(
            run_id=rid,
            name="control_room_run_report",
            payload=report,
            artifact_type="control_room_run_report",
            idempotency_key=_idem(rid, "control_room_run_report"),
        )
        return report
