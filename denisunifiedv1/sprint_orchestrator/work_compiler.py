"""Work Compiler - Compile executable work plans from artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import importlib.util


class ArtifactNormalizer:
    """Normalize heterogeneous artifacts into standardized signals."""

    def __init__(self):
        self.heuristics = {
            "ok": self._check_ok_field,
            "status_code": self._check_status_code,
            "endpoint_status": self._check_endpoint_status,
            "gate_status": self._check_gate_status,
            "schema_valid": self._check_schema_valid,
        }

    def normalize_artifact(self, artifact_path: Path) -> List[Dict[str, Any]]:
        """Normalize a single artifact into signals."""
        try:
            with artifact_path.open() as f:
                data = json.load(f)
        except Exception as e:
            return [{
                "signal_id": f"{artifact_path.stem}_parse_error",
                "category": "unknown",
                "severity": 1,
                "confidence": 0.1,
                "source_artifact": str(artifact_path),
                "detected_signal": {"reason": f"Failed to parse JSON: {str(e)}"},
            }]

        signals = []
        for field, checker in self.heuristics.items():
            signal = checker(data, artifact_path)
            if signal:
                signals.append(signal)

        # If no signals found, don't emit anything (successful artifacts)
        return signals

    def _check_ok_field(self, data: Dict, artifact_path: Path) -> Optional[Dict]:
        ok = data.get("ok")
        if ok is False:
            return {
                "signal_id": f"{artifact_path.stem}_ok_false",
                "category": self._infer_category(artifact_path),
                "severity": 4,
                "confidence": 0.9,
                "source_artifact": str(artifact_path),
                "detected_signal": {"ok": False, "endpoint_status": data.get("endpoint_status")},
            }
        return None

    def _check_status_code(self, data: Dict, artifact_path: Path) -> Optional[Dict]:
        status_code = data.get("status_code") or data.get("capabilities_endpoint_code")
        if status_code and status_code >= 400:
            return {
                "signal_id": f"{artifact_path.stem}_status_{status_code}",
                "category": self._infer_category(artifact_path),
                "severity": 5 if status_code >= 500 else 3,
                "confidence": 0.95,
                "source_artifact": str(artifact_path),
                "detected_signal": {"status_code": status_code},
            }
        return None

    def _check_endpoint_status(self, data: Dict, artifact_path: Path) -> Optional[Dict]:
        status = data.get("endpoint_status")
        if status and status not in ["success", "ok"]:
            return {
                "signal_id": f"{artifact_path.stem}_endpoint_{status}",
                "category": self._infer_category(artifact_path),
                "severity": 4,
                "confidence": 0.8,
                "source_artifact": str(artifact_path),
                "detected_signal": {"endpoint_status": status},
            }
        return None

    def _check_gate_status(self, data: Dict, artifact_path: Path) -> Optional[Dict]:
        gate_status = data.get("gate_status", {}).get("status")
        if gate_status and gate_status != "healthy":
            return {
                "signal_id": f"{artifact_path.stem}_gate_{gate_status}",
                "category": "gate",
                "severity": 3,
                "confidence": 0.85,
                "source_artifact": str(artifact_path),
                "detected_signal": {"gate_status": gate_status},
            }
        return None

    def _check_schema_valid(self, data: Dict, artifact_path: Path) -> Optional[Dict]:
        schema_valid = data.get("schema_validation", {}).get("schema_valid")
        if schema_valid is False:
            return {
                "signal_id": f"{artifact_path.stem}_schema_invalid",
                "category": "api",
                "severity": 2,
                "confidence": 0.9,
                "source_artifact": str(artifact_path),
                "detected_signal": {"schema_validation": data.get("schema_validation")},
            }
        return None

    def _infer_category(self, artifact_path: Path) -> str:
        name = artifact_path.stem.lower()
        if "api" in name or "capabilities" in name:
            return "api"
        elif "gate" in name:
            return "gate"
        elif "inference" in name:
            return "inference"
        elif "agent" in name:
            return "agent"
        elif "orchestration" in name:
            return "orchestration"
        elif "graph" in name:
            return "graph"
        else:
            return "unknown"


class RemediationRegistry:
    """Registry of known remediations with existence validation."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.smokes = self.discover_smokes()
        self.known_remediations = self._build_remediations()

    def discover_smokes(self, scripts_root: str = "scripts") -> Dict[str, Path]:
        """Discover available smoke test scripts."""
        scripts_dir = self.root_dir / scripts_root
        smokes = {}
        if scripts_dir.exists():
            for script in scripts_dir.glob("*smoke*.py"):
                # Extract component name from filename
                stem = script.stem.lower()
                if "capabilities" in stem:
                    name = "capabilities"
                elif "api" in stem and "capabilities" not in stem:
                    name = "api"
                elif "gate" in stem:
                    name = "gate"
                elif "inference" in stem:
                    name = "inference"
                elif "memory" in stem:
                    name = "memory"
                elif "voice" in stem:
                    name = "voice"
                elif "orchestration" in stem:
                    name = "orchestration"
                elif "self" in stem and "model" in stem:
                    name = "selfmodel"
                else:
                    continue  # Skip unknown
                smokes[name] = script
        return smokes

    def command_exists(self, cmd_tokens: List[str]) -> bool:
        """Check if a command exists and is executable."""
        if not cmd_tokens:
            return False

        cmd = cmd_tokens[0]
        if cmd == "python3":
            if len(cmd_tokens) > 1:
                target = cmd_tokens[1]
                if target.startswith("-m"):
                    # python3 -m module
                    module = cmd_tokens[2] if len(cmd_tokens) > 2 else ""
                    return importlib.util.find_spec(module) is not None
                else:
                    # python3 path.py
                    path = Path(target)
                    return path.exists() and path.is_file()
        elif cmd == "bash":
            # Only allow specific bash commands
            return False  # For safety, disable bash commands
        return False

    def _build_remediations(self) -> Dict[str, Dict[str, Any]]:
        """Build remediation mappings."""
        remediations = {}

        # Pattern-based mappings
        smoke_mappings = {
            "capabilities": "capabilities",
            "api": "api",
            "gate": "gate",
            "inference": "inference",
            "memory": "memory",
            "voice": "voice",
            "orchestration": "orchestration",
            "selfmodel": "selfmodel",
        }

        for component, smoke_key in smoke_mappings.items():
            if smoke_key in self.smokes:
                script_path = self.smokes[smoke_key]
                artifact_name = f"artifacts/phase{smoke_key.replace('registry', '')}_smoke.json"
                if component == "capabilities":
                    artifact_name = "artifacts/api/phase6_capabilities_registry_smoke.json"

                remediations[f"{component}_endpoint_failed"] = {
                    "commands": [
                        ["python3", str(script_path), "--out-json", artifact_name]
                    ],
                    "expected_artifacts": [artifact_name],
                    "expected_effect": f"{component} endpoint returns 200 with valid response",
                }

        return remediations

    def find_remediation(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """Find remediation for a signal ID using pattern matching."""
        # Direct match
        if signal_id in self.known_remediations:
            return self.known_remediations[signal_id]

        # Pattern matching
        signal_lower = signal_id.lower()
        for key, remediation in self.known_remediations.items():
            if key.replace("_endpoint_failed", "") in signal_lower:
                return remediation

        return None

    def find_remediation_with_key(self, signal_id: str) -> tuple[str, Dict[str, Any]] | None:
        """Find remediation for a signal ID and return (key, remediation)."""
        # Direct match
        if signal_id in self.known_remediations:
            return signal_id, self.known_remediations[signal_id]

        # Pattern matching
        signal_lower = signal_id.lower()
        for key, remediation in self.known_remediations.items():
            if key.replace("_endpoint_failed", "") in signal_lower:
                return key, remediation

        return None


class PlanBuilder:
    """Build executable sprint plans from normalized signals."""

    def __init__(self, registry: RemediationRegistry):
        self.registry = registry

    def build_plan(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a sprint plan from signals."""
        items = []
        rejected_signals = []

        for signal in signals:
            remediation_result = self.registry.find_remediation_with_key(signal["signal_id"])
            if remediation_result is None:
                rejected_signals.append({
                    **signal,
                    "reason": "no_remediation_found"
                })
                continue

            remediation_key, remediation = remediation_result

            # Validate commands exist
            if not all(self.registry.command_exists(cmd) for cmd in remediation["commands"]):
                rejected_signals.append({
                    **signal,
                    "reason": "commands_missing",
                    "commands": remediation["commands"]
                })
                continue

            # Validate expected artifacts are coherent
            expected_artifacts = remediation["expected_artifacts"]
            if not all(self._is_coherent_artifact(art) for art in expected_artifacts):
                rejected_signals.append({
                    **signal,
                    "reason": "artifacts_incoherent",
                    "expected_artifacts": expected_artifacts
                })
                continue

            # Create sprint item with score
            score = signal["severity"] * signal["confidence"]
            items.append({
                "signal_id": signal["signal_id"],
                "severity": signal["severity"],
                "confidence": signal["confidence"],
                "score": score,
                "source_artifact": signal["source_artifact"],
                "detected_signal": signal["detected_signal"],
                "remediation_key": remediation_key,
                "expected_effect": remediation["expected_effect"],
                "commands": remediation["commands"],
                "expected_artifacts": expected_artifacts,
                "definition_of_done": [
                    "All commands return exit code 0",
                    f"Expected artifacts created and contain success indicators",
                    f"Root cause addressed as per {remediation['expected_effect']}"
                ],
                "generated_at_utc": time.time(),
            })

        # Sort items by score (descending), then by signal_id
        items.sort(key=lambda x: (-x["score"], x["signal_id"]))

        # Dedupe items by (signal_id, source_artifact, remediation_key)
        seen = set()
        deduped_items = []
        for item in items:
            key = (item["signal_id"], item["source_artifact"], item["remediation_key"])
            if key not in seen:
                seen.add(key)
                deduped_items.append(item)

        plan = {
            "ok": True,  # Compilation successful
            "items": deduped_items,
            "rejected_signals": rejected_signals,
            "validation": {
                "commands_exist": True,  # We already validated
                "expected_artifacts_coherent": True,
            },
            "timestamp_utc": time.time(),
            "total_signals": len(signals),
            "accepted_items": len(deduped_items),
            "rejected_signals_count": len(rejected_signals),
        }

        # Add reason if no executable work
        if not deduped_items:
            if signals:
                plan["reason"] = "no_executable_work_found"
            else:
                plan["reason"] = "no_signals_detected"

        return plan

    def _is_coherent_artifact(self, artifact_path: str) -> bool:
        """Check if artifact path is coherent (relative, in artifacts/, etc.)."""
        if artifact_path.startswith("/tmp/") or artifact_path.startswith("/var/"):
            return False
        if not artifact_path.startswith("artifacts/"):
            return False
        # Could add more checks
        return True


def compile_work_from_artifacts(artifacts_root: Path, out_json: Path) -> Dict[str, Any]:
    """Main function to compile work from artifacts."""
    normalizer = ArtifactNormalizer()
    registry = RemediationRegistry(artifacts_root.parent)  # root_dir is project root
    builder = PlanBuilder(registry)

    # Scan artifacts
    artifacts_dir = artifacts_root
    signals = []
    if artifacts_dir.exists():
        for artifact_file in artifacts_dir.glob("*.json"):
            signals.extend(normalizer.normalize_artifact(artifact_file))

    # Build plan
    plan = builder.build_plan(signals)

    # Write output
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w") as f:
        json.dump(plan, f, indent=2)

    return plan
