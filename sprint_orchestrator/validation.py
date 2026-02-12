"""Run project validation targets and stream outputs as sprint events."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import time
from pathlib import Path

from .event_bus import EventBus, publish_event
from .models import SprintEvent
from .session_store import SessionStore


@dataclass(frozen=True)
class ValidationTarget:
    name: str
    command: list[str]
    timeout_sec: int = 1800


TARGET_NAMES = (
    "preflight",
    "autopoiesis-smoke",
    "gate-pentest",
    "validate-r1",
    "review-pack",
    "checkpoint-r1",
)


def resolve_target(project_root: Path, name: str) -> ValidationTarget:
    if name not in TARGET_NAMES:
        raise ValueError(f"Unknown target: {name}. Allowed: {', '.join(TARGET_NAMES)}")
    return ValidationTarget(name=name, command=["make", "-C", str(project_root), name])


def run_validation_target(
    *,
    session_id: str,
    worker_id: str,
    store: SessionStore,
    target: ValidationTarget,
    bus: EventBus | None = None,
) -> dict[str, object]:
    start = time.perf_counter()
    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="validation.start",
            message=f"Running validation target: {target.name}",
            payload={"command": target.command},
        ),
        bus,
    )

    proc = subprocess.Popen(
        target.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    timed_out = False

    try:
        assert proc.stdout is not None
        deadline = time.time() + target.timeout_sec
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            publish_event(
                store,
                SprintEvent(
                    session_id=session_id,
                    worker_id=worker_id,
                    kind="validation.output",
                    message=line[:400],
                    payload={"target": target.name},
                ),
                bus,
            )
            if time.time() > deadline:
                timed_out = True
                proc.kill()
                break
        returncode = proc.wait(timeout=5)
    except Exception as exc:
        proc.kill()
        returncode = 1
        lines.append(f"exception: {exc}")
    duration_ms = int((time.perf_counter() - start) * 1000)

    status = "ok" if returncode == 0 and not timed_out else "error"
    result = {
        "target": target.name,
        "status": status,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "lines": len(lines),
    }

    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="validation.end",
            message=f"Validation {target.name} finished with status={status}",
            payload=result,
        ),
        bus,
    )
    return result
