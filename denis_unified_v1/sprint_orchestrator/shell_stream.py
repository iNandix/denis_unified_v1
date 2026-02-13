"""Run shell commands and stream terminal output into session events."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .event_bus import EventBus, publish_event
from .models import SprintEvent
from .session_store import SessionStore


def run_command_stream(
    *,
    session_id: str,
    worker_id: str,
    store: SessionStore,
    command: list[str],
    cwd: Path,
    timeout_sec: int = 1800,
    bus: EventBus | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="terminal.start",
            message=f"run: {' '.join(command)}",
            payload={"cwd": str(cwd), "command": command},
        ),
        bus,
    )

    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines = 0
    timed_out = False
    deadline = time.time() + timeout_sec
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines += 1
            publish_event(
                store,
                SprintEvent(
                    session_id=session_id,
                    worker_id=worker_id,
                    kind="terminal.output",
                    message=line[:400],
                    payload={"line_no": lines},
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
        publish_event(
            store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind="terminal.error",
                message=f"exception: {exc}",
                payload={},
            ),
            bus,
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    status = "ok" if returncode == 0 and not timed_out else "error"
    result = {
        "status": status,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "lines": lines,
        "command": command,
    }

    publish_event(
        store,
        SprintEvent(
            session_id=session_id,
            worker_id=worker_id,
            kind="terminal.end",
            message=f"command finished status={status} rc={returncode}",
            payload=result,
        ),
        bus,
    )
    return result
