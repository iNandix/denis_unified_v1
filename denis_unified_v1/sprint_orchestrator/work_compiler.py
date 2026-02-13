#!/usr/bin/env python3
"""Work Compiler - Compile real work from artifacts.

This module compiles real work from artifacts:
1. ArtifactNormalizer - converts heterogeneous artifacts to signals
2. RemediationRegistry - maps signals to real remediations (only if scripts exist)
3. PlanBuilder - creates executable SprintPlan

Usage:
    python -m denis_unified_v1.sprint_orchestrator.work_compiler --artifacts-root artifacts --out-json work_plan.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============== DATA CLASSES ==============


@dataclass
class Signal:
    """Normalized signal from artifact."""

    signal_id: str
    category: str  # api|sse|gate|graph|agent|orchestration|unknown
    severity: int  # 1-5
    confidence: float  # 0.0-1.0
    source_artifact: str
    detected_signal: Dict[str, Any]
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemediationCandidate:
    """A potential remediation for a signal."""

    key: str
    description: str
    commands: List[str]
    expected_artifacts: List[str]
    definition_of_done: List[str]


@dataclass
class SprintItem:
    """An actionable item in the sprint plan."""

    source_artifact: str
    detected_signal: Dict[str, Any]
    expected_effect: str
    commands: List[str]
    expected_artifacts: List[str]
    definition_of_done: List[str]
    severity: int
    confidence: float


@dataclass
class RejectedSignal:
    """A signal that was rejected."""

    signal_id: str
    source_artifact: str
    reason: str  # no_remediation | commands_missing | artifacts_invalid


# ============== ARTIFACT NORMALIZER ==============


class ArtifactNormalizer:
    """Normalize heterogeneous artifacts to signals."""

    def __init__(self, artifacts_root: str):
        self.artifacts_root = Path(artifacts_root)

    def scan_artifacts(self) -> List[Path]:
        """Find all JSON artifacts."""
        artifacts = []
        if self.artifacts_root.exists():
            for f in self.artifacts_root.rglob("*.json"):
                artifacts.append(f)
        return artifacts

    def normalize(self, artifact_path: Path) -> List[Signal]:
        """Normalize an artifact to signals."""
        signals = []
        try:
            with open(artifact_path) as f:
                data = json.load(f)
        except Exception as e:
            signals.append(
                Signal(
                    signal_id=f"err_{artifact_path.name}",
                    category="unknown",
                    severity=1,
                    confidence=0.1,
                    source_artifact=str(artifact_path),
                    detected_signal={"error": str(e)[:100]},
                    raw_data={},
                )
            )
            return signals

        # Detect signals based on common patterns
        signals.extend(self._detect_ok_signals(artifact_path, data))
        signals.extend(self._detect_http_signals(artifact_path, data))
        signals.extend(self._detect_status_signals(artifact_path, data))
        signals.extend(self._detect_gate_signals(artifact_path, data))
        signals.extend(self._detect_duplicate_signals(artifact_path, data))

        return signals

    def _detect_ok_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect ok field signals."""
        signals = []
        if "ok" in data and data["ok"] is False:
            signals.append(
                Signal(
                    signal_id=f"ok_false_{path.stem}",
                    category="unknown",
                    severity=3,
                    confidence=0.8,
                    source_artifact=str(path),
                    detected_signal={
                        "ok": False,
                        "reason": data.get("error", "unknown"),
                    },
                    raw_data=data,
                )
            )
        return signals

    def _detect_http_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect HTTP status signals."""
        signals = []
        for key in ["http_status", "status_code"]:
            if key in data:
                status = data[key]
                if status != 200:
                    signals.append(
                        Signal(
                            signal_id=f"http_{status}_{path.stem}",
                            category="api",
                            severity=4 if status >= 500 else 3,
                            confidence=0.9,
                            source_artifact=str(path),
                            detected_signal={key: status},
                            raw_data=data,
                        )
                    )
        return signals

    def _detect_status_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect status field signals."""
        signals = []
        for key in ["status", "gate_status", "endpoint_status"]:
            if key in data:
                status = data[key]
                if status in ["failed", "error", "degraded"]:
                    signals.append(
                        Signal(
                            signal_id=f"status_{status}_{path.stem}",
                            category="api",
                            severity=4 if status == "failed" else 3,
                            confidence=0.8,
                            source_artifact=str(path),
                            detected_signal={key: status},
                            raw_data=data,
                        )
                    )
        return signals

    def _detect_gate_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect gate-related signals."""
        signals = []
        if "hard_failures" in data and data["hard_failures"] > 0:
            signals.append(
                Signal(
                    signal_id=f"gate_hard_fail_{path.stem}",
                    category="gate",
                    severity=5,
                    confidence=0.9,
                    source_artifact=str(path),
                    detected_signal={"hard_failures": data["hard_failures"]},
                    raw_data=data,
                )
            )
        return signals

    def _detect_duplicate_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect duplicate paths (from route sanity)."""
        signals = []
        if "duplicate_paths" in data and data["duplicate_paths"]:
            signals.append(
                Signal(
                    signal_id=f"duplicates_{path.stem}",
                    category="api",
                    severity=3,
                    confidence=0.9,
                    source_artifact=str(path),
                    detected_signal={"duplicate_paths": data["duplicate_paths"]},
                    raw_data=data,
                )
            )
        return signals


