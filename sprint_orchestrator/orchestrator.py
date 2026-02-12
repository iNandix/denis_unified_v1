"""High-level sprint orchestration service."""

from __future__ import annotations

from pathlib import Path

from .config import SprintOrchestratorConfig
from .event_bus import EventBus, publish_event
from .git_projects import RepoScanOptions, discover_git_projects, load_projects_status
from .models import SprintEvent, SprintSession, new_id, utc_now
from .planner import SprintPlanner
from .project_registry import ProjectRegistry
from .session_store import SessionStore


class SprintOrchestrator:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        self.store = SessionStore(config)
        self.bus = EventBus(self.store, config)
        self.planner = SprintPlanner(config)
        self.registry = ProjectRegistry(config)

    def discover_projects(self, scan_root: Path | None = None) -> list:
        root = (scan_root or self.config.projects_scan_root).resolve()
        repos = discover_git_projects(root, RepoScanOptions())
        statuses = load_projects_status(repos)
        self.registry.upsert_projects(statuses)
        return statuses

    def create_session(
        self,
        *,
        prompt: str,
        workers: int,
        projects: list,
        provider_pool: list[str] | None = None,
        proposal_id: str | None = None,
    ) -> SprintSession:
        session = SprintSession(
            session_id=new_id("sprint"),
            created_utc=utc_now(),
            prompt=prompt.strip(),
            workers_requested=workers,
            projects=projects,
            assignments=self.planner.build_assignments(
                prompt=prompt,
                workers=workers,
                projects=projects,
                provider_pool=provider_pool,
            ),
            status="active",
        )
        self.store.save_session(session)
        primary_project = session.assignments[0].project_path if session.assignments else str(self.config.projects_scan_root)
        self.registry.create_session(
            session_id=session.session_id,
            project_path=primary_project,
            prompt=prompt,
            workers=workers,
            proposal_id=proposal_id,
        )
        self.registry.bind_tasks_to_assignments(
            session_id=session.session_id,
            assignments=session.assignments,
        )
        publish_event(
            self.store,
            SprintEvent(
                session_id=session.session_id,
                worker_id="system",
                kind="session.start",
                message="Sprint session created",
                payload={"workers": workers, "projects": len(projects)},
            ),
            self.bus,
        )
        for assignment in session.assignments:
            publish_event(
                self.store,
                SprintEvent(
                    session_id=session.session_id,
                    worker_id=assignment.worker_id,
                    kind="assignment",
                    message=assignment.task,
                    payload=assignment.as_dict(),
                ),
                self.bus,
            )
        return session

    def emit(
        self,
        *,
        session_id: str,
        worker_id: str,
        kind: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        publish_event(
            self.store,
            SprintEvent(
                session_id=session_id,
                worker_id=worker_id,
                kind=kind,
                message=message,
                payload=payload or {},
            ),
            self.bus,
        )
