"""Detect placeholder/stub/simulation patterns in real git diff."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import subprocess
from typing import Any

from .config import SprintOrchestratorConfig
from .providers import merged_env


@dataclass(frozen=True)
class GuardViolation:
    file_path: str
    line_no: int
    category: str
    pattern: str
    line: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuardReport:
    status: str
    project_path: str
    violations: list[GuardViolation]
    scanned_files: int
    scanned_added_lines: int
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "project_path": self.project_path,
            "violations": [item.as_dict() for item in self.violations],
            "scanned_files": self.scanned_files,
            "scanned_added_lines": self.scanned_added_lines,
            "error": self.error,
        }


class ChangeGuard:
    """Fail-closed detector for non-production placeholders in code changes."""

    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        env = merged_env(config)
        self.enabled = _env_bool(env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_ENABLED"), True)
        self.fail_closed = _env_bool(env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_FAIL_CLOSED"), True)
        self.allow_marker = (env.get("DENIS_SPRINT_PLACEHOLDER_ALLOW_MARKER") or "denis:allow-placeholder").strip()
        self.max_violations = max(50, int(env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_MAX") or "300"))

        self.patterns: list[tuple[str, re.Pattern[str]]] = [
            ("placeholder", re.compile(r"(?i)\bplaceholder(s)?\b")),
            ("stub", re.compile(r"(?i)\bstub(s|bed)?\b")),
            ("mock", re.compile(r"(?i)\bmock(s|ed|ing)?\b")),
            ("simulation", re.compile(r"(?i)\bsimulat(e|ion|ed|ing)\b")),
            ("not_implemented", re.compile(r"\bNotImplementedError\b")),
            ("todo", re.compile(r"(?i)\b(TODO|FIXME|XXX)\b")),
            ("coming_soon", re.compile(r"(?i)coming soon|to be implemented|tbd")),
            ("pass_placeholder", re.compile(r"^\s*pass\s*(#.*)?$")),
        ]

    def inspect_repo_diff(self, project_path: Path) -> GuardReport:
        if not self.enabled:
            return GuardReport(
                status="disabled",
                project_path=str(project_path),
                violations=[],
                scanned_files=0,
                scanned_added_lines=0,
            )
        cmd = ["git", "-C", str(project_path), "diff", "--unified=0", "--no-color"]
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            status = "error"
            if self.fail_closed:
                status = "alert"
            return GuardReport(
                status=status,
                project_path=str(project_path),
                violations=[],
                scanned_files=0,
                scanned_added_lines=0,
                error=(proc.stderr or proc.stdout or "git_diff_failed").strip()[:400],
            )
        return self.inspect_diff_text(project_path=project_path, diff_text=proc.stdout or "")

    def inspect_diff_text(self, *, project_path: Path, diff_text: str) -> GuardReport:
        current_file = ""
        scan_current_file = True
        line_no = 0
        scanned_files: set[str] = set()
        scanned_added_lines = 0
        violations: list[GuardViolation] = []

        for raw in diff_text.splitlines():
            if raw.startswith("+++ b/"):
                current_file = raw[6:].strip()
                scan_current_file = _should_scan_file(current_file)
                scanned_files.add(current_file)
                continue
            if raw.startswith("@@"):
                start = _parse_new_hunk_start(raw)
                if start is not None:
                    line_no = start
                continue
            if raw.startswith("+") and not raw.startswith("+++"):
                if not scan_current_file:
                    line_no += 1
                    continue
                added = raw[1:]
                scanned_added_lines += 1
                if self.allow_marker and self.allow_marker in added:
                    line_no += 1
                    continue
                stripped = added.strip()
                for category, pattern in self.patterns:
                    if not pattern.search(added):
                        continue
                    if stripped.startswith("#") and category in {
                        "placeholder",
                        "stub",
                        "mock",
                        "simulation",
                        "coming_soon",
                    }:
                        continue
                    violations.append(
                        GuardViolation(
                            file_path=current_file or "(unknown)",
                            line_no=max(1, line_no),
                            category=category,
                            pattern=pattern.pattern,
                            line=added.strip()[:240],
                        )
                    )
                    if len(violations) >= self.max_violations:
                        break
                line_no += 1
                if len(violations) >= self.max_violations:
                    break
                continue
            if raw.startswith("-") and not raw.startswith("---"):
                continue
            if raw.startswith(" "):
                line_no += 1

        status = "clean" if not violations else "alert"
        return GuardReport(
            status=status,
            project_path=str(project_path),
            violations=violations,
            scanned_files=len(scanned_files),
            scanned_added_lines=scanned_added_lines,
        )


def _env_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_new_hunk_start(header: str) -> int | None:
    # Example: @@ -10,3 +45,8 @@
    match = re.search(r"\+(\d+)(?:,\d+)?", header)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _should_scan_file(path: str) -> bool:
    lower = path.lower()
    if not lower:
        return True
    skip_suffixes = (
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".lock",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
    )
    return not lower.endswith(skip_suffixes)
