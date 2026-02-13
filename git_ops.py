import subprocess
import time
from typing import Any, Dict, Optional

from safety_limits import SafetyLimits


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class GitOpsManager:
    """
    GitOps minimal:
    - dry_run(diff, target_path): NO aplica cambios, solo valida SafetyLimits y devuelve simulación.
    - status_only(): lee git status --porcelain; fail-open si git/no repo.
    """

    def __init__(self, safety: Optional[SafetyLimits] = None) -> None:
        self.safety = safety or SafetyLimits()

    def dry_run(self, diff: str, target_path: str) -> Dict[str, Any]:
        safety_verdict = self.safety.check_change(target_path, diff, mode="enforce")
        if not safety_verdict.get("ok", False):
            return {
                "status": "blocked",
                "reason": safety_verdict.get("reason"),
                "target_path": target_path,
                "safety_verdict": safety_verdict,
                "timestamp_utc": _utc_now(),
            }

        # Simulación: NO se toca el FS, NO se invoca git apply.
        return {
            "status": "dry_run_success",
            "target_path": target_path,
            "simulated_changes_preview": diff[:200],
            "safety_verdict": safety_verdict,
            "timestamp_utc": _utc_now(),
        }

    def status_only(self) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=".",
            )
            if result.returncode != 0:
                # not a git repo or other error -> degraded/skip, never raise
                return {
                    "status": "skippeddependency",
                    "reason": "git_status_failed",
                    "exit_code": result.returncode,
                    "stderr": (result.stderr or "").strip()[:500],
                    "changes": [],
                    "timestamp_utc": _utc_now(),
                }

            changes = [line for line in (result.stdout or "").splitlines() if line.strip()]
            return {
                "status": "success",
                "exit_code": result.returncode,
                "changes": changes,
                "timestamp_utc": _utc_now(),
            }
        except FileNotFoundError:
            return {
                "status": "skippeddependency",
                "reason": "git_not_installed",
                "exit_code": None,
                "changes": [],
                "timestamp_utc": _utc_now(),
            }
        except Exception as e:
            return {
                "status": "skippeddependency",
                "reason": "git_status_exception",
                "error": str(e),
                "exit_code": None,
                "changes": [],
                "timestamp_utc": _utc_now(),
            }


class PipelineRunner:
    """
    Pipeline interno: SafetyLimits gate + git status (opcional/degraded).
    """

    def __init__(self) -> None:
        self.git_ops = GitOpsManager()

    def run_checks(self, diff: str, target_path: str) -> Dict[str, Any]:
        dry_run = self.git_ops.dry_run(diff, target_path)
        status = self.git_ops.status_only()

        # Invariante: pipeline pasa si el dry-run pasa (git status es informativo).
        pipeline_passed = dry_run.get("status") == "dry_run_success"
        degraded = status.get("status") != "success"

        return {
            "pipeline_passed": pipeline_passed,
            "degraded": degraded,
            "dry_run": dry_run,
            "git_status": status,
            "timestamp_utc": _utc_now(),
        }


def simulate_infra_pipeline(diff: str, target_path: str) -> Dict[str, Any]:
    runner = PipelineRunner()
    return runner.run_checks(diff, target_path)
