"""Persistence for sprint sessions and event streams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import SprintOrchestratorConfig
from .models import SprintEvent, SprintSession


class SessionStore:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        self.config.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.config.events_dir.mkdir(parents=True, exist_ok=True)
        # Cache for snapshots and event indices
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._event_indices: dict[str, list[str]] = {}

    def snapshot_path(self, session_id: str) -> Path:
        return self.config.sessions_dir / f"{session_id}_snapshot.json"

    def event_index_path(self, session_id: str) -> Path:
        return self.config.events_dir / f"{session_id}_index.json"

    def session_path(self, session_id: str) -> Path:
        return self.config.sessions_dir / f"{session_id}.json"

    def events_path(self, session_id: str) -> Path:
        return self.config.events_dir / f"{session_id}.jsonl"

    def save_session(self, session: SprintSession) -> Path:
        path = self.session_path(session.session_id)
        data = session.as_dict()
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        self._snapshots[session.session_id] = data
        self.save_snapshot(session.session_id)
        return path

    def save_snapshot(self, session_id: str) -> None:
        snapshot = self._snapshots.get(session_id)
        if snapshot:
            path = self.snapshot_path(session_id)
            path.write_text(
                json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
            )

    def load_snapshot(self, session_id: str) -> dict[str, Any] | None:
        if session_id in self._snapshots:
            return self._snapshots[session_id]
        path = self.snapshot_path(session_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._snapshots[session_id] = data
            return data
        return None

    def update_event_index(self, session_id: str, event_id: str) -> None:
        if session_id not in self._event_indices:
            self._event_indices[session_id] = []
        if event_id not in self._event_indices[session_id]:
            self._event_indices[session_id].append(event_id)
        self.save_event_index(session_id)

    def save_event_index(self, session_id: str) -> None:
        index = self._event_indices.get(session_id, [])
        path = self.event_index_path(session_id)
        path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def load_event_index(self, session_id: str) -> list[str]:
        if session_id in self._event_indices:
            return self._event_indices[session_id]
        path = self.event_index_path(session_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._event_indices[session_id] = data
            return data
        return []

    def append_event(self, event: SprintEvent) -> Path:
        path = self.events_path(event.session_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.as_dict(), sort_keys=True))
            fh.write("\n")
        return path

    def read_events(self, session_id: str) -> list[dict[str, Any]]:
        path = self.events_path(session_id)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows
