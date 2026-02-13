import asyncio
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class DENISAgent:
    DEFAULT_TIMEOUT = 30

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _load_plan(self, plan_path: str) -> dict:
        full_path = self.base_dir / plan_path
        if not full_path.exists():
            raise FileNotFoundError(f"Plan not found: {full_path}")
        with open(full_path) as f:
            return json.load(f)

    def _compute_plan_hash(self, plan: dict) -> str:
        content = json.dumps(plan, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_tail(self, text: str, lines: int = 20) -> str:
        text_lines = text.splitlines()
        return "\n".join(text_lines[-lines:])

    async def _run_command(self, cmd: str, timeout: Optional[int] = None) -> dict:
        timeout = timeout or self.DEFAULT_TIMEOUT
        result = {
            "cmd": cmd,
            "returncode": None,
            "timeout": False,
            "stdout_tail": "",
            "stderr_tail": "",
            "stdout_full": "",
            "stderr_full": "",
        }
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                result["returncode"] = proc.returncode
                result["stdout_full"] = stdout.decode("utf-8", errors="replace")
                result["stderr_full"] = stderr.decode("utf-8", errors="replace")
                result["stdout_tail"] = self._get_tail(result["stdout_full"])
                result["stderr_tail"] = self._get_tail(result["stderr_full"])
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                result["timeout"] = True
                result["returncode"] = -1
        except Exception as e:
            result["returncode"] = -1
            result["stderr_tail"] = str(e)
        return result

    def _check_artifacts(self, expected_artifacts: list) -> tuple[list, list]:
        found = []
        missing = []
        for artifact_path in expected_artifacts:
            full_path = self.base_dir / artifact_path
            if full_path.exists():
                found.append(artifact_path)
            else:
                missing.append(artifact_path)
        return found, missing

    def _validate_item(self, item: dict) -> tuple[bool, str]:
        if not item.get("commands"):
            return False, "empty_commands"
        if not item.get("expected_artifacts"):
            return False, "no_expected_artifacts"
        return True, ""

    async def run_sprint(self, plan_path: str, max_items: int = 3) -> dict:
        plan = self._load_plan(plan_path)
        plan_hash = self._compute_plan_hash(plan)

        items = plan.get("items", [])
        sorted_items = sorted(
            items,
            key=lambda x: (x.get("severity", 0), x.get("confidence", 0)),
            reverse=True,
        )

        executed_items = []
        blocked_items = []
        success_count = 0
        failure_count = 0

        for i, item in enumerate(sorted_items[:max_items]):
            item_id = item.get("item_id", f"item_{i}")
            started_utc = datetime.now(timezone.utc).isoformat()

            valid, block_reason = self._validate_item(item)
            if not valid:
                blocked_items.append(
                    {
                        "item_id": item_id,
                        "reason": block_reason,
                        "severity": item.get("severity"),
                        "confidence": item.get("confidence"),
                    }
                )
                failure_count += 1
                continue

            commands = item.get("commands", [])
            expected_artifacts = item.get("expected_artifacts", [])
            timeout_per_cmd = item.get("timeout_sec", self.DEFAULT_TIMEOUT)

            commands_run = []
            all_success = True
            failure_reasons = []

            for cmd in commands:
                cmd_result = await self._run_command(cmd, timeout_per_cmd)
                commands_run.append(cmd_result)
                if cmd_result["timeout"]:
                    all_success = False
                    failure_reasons.append(f"timeout: {cmd}")
                elif cmd_result["returncode"] != 0:
                    all_success = False
                    failure_reasons.append(
                        f"returncode={cmd_result['returncode']}: {cmd}"
                    )

            if all_success:
                found, missing = self._check_artifacts(expected_artifacts)
                if missing:
                    all_success = False
                    failure_reasons.append(f"missing_artifacts: {missing}")
            else:
                found, missing = self._check_artifacts(expected_artifacts)

            finished_utc = datetime.now(timezone.utc).isoformat()

            executed_items.append(
                {
                    "item_id": item_id,
                    "severity": item.get("severity"),
                    "confidence": item.get("confidence"),
                    "commands_run": commands_run,
                    "artifacts_found": found if all_success else [],
                    "success": all_success,
                    "failure_reasons": failure_reasons,
                    "expected_artifacts": expected_artifacts,
                    "started_utc": started_utc,
                    "finished_utc": finished_utc,
                }
            )

            if all_success:
                success_count += 1
            else:
                failure_count += 1

        if success_count > 0 and failure_count > 0:
            overall_status = "partial"
        elif success_count > 0:
            overall_status = "green"
        else:
            overall_status = "failed"

        artifact = {
            "ok": overall_status != "failed",
            "overall_status": overall_status,
            "executed_items": executed_items,
            "blocked_items": blocked_items,
            "plan_hash": plan_hash,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        output_dir = self.base_dir / "artifacts" / "agent"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "denis_agent_sprint_run.json"
        with open(output_path, "w") as f:
            json.dump(artifact, f, indent=2)

        return artifact


async def main():
    import sys

    plan_path = (
        sys.argv[1] if len(sys.argv) > 1 else "artifacts/orchestration/work_plan.json"
    )
    max_items = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    agent = DENISAgent()
    result = await agent.run_sprint(plan_path, max_items=max_items)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
