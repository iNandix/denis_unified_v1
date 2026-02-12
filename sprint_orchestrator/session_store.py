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

    def session_path(self, session_id: str) -> Path:
        return self.config.sessions_dir / f"{session_id}.json"

    def events_path(self, session_id: str) -> Path:
        return self.config.events_dir / f"{session_id}.jsonl"

    def save_session(self, session: SprintSession) -> Path:
        path = self.session_path(session.session_id)
        path.write_text(json.dumps(session.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_session(self, session_id: str) -> dict[str, Any]:
        path = self.session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in sorted(self.config.sessions_dir.glob("*.json")):
            try:
                entries.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return entries

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