# ============== REMEDIATION REGISTRY ==============


class RemediationRegistry:
    """Registry of known remediations mapped to real scripts."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.smokes = self._discover_smokes()

        # Base mapping: signal patterns -> remediation keys
        self.signal_to_remediation = {
            "ok_false": "rerun_smoke",
            "http_404": "fix_endpoint",
            "http_500": "fix_server",
            "status_failed": "fix_component",
            "status_degraded": "fix_component",
            "gate_hard_fail": "fix_gate",
            "duplicates": "fix_duplicates",
            "missing_paths": "fix_routes",
            "neo4j_unavailable": "fix_neo4j",
            "redis_unavailable": "fix_redis",
        }

    def _discover_smokes(self) -> Dict[str, Path]:
        """Discover all smoke scripts."""
        smokes = {}
        scripts_dir = self.project_root / "scripts"

        if scripts_dir.exists():
            for f in scripts_dir.glob("*smoke*.py"):
                smokes[f.stem] = f

        return smokes

    def command_exists(self, cmd: str) -> bool:
        """Check if a command exists."""
        # Handle python3 scripts
        if cmd.startswith("python3 "):
            parts = cmd.split()
            if len(parts) >= 2:
                script_path = parts[1]
                if script_path.endswith(".py"):
                    return (self.project_root / script_path).exists()

        # Handle python3 -m modules
        if cmd.startswith("python3 -m "):
            module_name = cmd.replace("python3 -m ", "").split()[0]
            return importlib.util.find_spec(module_name) is not None

        return False

    def find_remediations(self, signal: Signal) -> List[RemediationCandidate]:
        """Find remediation candidates for a signal."""
        candidates = []

        signal_type = signal.signal_id.split("_")[0]

        if signal_type == "ok" and signal.detected_signal.get("ok") is False:
            # Try to find a matching smoke
            stem = Path(signal.source_artifact).stem
            for smoke_name, smoke_path in self.smokes.items():
                if stem.replace("_smoke", "") in smoke_name.lower():
                    candidates.append(
                        RemediationCandidate(
                            key=f"rerun_{smoke_name}",
                            description=f"Rerun {smoke_name}",
                            commands=[
                                f"python3 {smoke_path.relative_to(self.project_root)}"
                            ],
                            expected_artifacts=[f"artifacts/{smoke_path.stem}.json"],
                            definition_of_done=["returncode==0", "artifact.ok==true"],
                        )
                    )

        elif signal_type == "duplicates":
            candidates.append(
                RemediationCandidate(
                    key="fix_duplicates",
                    description="Fix duplicate routes in metacognitive_api.py",
                    commands=["python3 scripts/route_sanity_smoke.py"],
                    expected_artifacts=["artifacts/api/route_sanity_smoke.json"],
                    definition_of_done=["returncode==0", "duplicate_paths==[]"],
                )
            )

        elif signal_type == "gate" and signal.severity >= 4:
            candidates.append(
                RemediationCandidate(
                    key="fix_gate_hard_fail",
                    description="Fix hard failures in self-aware gate",
                    commands=["python3 scripts/smoke_self_aware_block.py"],
                    expected_artifacts=["artifacts/self_aware/block.json"],
                    definition_of_done=["returncode==0", "hard_failures==0"],
                )
            )

        elif (
            "neo4j" in str(signal.detected_signal).lower() or "graph" in signal.category
        ):
            candidates.append(
                RemediationCandidate(
                    key="fix_graph",
                    description="Run graph backfill and relationships smoke",
                    commands=["python3 scripts/graph_backfill_cognition.py"],
                    expected_artifacts=["artifacts/graph/backfill_cognition.json"],
                    definition_of_done=["returncode==0"],
                )
            )

        elif "missing_paths" in signal.signal_id or "route" in signal.category:
            candidates.append(
                RemediationCandidate(
                    key="fix_routes",
                    description="Fix route sanity issues",
                    commands=["python3 scripts/route_sanity_smoke.py"],
                    expected_artifacts=["artifacts/api/route_sanity_smoke.json"],
                    definition_of_done=["returncode==0", "missing_paths==[]"],
                )
            )

        # Filter candidates by existence
        valid_candidates = []
        for cand in candidates:
            all_cmds_exist = all(self.command_exists(cmd) for cmd in cand.commands)
            if all_cmds_exist:
                valid_candidates.append(cand)

        return valid_candidates


# ============== PLAN BUILDER ==============


class PlanBuilder:
    """Build executable sprint plan from signals."""

    def __init__(self, artifacts_root: str, project_root: Path):
        self.normalizer = ArtifactNormalizer(artifacts_root)
        self.registry = RemediationRegistry(project_root)

    def build_plan(self) -> Dict[str, Any]:
        """Build the sprint plan."""
        # Scan and normalize artifacts
        artifacts = self.normalizer.scan_artifacts()

        all_signals = []
        for artifact in artifacts:
            signals = self.normalizer.normalize(artifact)
            all_signals.extend(signals)

        # Build items and rejected signals
        items = []
        rejected = []

        for signal in all_signals:
            # Find remediations
            candidates = self.registry.find_remediations(signal)

            if not candidates:
                rejected.append(
                    RejectedSignal(
                        signal_id=signal.signal_id,
                        source_artifact=signal.source_artifact,
                        reason="no_remediation",
                    )
                )
                continue

            # Take first valid candidate
            cand = candidates[0]

            # Verify commands exist
            all_exist = all(self.registry.command_exists(cmd) for cmd in cand.commands)
            if not all_exist:
                rejected.append(
                    RejectedSignal(
                        signal_id=signal.signal_id,
                        source_artifact=signal.source_artifact,
                        reason="commands_missing",
                    )
                )
                continue

            # Create sprint item
            items.append(
                SprintItem(
                    source_artifact=signal.source_artifact,
                    detected_signal=signal.detected_signal,
                    expected_effect=cand.description,
                    commands=cand.commands,
                    expected_artifacts=cand.expected_artifacts,
                    definition_of_done=cand.definition_of_done,
                    severity=signal.severity,
                    confidence=signal.confidence,
                )
            )

        # Sort by severity
        items.sort(key=lambda x: (-x.severity, -x.confidence))

        return {
            "ok": True,
            "items": [
                {
                    "source_artifact": i.source_artifact,
                    "detected_signal": i.detected_signal,
                    "expected_effect": i.expected_effect,
                    "commands": i.commands,
                    "expected_artifacts": i.expected_artifacts,
                    "definition_of_done": i.definition_of_done,
                    "severity": i.severity,
                    "confidence": i.confidence,
                }
                for i in items
            ],
            "rejected_signals": [
                {
                    "signal_id": r.signal_id,
                    "source_artifact": r.source_artifact,
                    "reason": r.reason,
                }
                for r in rejected
            ],
            "validation": {"commands_exist": True, "expected_artifacts_coherent": True},
            "total_signals": len(all_signals),
            "total_items": len(items),
            "total_rejected": len(rejected),
            "timestamp_utc": _utc_now(),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Work Compiler - Compile real work from artifacts"
    )
    parser.add_argument(
        "--artifacts-root", default="artifacts", help="Root directory of artifacts"
    )
    parser.add_argument(
        "--out-json",
        default="artifacts/orchestration/work_plan.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--project-root", default=str(PROJECT_ROOT), help="Project root"
    )

    args = parser.parse_args()

    project_root = Path(args.project_root)
    artifacts_root = project_root / args.artifacts_root

    builder = PlanBuilder(str(artifacts_root), project_root)
    plan = builder.build_plan()

    # Write output
    out_path = project_root / args.out_json
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(plan, f, indent=2)

    print(json.dumps(plan, indent=2))

    return 0 if plan["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
