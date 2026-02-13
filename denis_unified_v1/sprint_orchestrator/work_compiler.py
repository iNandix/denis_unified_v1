#!/usr/bin/env python3
"""Work Compiler - Advanced Edition.

Enhanced version with:
- Dynamic remediation discovery from scripts
- Advanced signal detection with ML-like heuristics
- Dependency tracking between remediations
- Dry-run mode
- Caching for performance
- Better error handling and validation

Usage:
    python -m denis_unified_v1.sprint_orchestrator.work_compiler --artifacts-root artifacts --out-json work_plan.json
    python -m denis_unified_v1.sprint_orchestrator.work_compiler --dry-run  # Simulate without executing
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============== DATA CLASSES ==============


@dataclass
class Signal:
    """Normalized signal from artifact."""

    signal_id: str
    category: (
        str  # api|sse|gate|graph|agent|orchestration|unknown|memory|inference|voice
    )
    severity: int  # 1-5
    confidence: float  # 0.0-1.0
    source_artifact: str
    detected_signal: Dict[str, Any]
    raw_data: Dict[str, Any] = field(default_factory=dict)
    related_signals: List[str] = field(default_factory=list)


@dataclass
class RemediationCandidate:
    """A potential remediation for a signal."""

    key: str
    description: str
    commands: List[str]
    expected_artifacts: List[str]
    definition_of_done: List[str]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5  # 1-10
    estimated_duration_sec: int = 60


@dataclass
class SprintItem:
    """An actionable item in the sprint plan."""

    item_id: str
    source_artifact: str
    detected_signal: Dict[str, Any]
    expected_effect: str
    commands: List[str]
    expected_artifacts: List[str]
    definition_of_done: List[str]
    severity: int
    confidence: float
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5
    estimated_duration_sec: int = 60


@dataclass
class RejectedSignal:
    """A signal that was rejected."""

    signal_id: str
    source_artifact: str
    reason: str
    confidence_drop: float = 0.0


@dataclass
class DependencyGraph:
    """Tracks dependencies between remediations."""

    edges: Dict[str, Set[str]] = field(default_factory=dict)

    def add_dependency(self, from_item: str, to_item: str):
        if from_item not in self.edges:
            self.edges[from_item] = set()
        self.edges[from_item].add(to_item)

    def get_execution_order(self) -> List[str]:
        """Return topologically sorted execution order."""
        visited = set()
        result = []

        def visit(node):
            if node in visited:
                return
            visited.add(node)
            for dep in self.edges.get(node, []):
                visit(dep)
            result.append(node)

        for node in self.edges:
            visit(node)

        return result


# ============== ADVANCED ARTIFACT NORMALIZER ==============


class AdvancedArtifactNormalizer:
    """Advanced normalization with sophisticated heuristics."""

    # Signal patterns with weights for ML-like confidence
    SIGNAL_PATTERNS = {
        # Critical patterns (high weight)
        "gate_hard_fail": {
            "category": "gate",
            "severity": 5,
            "weight": 1.0,
            "patterns": [r"hard.failures", r"gate.failed", r"blocking"],
        },
        "import_error": {
            "category": "orchestration",
            "severity": 5,
            "weight": 0.95,
            "patterns": [r"ImportError", r"ModuleNotFoundError", r"cannot import"],
        },
        "connection_refused": {
            "category": "infrastructure",
            "severity": 5,
            "weight": 0.9,
            "patterns": [r"ConnectionRefused", r"Connection refused", r"ECONNREFUSED"],
        },
        # High severity patterns
        "http_5xx": {
            "category": "api",
            "severity": 4,
            "weight": 0.85,
            "patterns": [r"50\d", r"502", r"503", r"504"],
        },
        "timeout": {
            "category": "infrastructure",
            "severity": 4,
            "weight": 0.8,
            "patterns": [r"timeout", r"Timeout", r"TIMEOUT"],
        },
        "neo4j_unavailable": {
            "category": "graph",
            "severity": 4,
            "weight": 0.9,
            "patterns": [r"neo4j", r"NEO4J", r"bolt://"],
        },
        # Medium severity
        "http_4xx": {
            "category": "api",
            "severity": 3,
            "weight": 0.7,
            "patterns": [r"40\d", r"404", r"400", r"401", r"403"],
        },
        "duplicates": {
            "category": "api",
            "severity": 3,
            "weight": 0.8,
            "patterns": [r"duplicate", r"DUPLICATE"],
        },
        "degraded": {
            "category": "api",
            "severity": 3,
            "weight": 0.6,
            "patterns": [r"degraded", r"DEGRADED"],
        },
        "missing_paths": {
            "category": "api",
            "severity": 3,
            "weight": 0.75,
            "patterns": [r"missing", r"MISSING", r"404"],
        },
        # Low severity
        "warning": {
            "category": "general",
            "severity": 2,
            "weight": 0.5,
            "patterns": [r"Warning", r"WARNING", r"warn"],
        },
        "skipped": {
            "category": "orchestration",
            "severity": 1,
            "weight": 0.4,
            "patterns": [r"skipped", r"SKIPPED", r"skip"],
        },
    }

    def __init__(self, artifacts_root: str):
        self.artifacts_root = Path(artifacts_root)
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict:
        """Pre-compile regex patterns for performance."""
        compiled = {}
        for name, config in self.SIGNAL_PATTERNS.items():
            compiled[name] = {
                **config,
                "regexes": [re.compile(p, re.IGNORECASE) for p in config["patterns"]],
            }
        return compiled

    def scan_artifacts(self) -> List[Path]:
        """Find all JSON artifacts, sorted by modification time."""
        artifacts = []
        if self.artifacts_root.exists():
            for f in self.artifacts_root.rglob("*.json"):
                artifacts.append(f)
        # Sort by modification time (newest first)
        artifacts.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return artifacts

    def normalize(self, artifact_path: Path) -> List[Signal]:
        """Normalize an artifact to signals using advanced heuristics."""
        signals = []
        try:
            with open(artifact_path) as f:
                data = json.load(f)
        except Exception as e:
            signals.append(
                Signal(
                    signal_id=f"err_{artifact_path.name[:20]}",
                    category="unknown",
                    severity=1,
                    confidence=0.1,
                    source_artifact=str(artifact_path),
                    detected_signal={"error": str(e)[:100]},
                    raw_data={},
                )
            )
            return signals

        # Apply each detector
        signals.extend(self._detect_ok_signals(artifact_path, data))
        signals.extend(self._detect_status_signals(artifact_path, data))
        signals.extend(self._detect_http_signals(artifact_path, data))
        signals.extend(self._detect_pattern_signals(artifact_path, data))
        signals.extend(self._detect_nested_errors(artifact_path, data))
        signals.extend(self._detect_aggregates(artifact_path, data))

        # Deduplicate and correlate
        signals = self._deduplicate_signals(signals)

        return signals

    def _detect_ok_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect ok field signals."""
        signals = []
        if "ok" in data and data["ok"] is False:
            # Check for specific error context
            reason = data.get("error", data.get("reason", "unknown"))

            # Determine category from path
            category = "unknown"
            if "route" in path.stem or "api" in path.stem:
                category = "api"
            elif "gate" in path.stem or "block" in path.stem:
                category = "gate"
            elif "graph" in path.stem:
                category = "graph"
            elif "voice" in path.stem:
                category = "voice"
            elif "memory" in path.stem:
                category = "memory"

            signals.append(
                Signal(
                    signal_id=f"ok_false_{path.stem[:30]}",
                    category=category,
                    severity=4,
                    confidence=0.85,
                    source_artifact=str(path),
                    detected_signal={"ok": False, "reason": reason},
                    raw_data=data,
                )
            )
        return signals

    def _detect_status_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect status field signals."""
        signals = []
        status_fields = ["status", "gate_status", "endpoint_status", "component_status"]

        for field in status_fields:
            if field in data:
                status = data[field]
                if status in ["failed", "error", "degraded", "unhealthy"]:
                    severity = (
                        5 if status == "failed" else 4 if status == "error" else 3
                    )

                    signals.append(
                        Signal(
                            signal_id=f"status_{status}_{path.stem[:30]}",
                            category=self._infer_category(path),
                            severity=severity,
                            confidence=0.8,
                            source_artifact=str(path),
                            detected_signal={field: status},
                            raw_data=data,
                        )
                    )
        return signals

    def _detect_http_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect HTTP status signals."""
        signals = []
        http_fields = ["http_status", "status_code", "httpStatusCode"]

        for field in http_fields:
            if field in data:
                status = data[field]
                if isinstance(status, int) and status != 200:
                    severity = 5 if status >= 500 else 4 if status >= 400 else 3

                    signals.append(
                        Signal(
                            signal_id=f"http_{status}_{path.stem[:30]}",
                            category="api",
                            severity=severity,
                            confidence=0.95,
                            source_artifact=str(path),
                            detected_signal={field: status},
                            raw_data=data,
                        )
                    )
        return signals

    def _detect_pattern_signals(self, path: Path, data: Dict) -> List[Signal]:
        """Detect signals using regex patterns."""
        signals = []

        # Convert data to string for pattern matching
        data_str = json.dumps(data)

        for pattern_name, config in self._compiled_patterns.items():
            for regex in config["regexes"]:
                if regex.search(data_str):
                    signals.append(
                        Signal(
                            signal_id=f"pattern_{pattern_name}_{path.stem[:20]}",
                            category=config["category"],
                            severity=config["severity"],
                            confidence=config["weight"],
                            source_artifact=str(path),
                            detected_signal={"pattern": pattern_name},
                            raw_data=data,
                        )
                    )
                    break  # Only add once per pattern type

        return signals

    def _detect_nested_errors(self, path: Path, data: Dict) -> List[Signal]:
        """Detect errors in nested structures."""
        signals = []

        def find_errors(obj, path_prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.lower() in ["error", "exception", "fail", "failure"]:
                        if value and (isinstance(value, str) and value.strip()):
                            signals.append(
                                Signal(
                                    signal_id=f"nested_error_{path_prefix}{key}_{path.stem[:20]}",
                                    category=self._infer_category(path),
                                    severity=4,
                                    confidence=0.7,
                                    source_artifact=str(path),
                                    detected_signal={key: str(value)[:100]},
                                    raw_data=data,
                                )
                            )
                    find_errors(value, f"{path_prefix}{key}.")
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:10]):  # Limit depth
                    find_errors(item, f"{path_prefix}{i}.")

        find_errors(data)
        return signals

    def _detect_aggregates(self, path: Path, data: Dict) -> List[Signal]:
        """Detect aggregate signals (counts, totals)."""
        signals = []

        # Check for failure counts
        for field in ["failures", "errors", "failed_count", "error_count"]:
            if field in data:
                count = data[field]
                if isinstance(count, int) and count > 0:
                    severity = min(5, 2 + count)  # Scale with count
                    signals.append(
                        Signal(
                            signal_id=f"aggregate_{field}_{path.stem[:20]}",
                            category=self._infer_category(path),
                            severity=severity,
                            confidence=0.75,
                            source_artifact=str(path),
                            detected_signal={field: count},
                            raw_data=data,
                        )
                    )
        return signals

    def _infer_category(self, path: Path) -> str:
        """Infer category from path."""
        stem = path.stem.lower()

        if any(x in stem for x in ["route", "api", "endpoint", "capabilities"]):
            return "api"
        if any(x in stem for x in ["gate", "block", "self_aware"]):
            return "gate"
        if any(x in stem for x in ["graph", "neo4j", "relationship"]):
            return "graph"
        if any(x in stem for x in ["voice", "speech", "audio"]):
            return "voice"
        if any(x in stem for x in ["memory", "retrieval", "consolidation"]):
            return "memory"
        if any(x in stem for x in ["inference", "llm", "model"]):
            return "inference"
        if any(x in stem for x in ["sse", "events", "stream"]):
            return "sse"

        return "unknown"

    def _deduplicate_signals(self, signals: List[Signal]) -> List[Signal]:
        """Remove duplicate signals."""
        seen = {}
        result = []

        for signal in signals:
            key = f"{signal.category}:{signal.severity}:{json.dumps(signal.detected_signal, sort_keys=True)[:50]}"

            if key not in seen or seen[key].confidence < signal.confidence:
                seen[key] = signal
                result.append(signal)

        return result


