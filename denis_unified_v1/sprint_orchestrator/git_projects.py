"""Git project discovery and status extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Iterable

from .models import GitProjectStatus

_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "go",
}


@dataclass(frozen=True)
class RepoScanOptions:
    max_depth: int = 4
    max_repos: int = 20


def _run_git(repo_path: Path, args: list[str]) -> tuple[int, str]:
    cmd = ["git", "-C", str(repo_path), *args]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return proc.returncode, (proc.stderr or proc.stdout).strip()
    return 0, (proc.stdout or "").strip()


def _repo_depth(root: Path, path: Path) -> int:
    if path == root:
        return 0
    return len(path.relative_to(root).parts)


def discover_git_projects(root: Path, options: RepoScanOptions | None = None) -> list[Path]:
    opts = options or RepoScanOptions()
    root = root.resolve()
    repos: list[Path] = []

    for current, dirs, _ in os.walk(root):
        current_path = Path(current)
        depth = _repo_depth(root, current_path)
        if depth > opts.max_depth:
            dirs[:] = []
            continue

        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]

        if (current_path / ".git").exists():
            repos.append(current_path)
            dirs[:] = []
            if len(repos) >= opts.max_repos:
                break

    return sorted(set(repos))


def _parse_ahead_behind(repo_path: Path) -> tuple[int, int]:
    code, output = _run_git(repo_path, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
    if code != 0 or not output:
        return 0, 0
    parts = output.split()
    if len(parts) != 2:
        return 0, 0
    behind = int(parts[0])
    ahead = int(parts[1])
    return ahead, behind


def read_project_status(repo_path: Path) -> GitProjectStatus | None:
    code, branch = _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0:
        return None

    _, porcelain = _run_git(repo_path, ["status", "--porcelain"])
    dirty = bool(porcelain.strip())

    _, head_sha = _run_git(repo_path, ["rev-parse", "--short", "HEAD"])
    _, last_commit = _run_git(repo_path, ["log", "-1", "--pretty=%s"])

    ahead, behind = _parse_ahead_behind(repo_path)

    return GitProjectStatus(
        path=str(repo_path),
        name=repo_path.name,
        branch=branch or "unknown",
        dirty=dirty,
        ahead=ahead,
        behind=behind,
        head_sha=head_sha or "unknown",
        last_commit=last_commit or "(no commits)",
    )


def load_projects_status(repo_paths: Iterable[Path]) -> list[GitProjectStatus]:
    statuses: list[GitProjectStatus] = []
    for path in repo_paths:
        status = read_project_status(path)
        if status is not None:
            statuses.append(status)
    return statuses


def read_commit_tree(repo_path: Path, *, max_commits: int = 30, all_branches: bool = True) -> list[str]:
    safe_max = max(1, min(int(max_commits), 300))
    args = [
        "log",
        "--graph",
        "--decorate",
        "--oneline",
        f"--max-count={safe_max}",
    ]
    if all_branches:
        args.append("--all")
    code, output = _run_git(repo_path, args)
    if code != 0:
        return [f"(error reading commit tree: {output})"]
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    return lines or ["(no commits found)"]
