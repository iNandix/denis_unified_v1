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
    approval_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "project_path": self.project_path,
            "violations": [item.as_dict() for item in self.violations],
            "scanned_files": self.scanned_files,
            "scanned_added_lines": self.scanned_added_lines,
            "error": self.error,
            "approval_id": self.approval_id,
        }


class ChangeGuard:
    """Fail-closed detector for non-production placeholders in code changes."""

    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        env = merged_env(config)
        self.enabled = _env_bool(
            env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_ENABLED"), True
        )
        self.fail_closed = _env_bool(
            env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_FAIL_CLOSED"), True
        )
        self.allow_marker = (
            env.get("DENIS_SPRINT_PLACEHOLDER_ALLOW_MARKER")
            or "denis:allow-placeholder"
        ).strip()
        self.max_violations = max(
            50, int(env.get("DENIS_SPRINT_PLACEHOLDER_GUARD_MAX") or "300")
        )

        self.patterns: list[tuple[str, re.Pattern[str]]] = [
            ("placeholder", re.compile(r"(?i)\bplaceholder(s)?\b")),
            ("stub", re.compile(r"(?i)\bstub(s|bed)?\b")),
            ("mock", re.compile(r"(?i)\bmock(s|ed|ing)?\b")),
            ("simulation", re.compile(r"(?i)\bsimulat(e|ion|ed|ing)\b")),
            ("not_implemented", re.compile(r"\bNotImplementedError\b")),
            ("todo", re.compile(r"(?i)\b(TODO|FIXME|XXX)\b")),
            ("coming_soon", re.compile(r"(?i)coming soon|to be implemented|tbd")),
            ("pass_placeholder", re.compile(r"^\s*pass\s*(#.*)?$")),
            # Nuevos patrones para contracts y tests
            (
                "contract_missing_validation",
                re.compile(r"class\s+\w+.*?BaseModel.*?validators\s*="),
            ),
            (
                "test_missing",
                re.compile(r"def\s+(test_|tests\.)"),
            ),  # Simple heuristic, improve later
        ]

        # Patrones de archivos que requieren tests
        self.requires_test_patterns = [
            re.compile(r"/(?:services?|agents?|crews?|api|models?)/.*\.py$"),
        ]

    def _has_contract_changes(self, project_path: Path) -> bool:
        cmd = ["git", "-C", str(project_path), "diff", "--cached", "--name-only"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
        files = proc.stdout.splitlines()
        return any(f.startswith("contracts/") for f in files)

    def inspect_repo_diff(
        self,
        project_path: Path,
        approval_engine=None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> GuardReport:
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
        return self.inspect_diff_text(
            project_path=project_path, diff_text=proc.stdout or ""
        )

    def inspect_diff_text(self, *, project_path: Path, diff_text: str) -> GuardReport:
        current_file = ""
        scan_current_file = True
        line_no = 0
        scanned_files: set[str] = set()
        scanned_added_lines = 0
        violations: list[GuardViolation] = []

        # Para detección de tests faltantes: recopilar archivos modificados
        modified_files: set[str] = set()

        for raw in diff_text.splitlines():
            if raw.startswith("+++ b/"):
                current_file = raw[6:].strip()
                scan_current_file = _should_scan_file(current_file)
                scanned_files.add(current_file)
                # Si es archivo de código que requiere test, registrarlo
                if scan_current_file and self._requires_test(current_file):
                    modified_files.add(current_file)
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
                    # Detectar violaciones específicas de contracts
                    if category == "contract_missing_validation":
                        # Más específico: si se añade modelo BaseModel sin validadores
                        # Ya capturemos por patrón, no necesitamos lógica extra
                        pass
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

        # Chequeo posterior: tests faltantes para archivos modificados
        for mod_file in modified_files:
            if not self._has_test_for(project_path, mod_file):
                violations.append(
                    GuardViolation(
                        file_path=mod_file,
                        line_no=1,  # Línea genérica
                        category="missing_test",
                        pattern="test_file_missing",
                        line=f"No se encontró test para {mod_file}",
                    )
                )

        status = "clean" if not violations else "alert"
        contract_changes = self._has_contract_changes(project_path)
        approval_id = None
        if (violations or contract_changes) and approval_engine and session_id:
            reason = "Stubs/placeholders detected in diff" if violations else "Contract changes detected"
            diff_summary = f"Violations: {len(violations)}" if violations else "Contract files modified"
            risk = "high" if contract_changes else "medium"
            approval_id = approval_engine.request_approval(
                session_id=session_id,
                task_id=task_id,
                reason=reason,
                diff_summary=diff_summary,
                risk=risk,
            )
        return GuardReport(
            status=status,
            project_path=str(project_path),
            violations=violations,
            scanned_files=len(scanned_files),
            scanned_added_lines=scanned_added_lines,
            approval_id=approval_id,
        )

    def _requires_test(self, file_path: str) -> bool:
        """Determina si un archivo requiere test asociado."""
        # Excluir tests, docs,配置文件
        skip_suffixes = (
            "test_",
            "conftest.py",
            ".md",
            ".rst",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
        )
        if any(file_path.endswith(s) for s in skip_suffixes):
            return False
        # Solo archivos en src/ o módulos principales
        if file_path.startswith(("tests/", "docs/", "contextpacks/", ".", "venv")):
            return False
        # Si coincide con patrón de módulos que requieren test
        for pat in self.requires_test_patterns:
            if pat.search(file_path):
                return True
        return False

    def _has_test_for(self, project_root: Path, source_file: str) -> bool:
        """Verifica si existe un test para el archivo fuente."""
        # Estrategias:
        # 1. tests/<source_file>  -> tests/services/crew_manager.py
        # 2. tests/test_<nombre>.py
        # 3. tests/<dirname>/test_<nombre>.py
        src_path = Path(source_file)
        possible_tests = [
            project_root / "tests" / src_path.relative_to(project_root / "src")
            if str(src_path).startswith("src/")
            else None,
            project_root / "tests" / f"test_{src_path.name}",
            project_root / "tests" / src_path.parent / f"test_{src_path.name}",
        ]
        for p in possible_tests:
            if p and p.exists():
                return True
        return False


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