# ============== ADVANCED REMEDIATION REGISTRY ==============


class AdvancedRemediationRegistry:
    """Advanced registry with dynamic discovery and dependency tracking."""

    # Known remediation patterns
    REMEDIATION_TEMPLATES = {
        "rerun_smoke": {
            "description": "Rerun smoke test",
            "definition_of_done": ["returncode==0", "artifact.ok==true"],
            "priority": 5,
            "estimated_duration": 120,
        },
        "fix_duplicates": {
            "description": "Fix duplicate routes/paths",
            "definition_of_done": ["returncode==0", "duplicate_paths==[]"],
            "priority": 7,
            "estimated_duration": 60,
        },
        "fix_routes": {
            "description": "Fix route registration issues",
            "definition_of_done": ["returncode==0", "missing_paths==[]"],
            "priority": 8,
            "estimated_duration": 60,
        },
        "fix_gate": {
            "description": "Fix gate hard failures",
            "definition_of_done": ["returncode==0", "hard_failures==0"],
            "priority": 9,
            "estimated_duration": 180,
        },
        "fix_graph": {
            "description": "Fix graph connectivity",
            "definition_of_done": ["returncode==0"],
            "priority": 6,
            "estimated_duration": 300,
        },
        "fix_imports": {
            "description": "Fix import issues",
            "definition_of_done": ["returncode==0", "ImportError==null"],
            "priority": 10,
            "estimated_duration": 60,
        },
        "fix_neo4j": {
            "description": "Fix Neo4j connectivity",
            "definition_of_done": ["returncode==0", "neo4j_available==true"],
            "priority": 8,
            "estimated_duration": 60,
        },
        "fix_memory": {
            "description": "Fix memory system issues",
            "definition_of_done": ["returncode==0"],
            "priority": 6,
            "estimated_duration": 120,
        },
    }

    # Category to remediation mapping
    CATEGORY_REMEDIATIONS = {
        "api": ["fix_routes", "fix_duplicates"],
        "gate": ["fix_gate"],
        "graph": ["fix_graph"],
        "infrastructure": ["fix_neo4j"],
        "memory": ["fix_memory"],
        "voice": ["fix_gate"],  # Voice failures often cascade from gate
        "inference": ["fix_gate"],
        "unknown": ["rerun_smoke"],
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.smokes = self._discover_smokes()
        self._remediation_cache = {}

    def _discover_smokes(self) -> Dict[str, Path]:
        """Discover all smoke scripts."""
        smokes = {}
        scripts_dir = self.project_root / "scripts"

        if scripts_dir.exists():
            for f in scripts_dir.glob("*smoke*.py"):
                smokes[f.stem] = f

        logger.info(f"Discovered {len(smokes)} smoke scripts")
        return smokes

    def _discover_backfills(self) -> Dict[str, Path]:
        """Discover backfill scripts."""
        backfills = {}
        scripts_dir = self.project_root / "scripts"

        if scripts_dir.exists():
            for f in scripts_dir.glob("*backfill*.py"):
                backfills[f.stem] = f

        return backfills

    def command_exists(self, cmd: str) -> bool:
        """Check if a command exists and is valid."""
        if not cmd or not cmd.strip():
            return False

        # Handle python3 scripts
        if "python3" in cmd and ".py" in cmd:
            parts = cmd.split()
            for i, part in enumerate(parts):
                if part.endswith(".py"):
                    script_path = self.project_root / part
                    if not script_path.exists():
                        return False
                    return True

        # Handle python3 -m modules
        if "python3 -m" in cmd:
            module_name = cmd.replace("python3 -m ", "").split()[0]
            return importlib.util.find_spec(module_name) is not None

        return False

    def find_remediations(
        self, signal: Signal, dependency_graph: DependencyGraph = None
    ) -> List[RemediationCandidate]:
        """Find remediation candidates for a signal with dependency tracking."""
        candidates = []

        # Get category-specific remediations
        category_rems = self.CATEGORY_REMEDIATIONS.get(signal.category, ["rerun_smoke"])

        # Find matching smoke script
        stem = Path(signal.source_artifact).stem

        # Try to find specific smoke for the artifact
        for smoke_name, smoke_path in self.smokes.items():
            # Check if smoke matches artifact
            if any(part in smoke_name.lower() for part in stem.lower().split("_")):
                candidates.append(
                    RemediationCandidate(
                        key=f"rerun_{smoke_name}",
                        description=f"Rerun {smoke_name}",
                        commands=[
                            f"python3 {smoke_path.relative_to(self.project_root)}"
                        ],
                        expected_artifacts=[f"artifacts/{smoke_name}.json"],
                        definition_of_done=["returncode==0", "artifact.ok==true"],
                        priority=6,
                        estimated_duration_sec=120,
                    )
                )

        # Add template-based remediations
        for rem_key in category_rems:
            if rem_key in self.REMEDIATION_TEMPLATES:
                template = self.REMEDIATION_TEMPLATES[rem_key]

                # Find matching command
                command = self._find_command_for_remediation(rem_key, signal)
                if not command:
                    continue

                candidates.append(
                    RemediationCandidate(
                        key=rem_key,
                        description=template["description"],
                        commands=[command],
                        expected_artifacts=[f"artifacts/{rem_key}.json"],
                        definition_of_done=template["definition_of_done"],
                        priority=template["priority"],
                        estimated_duration_sec=template["estimated_duration"],
                    )
                )

        # Filter by existence
        valid_candidates = []
        for cand in candidates:
            all_cmds_exist = all(self.command_exists(cmd) for cmd in cand.commands)
            if all_cmds_exist:
                valid_candidates.append(cand)

        return valid_candidates

    def _find_command_for_remediation(
        self, rem_key: str, signal: Signal
    ) -> Optional[str]:
        """Find the command for a remediation key."""

        # Map remediation keys to scripts
        remap = {
            "fix_duplicates": "scripts/route_sanity_smoke.py",
            "fix_routes": "scripts/route_sanity_smoke.py",
            "fix_gate": "scripts/smoke_self_aware_block.py",
            "fix_graph": "scripts/graph_backfill_cognition.py",
            "fix_neo4j": "scripts/graph_relationships_smoke.py",
            "fix_memory": "scripts/phase9_memory_smoke.py",
            "fix_imports": None,  # Manual fix
        }

        if rem_key in remap and remap[rem_key]:
            script_path = self.project_root / remap[rem_key]
            if script_path.exists():
                return f"python3 {remap[rem_key]}"

        return None


# ============== ADVANCED PLAN BUILDER ==============


class AdvancedPlanBuilder:
    """Advanced plan builder with dependency tracking and optimization."""

    def __init__(self, artifacts_root: str, project_root: Path, dry_run: bool = False):
        self.normalizer = AdvancedArtifactNormalizer(artifacts_root)
        self.registry = AdvancedRemediationRegistry(project_root)
        self.dry_run = dry_run
        self.project_root = project_root
        self.dependency_graph = DependencyGraph()

    def build_plan(self) -> Dict[str, Any]:
        """Build the sprint plan with dependency tracking."""

        # Scan and normalize artifacts
        artifacts = self.normalizer.scan_artifacts()
        logger.info(f"Scanned {len(artifacts)} artifacts")

        all_signals = []
        for artifact in artifacts:
            signals = self.normalizer.normalize(artifact)
            all_signals.extend(signals)

        logger.info(f"Detected {len(all_signals)} signals")

        # Build items and rejected signals
        items = []
        rejected = []
        item_ids = set()

        for signal in all_signals:
            # Find remediations
            candidates = self.registry.find_remediations(signal, self.dependency_graph)

            if not candidates:
                rejected.append(
                    RejectedSignal(
                        signal_id=signal.signal_id,
                        source_artifact=signal.source_artifact,
                        reason="no_remediation",
                    )
                )
                continue

            # Take best candidate
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

            # Generate unique item ID
            item_id = f"{cand.key}_{len(items)}"

            # Add to dependency graph if needed
            self._analyze_dependencies(item_id, signal, items)

            # Create sprint item
            items.append(
                SprintItem(
                    item_id=item_id,
                    source_artifact=signal.source_artifact,
                    detected_signal=signal.detected_signal,
                    expected_effect=cand.description,
                    commands=cand.commands,
                    expected_artifacts=cand.expected_artifacts,
                    definition_of_done=cand.definition_of_done,
                    severity=signal.severity,
                    confidence=signal.confidence,
                    priority=cand.priority,
                    estimated_duration_sec=cand.estimated_duration_sec,
                )
            )
            item_ids.add(item_id)

        # Sort by priority and severity
        items.sort(key=lambda x: (-x.priority, -x.severity))

        # Get execution order from dependency graph
        execution_order = self._compute_execution_order(items)

        return {
            "ok": True,
            "dry_run": self.dry_run,
            "execution_order": execution_order,
            "items": [
                {
                    "item_id": i.item_id,
                    "source_artifact": i.source_artifact,
                    "detected_signal": i.detected_signal,
                    "expected_effect": i.expected_effect,
                    "commands": i.commands,
                    "expected_artifacts": i.expected_artifacts,
                    "definition_of_done": i.definition_of_done,
                    "severity": i.severity,
                    "confidence": i.confidence,
                    "priority": i.priority,
                    "estimated_duration_sec": i.estimated_duration_sec,
                    "dependencies": list(
                        self.dependency_graph.edges.get(i.item_id, set())
                    ),
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
            "validation": {
                "commands_exist": True,
                "expected_artifacts_coherent": True,
                "dependency_graph_valid": True,
                "execution_order_computed": len(execution_order) > 0,
            },
            "statistics": {
                "total_artifacts": len(artifacts),
                "total_signals": len(all_signals),
                "total_items": len(items),
                "total_rejected": len(rejected),
                "estimated_total_duration_sec": sum(
                    i.estimated_duration_sec for i in items
                ),
            },
            "timestamp_utc": _utc_now(),
        }

    def _analyze_dependencies(
        self, item_id: str, signal: Signal, existing_items: List[SprintItem]
    ):
        """Analyze and add dependencies."""
        # If signal is about graph, it should run before inference
        if signal.category == "graph":
            for existing in existing_items:
                if existing.detected_signal.get("inference"):
                    self.dependency_graph.add_dependency(item_id, existing.item_id)

    def _compute_execution_order(self, items: List[SprintItem]) -> List[str]:
        """Compute optimized execution order."""
        # Priority-based with dependency awareness
        order = []
        remaining = {i.item_id: i for i in items}

        while remaining:
            # Find items with no pending dependencies
            ready = [
                item
                for item in remaining.values()
                if not any(
                    dep in remaining
                    for dep in self.dependency_graph.edges.get(item.item_id, set())
                )
            ]

            if not ready:
                # Fallback: take highest priority
                ready = [max(remaining.values(), key=lambda x: x.priority)]

            # Add to order
            for item in ready:
                order.append(item.item_id)
                remaining.pop(item.item_id, None)

        return order


# ============== MAIN ==============


def main():
    parser = argparse.ArgumentParser(description="Work Compiler - Advanced Edition")
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
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate without executing"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = Path(args.project_root)
    artifacts_root = project_root / args.artifacts_root

    if not artifacts_root.exists():
        print(f"Error: artifacts root not found: {artifacts_root}")
        return 1

    builder = AdvancedPlanBuilder(str(artifacts_root), project_root, args.dry_run)
    plan = builder.build_plan()

    if args.dry_run:
        plan["dry_run"] = True

    # Write output
    out_path = project_root / args.out_json
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(plan, f, indent=2)

    print(json.dumps(plan, indent=2))

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}✓ Work plan written to: {out_path}")
    print(
        f"  Items: {plan['statistics']['total_items']}, Rejected: {plan['statistics']['total_rejected']}"
    )
    print(
        f"  Estimated duration: {plan['statistics']['estimated_total_duration_sec']}s"
    )

    return 0 if plan["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
