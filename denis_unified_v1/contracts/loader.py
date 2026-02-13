"""Contract loader with fail-open behavior for Level 3 metacognitive contracts.

This module loads contracts from registry.yaml when present, and falls back to
individual files (e.g., level3_metacognitive.yaml). It is tolerant to missing
files and returns structured diagnostics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import yaml


def _project_root(scan_root: str | None = None) -> Path:
    if scan_root:
        return Path(scan_root).resolve()
    return Path(__file__).resolve().parents[2]


def _contracts_dir(root: Path) -> Path:
    # loader.py lives in denis_unified_v1/contracts, so root/"contracts" exists
    return root / "contracts"


def _load_yaml(path: Path, errors: list[str]) -> Dict[str, Any]:
    try:
        with path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"failed to load {path}: {exc}")
        return {}


def load_contracts(scan_root: str | None = None) -> Dict[str, Any]:
    root = _project_root(scan_root)
    contracts_dir = _contracts_dir(root)

    status = "ok"
    errors: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []
    contracts: Dict[str, Dict[str, Any]] = {}

    registry_path = contracts_dir / "registry.yaml"
    entries: list[Dict[str, Any]] = []

    if registry_path.exists():
        registry = _load_yaml(registry_path, errors)
        entries = registry.get("contracts", []) if isinstance(registry, dict) else []
        if not entries:
            warnings.append("registry.yaml has no contracts entries")
    else:
        warnings.append("registry.yaml not found; falling back to level3_metacognitive.yaml")

    # If no registry entries, fallback to explicit metacognitive file
    if not entries:
        fallback = contracts_dir / "level3_metacognitive.yaml"
        if fallback.exists():
            entries = [{"id": "level3_metacognitive_fallback", "file": fallback.name}]
        else:
            skipped.append("level3_metacognitive.yaml missing")
            status = "skipped_dependency"
            return {
                "contracts": contracts,
                "errors": errors,
                "warnings": warnings,
                "skipped": skipped,
                "status": status,
                "root": str(root),
            }

    for entry in entries:
        file_name = entry.get("file") if isinstance(entry, dict) else None
        contract_id = entry.get("id") if isinstance(entry, dict) else None
        if not file_name:
            warnings.append(f"entry without file: {entry}")
            continue
        path = contracts_dir / file_name
        if not path.exists():
            skipped.append(f"missing {file_name}")
            continue
        data = _load_yaml(path, errors)
        if not isinstance(data, dict):
            warnings.append(f"invalid data in {file_name}")
            continue
        for contract in data.get("contracts", []) if isinstance(data.get("contracts", []), list) else []:
            cid = contract.get("id") or contract_id or file_name
            contracts[str(cid)] = contract

    if errors:
        status = "error"
    elif skipped:
        status = "degraded" if contracts else "skipped_dependency"
    elif warnings:
        status = "degraded"

    return {
        "contracts": contracts,
        "errors": errors,
        "warnings": warnings,
        "skipped": skipped,
        "status": status,
        "root": str(root),
    }
