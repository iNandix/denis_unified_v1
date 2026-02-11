"""
Self-Extension Engine - Orquestador de auto-extensiones.

Coordina:
- CapabilityDetector: detecta gaps
- ExtensionGenerator: genera codigo
- BehaviorHandbook: patrones extraidos
- Approval workflow: human-in-the-loop

Contratos aplicados:
- L3.EXT.HUMAN_APPROVAL_REQUIRED
- L3.EXT.SANDBOX_VALIDATION
- L3.EXT.REVERSIBILITY
- L3.EXT.CODE_QUALITY_THRESHOLD
- L3.EXT.STYLE_CONSISTENCY
- L3.EXT.DEPENDENCY_MANAGEMENT
- L3.EXT.ONLY_EXTEND_NO_MODIFY
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from denis_unified_v1.autopoiesis.behavior_handbook import create_handbook
from denis_unified_v1.autopoiesis.capability_detector import (
    CapabilityDetector,
    CapabilityGap,
    create_detector,
)
from denis_unified_v1.autopoiesis.extension_generator import (
    ExtensionGenerator,
    GeneratedExtension,
    create_generator,
)
from denis_unified_v1.metacognitive.hooks import (
    emit_reflection,
    get_hooks,
    metacognitive_trace,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_event(channel: str, data: dict[str, Any]) -> None:
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(url, decode_responses=True)
        payload = json.dumps({**data, "timestamp_utc": _utc_now()}, sort_keys=True)
        r.publish(channel, payload)
    except Exception:
        pass


def _audit_event(proposal_id: str, event: str, data: dict[str, Any]) -> None:
    payload = {
        "proposal_id": proposal_id,
        "event": event,
        **data,
        "timestamp_utc": _utc_now(),
    }
    _emit_event("denis:self_extension:audit", payload)
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(url, decode_responses=True)
        key = f"denis:self_extension:audit:{proposal_id}:{int(time.time()*1000)}"
        r.setex(key, 86400 * 30, json.dumps(payload, sort_keys=True))
    except Exception:
        pass


@dataclass
class ExtensionProposal:
    """Propuesta de extension generada."""

    id: str
    gap_id: str
    name: str
    description: str
    type: str
    generated_code: str
    quality_score: float
    template_used: str
    status: str
    approval_status: str
    approved_by: str | None
    approved_at: str | None
    sandbox_result: dict[str, Any] | None
    deployment_result: dict[str, Any] | None
    timestamp_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SandboxResult:
    """Resultado de validacion en sandbox."""

    success: bool
    compilation_passed: bool
    typecheck_passed: bool
    tests_passed: bool
    lint_passed: bool
    security_passed: bool
    output: str
    errors: list[str]
    duration_ms: float


class SelfExtensionEngine:
    """Motor de auto-extension con gate estricto."""

    _FORBIDDEN_IMPORT_ROOTS = {
        "subprocess",
        "socket",
        "ftplib",
        "telnetlib",
        "paramiko",
        "ctypes",
        "pickle",
        "marshal",
        "multiprocessing",
    }
    _FORBIDDEN_PATTERNS = (
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"__import__\s*\(",
        r"os\.system\s*\(",
        r"subprocess\.",
        r"rm\s+-rf",
        r"curl\s+.+\|\s*(bash|sh)",
    )
    _SYSTEM_APPROVERS = {"system", "auto", "bot", "ai", "script", "daemon"}

    def __init__(self):
        self._hooks = get_hooks()
        self._capability_detector: CapabilityDetector = create_detector()
        self._extension_generator: ExtensionGenerator = create_generator()
        self._behavior_handbook = create_handbook()
        self._proposals: list[ExtensionProposal] = []
        self._gaps_detected: list[CapabilityGap] = []

        self._min_quality_score = max(
            0.7, float(os.getenv("DENIS_SELF_EXTENSION_MIN_QUALITY", "0.8"))
        )
        self._allow_system_approval = (
            os.getenv("DENIS_SELF_EXTENSION_ALLOW_SYSTEM_APPROVAL", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )
        deploy_dir = os.getenv("DENIS_SELF_EXTENSION_DEPLOY_DIR", "/tmp/denis_self_extensions")
        self._deploy_root = Path(deploy_dir).expanduser().resolve()
        self._sandbox_timeout_seconds = max(
            5, int(os.getenv("DENIS_SELF_EXTENSION_SANDBOX_TIMEOUT_SECONDS", "20"))
        )
        self._strict_tooling = (
            os.getenv("DENIS_SELF_EXTENSION_STRICT_TOOLING", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self._sandbox_python = self._resolve_sandbox_python()

    def _find_proposal(self, proposal_id: str) -> ExtensionProposal | None:
        return next((p for p in self._proposals if p.id == proposal_id), None)

    def _extract_import_roots(self, code: str) -> set[str]:
        roots: set[str] = set()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return roots
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    roots.add(node.module.split(".")[0])
        return roots

    def _contains_forbidden_patterns(self, code: str) -> list[str]:
        found: list[str] = []
        for pattern in self._FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                found.append(pattern)
        return found

    def _to_module_name(self, value: str) -> str:
        module = value.replace("-", "_").replace(" ", "_").lower()
        module = re.sub(r"[^a-z0-9_]+", "_", module).strip("_")
        if not module:
            module = "generated_extension"
        if module[0].isdigit():
            module = f"ext_{module}"
        return module

    def _resolve_sandbox_python(self) -> str:
        env_override = (os.getenv("DENIS_SELF_EXTENSION_SANDBOX_PYTHON") or "").strip()
        candidates = [
            env_override,
            "/tmp/denis_gate_venv/bin/python",
            "/media/jotah/SSD_denis/.venv_oceanai/bin/python3",
            sys.executable,
            "python3",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            if "/" in candidate and not os.path.exists(candidate):
                continue
            if "/" not in candidate and shutil.which(candidate) is None:
                continue
            return candidate
        return sys.executable

    def _run_command(self, cmd: list[str], cwd: Path) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._sandbox_timeout_seconds,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "").strip()[:4000],
                "stderr": (proc.stderr or "").strip()[:4000],
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"timeout>{self._sandbox_timeout_seconds}s",
            }

    def _python_has_module(self, module_name: str) -> bool:
        check = self._run_command(
            [self._sandbox_python, "-c", f"import {module_name}"],
            cwd=Path.cwd(),
        )
        return bool(check["ok"])

    def _build_rollback_plan(self, proposal_id: str) -> dict[str, Any]:
        return {
            "strategy": "delete_generated_files",
            "remove_paths": [
                "{deploy_root}/{proposal_id}/*.py",
                "{deploy_root}/{proposal_id}/*.md",
            ],
            "redis_cleanup": [f"denis:self_extension:audit:{proposal_id}:*"],
        }

    def _build_extension_payload(self, proposal: ExtensionProposal) -> GeneratedExtension:
        return GeneratedExtension(
            id=proposal.metadata.get("extension_id", proposal.id),
            type=proposal.metadata["extension_type"],
            name=proposal.name,
            description=proposal.description,
            code=proposal.generated_code,
            imports=proposal.metadata.get("imports", []),
            dependencies=proposal.metadata.get("dependencies", []),
            test_code=proposal.metadata.get("test_code", ""),
            doc_code=proposal.metadata.get("doc_code", ""),
            checksum=proposal.metadata.get("checksum", ""),
            quality_score=proposal.quality_score,
            timestamp_utc=proposal.timestamp_utc,
            gap_id=proposal.gap_id,
        )

    def build_handbook(self) -> dict[str, Any]:
        entry = self._behavior_handbook.build()
        emit_reflection(
            reflection_type="handbook_built",
            target="behavior_handbook",
            finding=f"Handbook construido con {entry.metadata.get('patterns_count', 0)} patrones",
            confidence=0.9,
        )
        return {
            "patterns_count": entry.metadata.get("patterns_count", 0),
            "timestamp_utc": _utc_now(),
        }

    @metacognitive_trace("self_extension_detect_gaps")
    def detect_gaps(self) -> list[CapabilityGap]:
        gaps = self._capability_detector.detect_all()
        self._gaps_detected = gaps
        emit_reflection(
            reflection_type="gaps_detected",
            target="self_extension",
            finding=f"Detectados {len(gaps)} gaps",
            confidence=0.8,
            recommendation="Revisar gaps de severity alta primero"
            if any(g.severity.value == "high" for g in gaps)
            else None,
        )
        return gaps

    @metacognitive_trace("self_extension_generate_extension")
    def generate_extension(
        self,
        gap: CapabilityGap,
        template_type: str = "basic_tool",
    ) -> ExtensionProposal | None:
        emit_reflection(
            reflection_type="extension_generation_started",
            target=gap.id,
            finding=f"Generando extension para: {gap.title}",
            confidence=0.7,
        )
        try:
            name = gap.title.replace(" ", "-").lower()[:30]
            if template_type == "basic_tool":
                extension = self._extension_generator.generate_tool(
                    name=name,
                    description=gap.description,
                    gap_id=gap.id,
                )
            elif template_type == "memory_processor":
                extension = self._extension_generator.generate_memory_processor(
                    name=name,
                    description=gap.description,
                    gap_id=gap.id,
                )
            else:
                extension = self._extension_generator.generate_tool(
                    name=name,
                    description=gap.description,
                    gap_id=gap.id,
                )
        except Exception as e:
            emit_reflection(
                reflection_type="extension_generation_failed",
                target=gap.id,
                finding=f"Error generando extension: {str(e)}",
                confidence=0.3,
            )
            return None

        proposal = ExtensionProposal(
            id=f"prop_{extension.id}",
            gap_id=gap.id,
            name=extension.name,
            description=extension.description,
            type=extension.type.value,
            generated_code=extension.code,
            quality_score=extension.quality_score,
            template_used=template_type,
            status="generated",
            approval_status="pending",
            approved_by=None,
            approved_at=None,
            sandbox_result=None,
            deployment_result=None,
            timestamp_utc=_utc_now(),
            metadata={
                "checksum": extension.checksum,
                "imports": extension.imports,
                "dependencies": extension.dependencies,
                "extension_type": extension.type,
                "extension_id": extension.id,
                "test_code": extension.test_code,
                "doc_code": extension.doc_code,
                "rollback_plan": self._build_rollback_plan(f"prop_{extension.id}"),
            },
        )
        self._proposals.append(proposal)
        _audit_event(proposal.id, "generated", {"quality_score": proposal.quality_score})

        emit_reflection(
            reflection_type="extension_generated",
            target=proposal.id,
            finding=f"Extension generada: {proposal.name}",
            confidence=proposal.quality_score,
            recommendation=f"Quality score: {proposal.quality_score:.0%}",
        )
        return proposal

    def validate_style_consistency(self, proposal: ExtensionProposal) -> dict[str, Any]:
        code = proposal.generated_code
        errors: list[str] = []
        if "from __future__ import annotations" not in code:
            errors.append("missing_future_annotations")
        if not re.search(r"^class\s+[A-Z][A-Za-z0-9_]*", code, flags=re.MULTILINE):
            errors.append("missing_pascalcase_class")
        for line_no, line in enumerate(code.splitlines(), start=1):
            if len(line) > 120:
                errors.append(f"line_too_long:{line_no}")
                break
            if "\t" in line:
                errors.append(f"tab_character:{line_no}")
                break
        return {"passed": not errors, "errors": errors}

    def validate_dependencies(self, proposal: ExtensionProposal) -> dict[str, Any]:
        imports = self._extract_import_roots(proposal.generated_code)
        blocked = sorted(imports & self._FORBIDDEN_IMPORT_ROOTS)
        deps = set(proposal.metadata.get("dependencies", []))
        errors: list[str] = []
        if blocked:
            errors.append(f"forbidden_imports:{','.join(blocked)}")
        if "neo4j" in imports and "neo4j" not in deps:
            errors.append("missing_declared_dependency:neo4j")
        if "redis" in imports and "redis" not in deps:
            errors.append("missing_declared_dependency:redis")
        return {"passed": not errors, "errors": errors, "imports": sorted(imports)}

    def validate_reversibility(self, proposal: ExtensionProposal) -> dict[str, Any]:
        plan = proposal.metadata.get("rollback_plan")
        errors: list[str] = []
        if not isinstance(plan, dict):
            errors.append("rollback_plan_missing")
        else:
            if not plan.get("strategy"):
                errors.append("rollback_strategy_missing")
            remove_paths = plan.get("remove_paths")
            if not isinstance(remove_paths, list) or not remove_paths:
                errors.append("rollback_remove_paths_missing")
        return {"passed": not errors, "errors": errors}

    def validate_human_approval(self, approved_by: str) -> dict[str, Any]:
        actor = (approved_by or "").strip().lower()
        if not actor:
            return {"passed": False, "reason": "empty_approver"}
        if not self._allow_system_approval and actor in self._SYSTEM_APPROVERS:
            return {"passed": False, "reason": "non_human_approver"}
        return {"passed": True, "reason": "ok"}

    def validate_sandbox_execution(self, proposal: ExtensionProposal) -> SandboxResult:
        start = time.perf_counter()
        errors: list[str] = []
        compilation_passed = False
        typecheck_passed = False
        tests_passed = False
        lint_passed = False
        security_passed = False
        output_lines: list[str] = []

        code = proposal.generated_code
        forbidden = self._contains_forbidden_patterns(code)
        if forbidden:
            errors.append(f"forbidden_patterns:{','.join(forbidden)}")

        dep_check = self.validate_dependencies(proposal)
        if not dep_check["passed"]:
            errors.extend(dep_check["errors"])

        style_check = self.validate_style_consistency(proposal)
        if not style_check["passed"]:
            errors.extend(style_check["errors"])

        try:
            ast.parse(code)
        except Exception as e:
            errors.append(f"ast_parse_error:{e}")

        module_name = self._to_module_name(proposal.name or proposal.id)
        test_code = proposal.metadata.get("test_code", "")
        if not isinstance(test_code, str):
            test_code = ""

        if not test_code.strip():
            test_code = f"""from {module_name} import *  # noqa: F401,F403

