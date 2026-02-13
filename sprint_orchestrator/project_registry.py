"""Global project/proposal/session registry (SQLite + optional Atlas sync)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import urllib.error
import urllib.request

from .config import SprintOrchestratorConfig
from .models import GitProjectStatus, WorkerAssignment, new_id
from .providers import merged_env
from .git_projects import read_commit_tree


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TaskView:
    task_id: str
    phase: str
    task: str
    status: str
    provider: str
    updated_utc: str
    completed_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "task": self.task,
            "status": self.status,
            "provider": self.provider,
            "updated_utc": self.updated_utc,
            "completed_utc": self.completed_utc,
        }


class ProjectRegistry:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        env = merged_env(config)
        configured = (env.get("DENIS_SPRINT_REGISTRY_DB") or "").strip()
        self.db_path = Path(configured) if configured else (config.state_dir / "project_registry.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self.atlas_enabled = (env.get("DENIS_SPRINT_REGISTRY_ATLAS_ENABLED") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.atlas_url = (
            env.get("DENIS_SPRINT_REGISTRY_ATLAS_URL")
            or env.get("DENIS_MASTER_URL")
            or "http://127.0.0.1:8084"
        ).strip().rstrip("/")

    def status(self) -> dict[str, Any]:
        return {
            "db_path": str(self.db_path),
            "atlas_enabled": self.atlas_enabled,
            "atlas_url": self.atlas_url,
        }

    def upsert_projects(self, projects: list[GitProjectStatus]) -> None:
        now = _utc_now()
        with self._connect() as conn:
            for item in projects:
                conn.execute(
                    """
                    INSERT INTO projects(path, name, branch, dirty, head_sha, last_commit, first_seen_utc, last_seen_utc)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET
                      name=excluded.name,
                      branch=excluded.branch,
                      dirty=excluded.dirty,
                      head_sha=excluded.head_sha,
                      last_commit=excluded.last_commit,
                      last_seen_utc=excluded.last_seen_utc
                    """,
                    (
                        item.path,
                        item.name,
                        item.branch,
                        int(item.dirty),
                        item.head_sha,
                        item.last_commit,
                        now,
                        now,
                    ),
                )
            conn.commit()

    def create_proposal(
        self,
        *,
        project_path: str,
        source_file: str,
        normalized: dict[str, Any],
        merged: dict[str, Any],
    ) -> str:
        proposal_id = new_id("proposal")
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO proposals(proposal_id, project_path, source_file, normalized_json, merged_json, created_utc, updated_utc)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    proposal_id,
                    project_path,
                    source_file,
                    json.dumps(normalized, sort_keys=True),
                    json.dumps(merged, sort_keys=True),
                    now,
                    now,
                ),
            )
            for item in merged.get("todo_by_phase") or []:
                phase = str(item.get("phase") or "")
                for task in item.get("tasks") or []:
                    text = str(task).strip()
                    if not text:
                        continue
                    conn.execute(
                        """
                        INSERT INTO proposal_tasks(task_id, proposal_id, phase, task, status, provider, updated_utc)
                        VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            new_id("task"),
                            proposal_id,
                            phase,
                            text,
                            "pending",
                            "",
                            now,
                        ),
                    )
            conn.commit()
        return proposal_id

    def create_session(
        self,
        *,
        session_id: str,
        project_path: str,
        prompt: str,
        workers: int,
        proposal_id: str | None = None,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(session_id, project_path, proposal_id, prompt, workers, status, created_utc, updated_utc)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                  proposal_id=excluded.proposal_id,
                  status=excluded.status,
                  updated_utc=excluded.updated_utc
                """,
                (session_id, project_path, proposal_id or "", prompt, workers, "active", now, now),
            )
            conn.commit()

    def bind_tasks_to_assignments(
        self,
        *,
        session_id: str,
        assignments: list[WorkerAssignment],
    ) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT proposal_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                return
            proposal_id = str(row["proposal_id"] or "")
            if not proposal_id:
                return
            pending = conn.execute(
                """
                SELECT task_id FROM proposal_tasks
                WHERE proposal_id=? AND status='pending'
                ORDER BY rowid ASC
                """,
                (proposal_id,),
            ).fetchall()
            if not pending:
                return

            now = _utc_now()
            for idx, assignment in enumerate(assignments):
                if idx >= len(pending):
                    break
                task_id = str(pending[idx]["task_id"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO session_worker_tasks(session_id, worker_id, task_id, assigned_utc)
                    VALUES(?,?,?,?)
                    """,
                    (session_id, assignment.worker_id, task_id, now),
                )
                conn.execute(
                    """
                    UPDATE proposal_tasks
                    SET status='in_progress', updated_utc=?
                    WHERE task_id=?
                    """,
                    (now, task_id),
                )
            conn.commit()

    def mark_task_done_for_worker(
        self,
        *,
        session_id: str,
        worker_id: str,
        provider: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT task_id FROM session_worker_tasks
                WHERE session_id=? AND worker_id=?
                """,
                (session_id, worker_id),
            ).fetchone()
            if row is None:
                return
            task_id = str(row["task_id"])
            conn.execute(
                """
                UPDATE proposal_tasks
                SET status='done', provider=?, completed_utc=?, updated_utc=?
                WHERE task_id=?
                """,
                (provider, now, now, task_id),
            )
            conn.commit()

    def record_stub_validation(
        self,
        *,
        session_id: str,
        worker_id: str,
        provider: str,
        file_path: str,
        line_no: int,
        category: str,
        pattern: str,
        line: str,
        decision: str,
        note: str = "",
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stub_validations(
                    validation_id, session_id, worker_id, provider,
                    file_path, line_no, category, pattern, line,
                    decision, note, created_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("stub"),
                    session_id,
                    worker_id,
                    provider,
                    file_path,
                    line_no,
                    category,
                    pattern,
                    line,
                    decision,
                    note,
                    now,
                ),
            )
            conn.commit()

    def list_stub_validations(
        self,
        *,
        project_path: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(1000, int(limit)))
        query = """
            SELECT validation_id, session_id, worker_id, provider, file_path, line_no, category, pattern, line, decision, note, created_utc
            FROM stub_validations
        """
        params: list[Any] = []
        if project_path:
            query += " WHERE file_path LIKE ?"
            params.append(f"{project_path}%")
        query += " ORDER BY created_utc DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def record_contract_decision(
        self,
        *,
        session_id: str,
        worker_id: str,
        provider: str,
        file_path: str,
        change_type: str,
        decision: str,
        note: str = "",
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_decisions(
                    decision_id, session_id, worker_id, provider,
                    file_path, change_type, decision, note, created_utc
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    new_id("contract"),
                    session_id,
                    worker_id,
                    provider,
                    file_path,
                    change_type,
                    decision,
                    note,
                    now,
                ),
            )
            conn.commit()

    def latest_proposal_for_project(self, project_path: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT proposal_id FROM proposals
                WHERE project_path=?
                ORDER BY created_utc DESC
                LIMIT 1
                """,
                (project_path,),
            ).fetchone()
            return str(row["proposal_id"]) if row else ""

    def build_journal(
        self,
        *,
        project_path: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            proposal_id = ""
            if session_id:
                row = conn.execute("SELECT proposal_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                proposal_id = str(row["proposal_id"] or "") if row else ""
            if not proposal_id:
                proposal_id = self.latest_proposal_for_project(project_path)

            if not proposal_id:
                return {
                    "project_path": project_path,
                    "proposal_id": "",
                    "pending": [],
                    "in_progress": [],
                    "done": [],
                }

            rows = conn.execute(
                """
                SELECT task_id, phase, task, status, provider, updated_utc, completed_utc
                FROM proposal_tasks
                WHERE proposal_id=?
                ORDER BY phase ASC, rowid ASC
                """,
                (proposal_id,),
            ).fetchall()
            pending: list[dict[str, Any]] = []
            in_progress: list[dict[str, Any]] = []
            done: list[dict[str, Any]] = []
            for row in rows:
                item = TaskView(
                    task_id=str(row["task_id"]),
                    phase=str(row["phase"] or ""),
                    task=str(row["task"] or ""),
                    status=str(row["status"] or "pending"),
                    provider=str(row["provider"] or ""),
                    updated_utc=str(row["updated_utc"] or ""),
                    completed_utc=str(row["completed_utc"] or ""),
                ).as_dict()
                status = item["status"]
                if status == "done":
                    done.append(item)
                elif status == "in_progress":
                    in_progress.append(item)
                else:
                    pending.append(item)
            return {
                "project_path": project_path,
                "proposal_id": proposal_id,
                "pending": pending,
                "in_progress": in_progress,
                "done": done,
            }

    def get_commit_tree(self, project_path: str, *, max_commits: int = 30, all_branches: bool = True) -> list[str]:
        """Get commit tree lines for the project."""
        return read_commit_tree(Path(project_path), max_commits=max_commits, all_branches=all_branches)

    def sync_from_atlas(self) -> dict[str, Any]:
        if not self.atlas_enabled:
            return {"status": "disabled", "projects_synced": 0}
        url = f"{self.atlas_url}/v1/memory/atlas/projects"
        req = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            return {"status": "error", "error": str(exc), "projects_synced": 0}
        try:
            payload = json.loads(raw)
        except Exception as exc:
            return {"status": "error", "error": f"invalid_json:{exc}", "projects_synced": 0}

        items = payload if isinstance(payload, list) else payload.get("projects", [])
        now = _utc_now()
        synced = 0
        with self._connect() as conn:
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if not path:
                    continue
                conn.execute(
                    """
                    INSERT INTO projects(path, name, branch, dirty, head_sha, last_commit, first_seen_utc, last_seen_utc)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(path) DO UPDATE SET
                      name=excluded.name,
                      branch=excluded.branch,
                      last_seen_utc=excluded.last_seen_utc
                    """,
                    (
                        path,
                        str(item.get("name") or Path(path).name),
                        str(item.get("branch") or "unknown"),
                        int(bool(item.get("dirty", False))),
                        str(item.get("head_sha") or ""),
                        str(item.get("last_commit") or ""),
                        now,
                        now,
                    ),
                )
                synced += 1
            conn.commit()
        return {"status": "ok", "projects_synced": synced}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects(
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    dirty INTEGER NOT NULL DEFAULT 0,
                    head_sha TEXT NOT NULL DEFAULT '',
                    last_commit TEXT NOT NULL DEFAULT '',
                    first_seen_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proposals(
                    proposal_id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    normalized_json TEXT NOT NULL,
                    merged_json TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proposal_tasks(
                    task_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    completed_utc TEXT NOT NULL DEFAULT '',
                    updated_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions(
                    session_id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    proposal_id TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL,
                    workers INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_worker_tasks(
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    assigned_utc TEXT NOT NULL,
                    PRIMARY KEY(session_id, worker_id)
                );

                CREATE TABLE IF NOT EXISTS stub_validations(
                    validation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_no INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    line TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contract_decisions(
                    decision_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_utc TEXT NOT NULL
                );
                """
            )
            conn.commit()
