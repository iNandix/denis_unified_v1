"""Configuration for sprint orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


_DEFAULT_PROVIDER_POOL = [
    "denis_canonical",
    "legacy_core",
    "denis_agent",
    "codex",
    "claude_code",
    "opencode",
    "groq",
    "ollama_cloud",
    "llama_node1",
    "llama_node2",
]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SprintOrchestratorConfig:
    enabled: bool
    state_dir: Path
    sessions_dir: Path
    events_dir: Path
    projects_scan_root: Path
    max_workers: int
    provider_pool: list[str]
    primary_provider: str
    pin_legacy_first: bool



def load_sprint_config(project_root: Path | None = None) -> SprintOrchestratorConfig:
    root = project_root or Path.cwd()
    state_dir = Path(os.getenv("DENIS_SPRINT_STATE_DIR", root / ".sprint_orchestrator"))
    providers_raw = os.getenv("DENIS_SPRINT_PROVIDER_POOL", ",".join(_DEFAULT_PROVIDER_POOL))
    provider_pool = [p.strip() for p in providers_raw.split(",") if p.strip()]
    if not provider_pool:
        provider_pool = list(_DEFAULT_PROVIDER_POOL)

    scan_root = Path(os.getenv("DENIS_SPRINT_SCAN_ROOT", str(root))).resolve()
    max_workers = int(os.getenv("DENIS_SPRINT_MAX_WORKERS", "4"))
    if max_workers < 1:
        max_workers = 1
    if max_workers > 8:
        max_workers = 8

    return SprintOrchestratorConfig(
        enabled=_env_bool("DENIS_USE_SPRINT_ORCHESTRATOR", False),
        state_dir=state_dir,
        sessions_dir=state_dir / "sessions",
        events_dir=state_dir / "events",
        projects_scan_root=scan_root,
        max_workers=max_workers,
        provider_pool=provider_pool,
        primary_provider=(os.getenv("DENIS_SPRINT_PRIMARY_PROVIDER") or "denis_canonical").strip(),
        pin_legacy_first=_env_bool("DENIS_SPRINT_PIN_LEGACY_FIRST", True),
    )