def test_module_imports():
    assert True
"""

        with tempfile.TemporaryDirectory(prefix="denis_selfext_") as sandbox_dir_raw:
            sandbox_dir = Path(sandbox_dir_raw)
            code_path = sandbox_dir / f"{module_name}.py"
            test_path = sandbox_dir / f"test_{module_name}.py"

            code_path.write_text(code, encoding="utf-8")
            test_path.write_text(test_code, encoding="utf-8")

            compile_cmd = [
                self._sandbox_python,
                "-m",
                "py_compile",
                str(code_path),
                str(test_path),
            ]
            compile_result = self._run_command(compile_cmd, cwd=sandbox_dir)
            compilation_passed = bool(compile_result["ok"])
            output_lines.append(f"compile_rc={compile_result['returncode']}")
            if compile_result["stderr"]:
                output_lines.append(f"compile_err={compile_result['stderr']}")
            if not compilation_passed:
                errors.append(f"compile_error:rc={compile_result['returncode']}")

            has_ruff = self._python_has_module("ruff")
            if not has_ruff:
                lint_passed = not self._strict_tooling
                errors.append("missing_tool:ruff")
            else:
                lint_cmd = [
                    self._sandbox_python,
                    "-m",
                    "ruff",
                    "check",
                    str(code_path),
                    str(test_path),
                ]
                lint_result = self._run_command(lint_cmd, cwd=sandbox_dir)
                lint_passed = bool(lint_result["ok"])
                output_lines.append(f"ruff_rc={lint_result['returncode']}")
                if lint_result["stdout"]:
                    output_lines.append(f"ruff_out={lint_result['stdout']}")
                if lint_result["stderr"]:
                    output_lines.append(f"ruff_err={lint_result['stderr']}")
                if not lint_passed:
                    errors.append(f"lint_error:rc={lint_result['returncode']}")

            has_mypy = self._python_has_module("mypy")
            if not has_mypy:
                typecheck_passed = not self._strict_tooling
                errors.append("missing_tool:mypy")
            else:
                typecheck_cmd = [
                    self._sandbox_python,
                    "-m",
                    "mypy",
                    "--hide-error-context",
                    "--no-error-summary",
                    "--ignore-missing-imports",
                    "--follow-imports=silent",
                    str(code_path),
                    str(test_path),
                ]
                typecheck_result = self._run_command(typecheck_cmd, cwd=sandbox_dir)
                typecheck_passed = bool(typecheck_result["ok"])
                output_lines.append(f"mypy_rc={typecheck_result['returncode']}")
                if typecheck_result["stdout"]:
                    output_lines.append(f"mypy_out={typecheck_result['stdout']}")
                if typecheck_result["stderr"]:
                    output_lines.append(f"mypy_err={typecheck_result['stderr']}")
                if not typecheck_passed:
                    errors.append(f"typecheck_error:rc={typecheck_result['returncode']}")

            has_pytest = self._python_has_module("pytest")
            if not has_pytest:
                tests_passed = not self._strict_tooling
                errors.append("missing_tool:pytest")
            else:
                test_cmd = [
                    self._sandbox_python,
                    "-m",
                    "pytest",
                    "-q",
                    str(test_path),
                ]
                test_result = self._run_command(test_cmd, cwd=sandbox_dir)
                tests_passed = bool(test_result["ok"])
                output_lines.append(f"pytest_rc={test_result['returncode']}")
                if test_result["stdout"]:
                    output_lines.append(f"pytest_out={test_result['stdout']}")
                if test_result["stderr"]:
                    output_lines.append(f"pytest_err={test_result['stderr']}")
                if not tests_passed:
                    errors.append(f"tests_error:rc={test_result['returncode']}")

            has_bandit = self._python_has_module("bandit")
            if not has_bandit:
                security_passed = not self._strict_tooling
                errors.append("missing_tool:bandit")
            else:
                bandit_cmd = [
                    self._sandbox_python,
                    "-m",
                    "bandit",
                    "-q",
                    "-r",
                    str(code_path),
                ]
                bandit_result = self._run_command(bandit_cmd, cwd=sandbox_dir)
                security_passed = bool(bandit_result["ok"])
                output_lines.append(f"bandit_rc={bandit_result['returncode']}")
                if bandit_result["stdout"]:
                    output_lines.append(f"bandit_out={bandit_result['stdout']}")
                if bandit_result["stderr"]:
                    output_lines.append(f"bandit_err={bandit_result['stderr']}")
                if not security_passed:
                    errors.append(f"security_error:rc={bandit_result['returncode']}")

        duration_ms = (time.perf_counter() - start) * 1000
        success = (
            compilation_passed
            and typecheck_passed
            and tests_passed
            and lint_passed
            and security_passed
            and not errors
        )
        return SandboxResult(
            success=success,
            compilation_passed=compilation_passed,
            typecheck_passed=typecheck_passed,
            tests_passed=tests_passed,
            lint_passed=lint_passed,
            security_passed=security_passed,
            output="\n".join(output_lines) if output_lines else "Sandbox validation completed",
            errors=errors,
            duration_ms=round(duration_ms, 3),
        )

    def validate_sandbox(self, proposal: ExtensionProposal) -> SandboxResult:
        result = self.validate_sandbox_execution(proposal)
        proposal.sandbox_result = {
            "success": result.success,
            "compilation_passed": result.compilation_passed,
            "typecheck_passed": result.typecheck_passed,
            "tests_passed": result.tests_passed,
            "lint_passed": result.lint_passed,
            "security_passed": result.security_passed,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
        }
        proposal.status = "sandbox_passed" if result.success else "sandbox_failed"
        _audit_event(
            proposal.id,
            "sandbox_validation",
            {
                "success": result.success,
                "errors": result.errors,
                "duration_ms": result.duration_ms,
            },
        )
        emit_reflection(
            reflection_type="sandbox_validation",
            target=proposal.id,
            finding=f"Sandbox: {'APROBADO' if result.success else 'RECHAZADO'}",
            confidence=1.0 if result.success else 0.3,
            recommendation=", ".join(result.errors) if result.errors else None,
        )
        return result

    def _run_gate_checks(self, proposal: ExtensionProposal) -> dict[str, dict[str, Any]]:
        return {
            "quality": {
                "passed": proposal.quality_score >= self._min_quality_score,
                "errors": []
                if proposal.quality_score >= self._min_quality_score
                else [
                    f"quality_below_threshold:{proposal.quality_score:.3f}<{self._min_quality_score:.3f}"
                ],
            },
            "sandbox": {
                "passed": bool(proposal.sandbox_result and proposal.sandbox_result.get("success")),
                "errors": []
                if proposal.sandbox_result and proposal.sandbox_result.get("success")
                else ["sandbox_missing_or_failed"],
            },
            "style": self.validate_style_consistency(proposal),
            "dependencies": self.validate_dependencies(proposal),
            "reversibility": self.validate_reversibility(proposal),
        }

    def submit_for_approval(self, proposal: ExtensionProposal) -> dict[str, Any]:
        if proposal.status not in {"sandbox_passed", "generated"}:
            return {"status": "rejected", "reason": "invalid_state_for_submission"}

        checks = self._run_gate_checks(proposal)
        failed = [name for name, check in checks.items() if not check["passed"]]
        if failed:
            _audit_event(proposal.id, "gate_rejected_submission", {"failed_checks": failed})
            emit_reflection(
                reflection_type="approval_rejected_gate",
                target=proposal.id,
                finding=f"Gate rechazado: {', '.join(failed)}",
                confidence=1.0,
            )
            return {
                "status": "rejected",
                "reason": "gate_failed",
                "failed_checks": failed,
                "checks": checks,
            }

        proposal.status = "pending_approval"
        proposal.approval_status = "pending"
        _emit_event(
            "denis:self_extension:approval_required",
            {
                "proposal_id": proposal.id,
                "name": proposal.name,
                "quality_score": proposal.quality_score,
                "gap_id": proposal.gap_id,
            },
        )
        _audit_event(proposal.id, "approval_submitted", {"quality_score": proposal.quality_score})
        emit_reflection(
            reflection_type="approval_submitted",
            target=proposal.id,
            finding="Propuesta enviada para aprobacion",
            confidence=0.9,
            recommendation="Esperando aprobacion humana",
        )
        return {
            "status": "submitted",
            "proposal_id": proposal.id,
            "quality_score": proposal.quality_score,
            "checks": checks,
        }

    def approve_proposal(
        self,
        proposal_id: str,
        approved_by: str = "human",
    ) -> dict[str, Any]:
        proposal = self._find_proposal(proposal_id)
        if not proposal:
            return {"status": "error", "reason": "proposal_not_found"}
        if proposal.status != "pending_approval":
            return {"status": "error", "reason": "not_pending_approval"}

        approval_check = self.validate_human_approval(approved_by)
        if not approval_check["passed"]:
            _audit_event(
                proposal.id,
                "approval_rejected_actor",
                {"approved_by": approved_by, "reason": approval_check["reason"]},
            )
            return {
                "status": "rejected",
                "reason": approval_check["reason"],
                "proposal_id": proposal.id,
            }

        checks = self._run_gate_checks(proposal)
        failed = [name for name, check in checks.items() if not check["passed"]]
        if failed:
            _audit_event(proposal.id, "approval_rejected_gate", {"failed_checks": failed})
            return {
                "status": "rejected",
                "reason": "gate_failed",
                "failed_checks": failed,
            }

        proposal.approval_status = "approved"
        proposal.approved_by = approved_by
        proposal.approved_at = _utc_now()
        proposal.status = "approved"
        _emit_event(
            "denis:self_extension:proposal_approved",
            {"proposal_id": proposal.id, "approved_by": approved_by},
        )
        _audit_event(proposal.id, "approved", {"approved_by": approved_by})
        emit_reflection(
            reflection_type="proposal_approved",
            target=proposal.id,
            finding=f"Propuesta aprobada por: {approved_by}",
            confidence=1.0,
        )
        return {
            "status": "approved",
            "proposal_id": proposal.id,
            "approved_by": approved_by,
            "approved_at": proposal.approved_at,
        }

    def reject_proposal(self, proposal_id: str, reason: str) -> dict[str, Any]:
        proposal = self._find_proposal(proposal_id)
        if not proposal:
            return {"status": "error", "reason": "proposal_not_found"}
        proposal.approval_status = "rejected"
        proposal.status = "rejected"
        _audit_event(proposal.id, "rejected", {"reason": reason})
        emit_reflection(
            reflection_type="proposal_rejected",
            target=proposal.id,
            finding=f"Rechazada: {reason}",
            confidence=1.0,
        )
        return {"status": "rejected", "proposal_id": proposal_id, "reason": reason}

    def deploy_extension(self, proposal: ExtensionProposal) -> dict[str, Any]:
        if proposal.approval_status != "approved":
            return {"status": "error", "reason": "not_approved"}
        if proposal.approved_by is None:
            return {"status": "error", "reason": "missing_approver"}
        approval_check = self.validate_human_approval(proposal.approved_by)
        if not approval_check["passed"]:
            return {"status": "error", "reason": approval_check["reason"]}

        checks = self._run_gate_checks(proposal)
        failed = [name for name, check in checks.items() if not check["passed"]]
        if failed:
            return {"status": "error", "reason": "gate_failed", "failed_checks": failed}

        proposal_dir = self._deploy_root / proposal.id
        proposal_dir.mkdir(parents=True, exist_ok=True)

        extension = self._build_extension_payload(proposal)
        paths = self._extension_generator.save_extension(extension, str(proposal_dir))
        rollback_plan = {
            "strategy": "delete_generated_files",
            "remove_paths": [path for path in paths.values() if path],
            "redis_cleanup": [f"denis:self_extension:audit:{proposal.id}:*"],
        }
        proposal.metadata["rollback_plan"] = rollback_plan
        proposal.deployment_result = {
            "success": True,
            "paths": paths,
            "deployed_at": _utc_now(),
            "rollback_plan": rollback_plan,
        }
        proposal.status = "deployed"

        self._behavior_handbook.add_success_story(
            name=proposal.name,
            category=proposal.type,
            code=proposal.generated_code[:500],
            context=["deployment", proposal.type],
            outcome=["deployed", "successful"],
        )

        _emit_event(
            "denis:self_extension:deployed",
            {"proposal_id": proposal.id, "name": proposal.name},
        )
        _audit_event(proposal.id, "deployed", {"paths": paths})
        emit_reflection(
            reflection_type="extension_deployed",
            target=proposal.id,
            finding=f"Extension deployada: {proposal.name}",
            confidence=1.0,
        )
        return {
            "status": "deployed",
            "proposal_id": proposal.id,
            "paths": paths,
            "rollback_plan": rollback_plan,
        }

    def get_proposals(self, status: str | None = None) -> list[ExtensionProposal]:
        if status:
            return [p for p in self._proposals if p.status == status]
        return self._proposals

    def get_gaps(self, status: str | None = None) -> list[CapabilityGap]:
        detector = create_detector()
        return detector.get_gaps(status)

    def get_status(self) -> dict[str, Any]:
        return {
            "extensions_generated": len([p for p in self._proposals if p.status == "generated"]),
            "sandbox_passed": len([p for p in self._proposals if p.status == "sandbox_passed"]),
            "pending_approval": len([p for p in self._proposals if p.status == "pending_approval"]),
            "approved": len([p for p in self._proposals if p.status == "approved"]),
            "deployed": len([p for p in self._proposals if p.status == "deployed"]),
            "gaps_detected": len(self._gaps_detected),
            "high_severity_gaps": len(
                [g for g in self._gaps_detected if g.severity.value == "high"]
            ),
            "gate": {
                "min_quality_score": self._min_quality_score,
                "allow_system_approval": self._allow_system_approval,
                "deploy_root": str(self._deploy_root),
                "strict_tooling": self._strict_tooling,
                "sandbox_python": self._sandbox_python,
                "sandbox_timeout_seconds": self._sandbox_timeout_seconds,
            },
        }


def create_self_extension_engine() -> SelfExtensionEngine:
    return SelfExtensionEngine()


def validate_human_approval(approved_by: str) -> dict[str, Any]:
    return create_self_extension_engine().validate_human_approval(approved_by)


def validate_sandbox_execution(proposal: ExtensionProposal) -> SandboxResult:
    return create_self_extension_engine().validate_sandbox_execution(proposal)


def validate_style_consistency(proposal: ExtensionProposal) -> dict[str, Any]:
    return create_self_extension_engine().validate_style_consistency(proposal)


def validate_dependencies(proposal: ExtensionProposal) -> dict[str, Any]:
    return create_self_extension_engine().validate_dependencies(proposal)


def validate_reversibility(proposal: ExtensionProposal) -> dict[str, Any]:
    return create_self_extension_engine().validate_reversibility(proposal)


if __name__ == "__main__":
    print("=== SELF-EXTENSION ENGINE ===")
    engine = create_self_extension_engine()
    print(json.dumps(engine.get_status(), indent=2))
