from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifacts_root() -> Path:
    # Repo-local artifacts dir (safe for tests/dev)
    root = Path(os.getenv("DENIS_ARTIFACTS_DIR") or Path.cwd() / "artifacts")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_artifact_path(*, run_id: str, name: str, idempotency_key: str | None = None) -> Path:
    safe_run = (run_id or "run").strip()[:80]
    safe_name = (name or "artifact").strip().replace("/", "_")[:80]
    out_dir = artifacts_root() / "control_room" / safe_run
    out_dir.mkdir(parents=True, exist_ok=True)
    if idempotency_key:
        suffix = (idempotency_key or "").strip()[:16]
        filename = f"{safe_name}__{suffix}.json"
    else:
        filename = f"{safe_name}.json"
    return out_dir / filename


def save_artifact(
    *,
    run_id: str,
    name: str,
    payload: dict[str, Any],
    artifact_type: str = "control_room_artifact",
    idempotency_key: str | None = None,
) -> Path:
    safe_run = (run_id or "run").strip()[:80]
    safe_name = (name or "artifact").strip().replace("/", "_")[:80]
    path = build_artifact_path(run_id=safe_run, name=safe_name, idempotency_key=idempotency_key)

    # Dedupe/idempotency: if the artifact already exists, do not duplicate.
    if path.exists():
        return path

    payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    payload_sha256 = _sha256_bytes(payload_json)
    body = {
        "schema_version": "artifact_v1_1",
        "run_id": safe_run,
        "name": safe_name,
        "artifact_type": (artifact_type or "control_room_artifact"),
        "idempotency_key": (idempotency_key or ""),
        "created_at": _utc_now(),
        "size_bytes": int(len(payload_json)),
        "sha256": payload_sha256,
        "payload": payload,
    }
    path.write_text(json.dumps(body, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    return path
