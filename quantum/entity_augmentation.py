"""Phase-1 Neo4j quantum augmentation and rollback (idempotent)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "config" / "quantum_mapping.yaml"

_SAFE_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DEFAULT_DIMENSIONS = {
    "intentional": 0.5,
    "emotional": 0.0,
    "contextual": 0.5,
    "historical_coherence": 0.8,
}

_QUANTUM_PROPS = [
    "cognitive_state",
    "cognitive_dimensions",
    "amplitude",
    "phase",
    "last_propagation",
    "last_augmented",
]


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str


def resolve_neo4j_config() -> Neo4jConfig:
    uri = (os.getenv("NEO4J_URI") or "bolt://10.10.10.1:7687").strip()
    user = (os.getenv("NEO4J_USER") or "neo4j").strip()
    password = (os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or "").strip()
    return Neo4jConfig(uri=uri, user=user, password=password)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(level: str, event: str, **payload: Any) -> None:
    record = {
        "ts_utc": _utc_now(),
        "level": level,
        "event": event,
        **payload,
    }
    print(json.dumps(record, sort_keys=True))


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(raw)
    except ModuleNotFoundError:
        loaded = json.loads(raw)

    if not isinstance(loaded, dict):
        raise ValueError("quantum mapping must be a dict")
    default_dims = loaded.get("default_dimensions") or _DEFAULT_DIMENSIONS
    overrides = loaded.get("label_overrides") or {}
    if not isinstance(default_dims, dict):
        raise ValueError("default_dimensions must be a dict")
    if not isinstance(overrides, dict):
        raise ValueError("label_overrides must be a dict")
    return {
        "default_dimensions": default_dims,
        "label_overrides": overrides,
    }


def _safe_label(label: str) -> str:
    if not _SAFE_LABEL.match(label):
        raise ValueError(f"Unsafe label in mapping: {label}")
    return label


def _new_result(status: str, action: str) -> dict[str, Any]:
    return {"status": status, "action": action, "steps": []}


def _record_step(result: dict[str, Any], name: str, details: dict[str, Any]) -> None:
    result["steps"].append({"step": name, **details})


def _driver_from_config(cfg: Neo4jConfig):
    if not cfg.password:
        raise ValueError(
            "Missing Neo4j password. Set NEO4J_PASSWORD or NEO4J_PASS before execute mode."
        )
    return GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))


def _read_label_distribution(session) -> list[dict[str, Any]]:
    query = """
    MATCH (n)
    UNWIND labels(n) AS label
    RETURN label, count(*) AS cnt
    ORDER BY cnt DESC
    """
    rows = session.run(query).data()
    return [{"label": r["label"], "count": r["cnt"]} for r in rows]


def _ensure_index_for_labels(session, labels: list[str]) -> list[str]:
    queries: list[str] = []
    for label in labels:
        safe_label = _safe_label(label)
        index_name = f"cognitive_amplitude_{safe_label.lower()}"
        query = (
            f"CREATE INDEX {index_name} IF NOT EXISTS "
            f"FOR (n:{safe_label}) ON (n.amplitude)"
        )
        session.run(query).consume()
        queries.append(query)
    return queries


def _augment_global(session) -> dict[str, int]:
    changed: dict[str, int] = {}
    queries = {
        "cognitive_state": """
            MATCH (n)
            WHERE n.cognitive_state IS NULL
            SET n.cognitive_state = '{}'
            RETURN count(n) AS cnt
        """,
        "amplitude": """
            MATCH (n)
            WHERE n.amplitude IS NULL
            SET n.amplitude = 1.0
            RETURN count(n) AS cnt
        """,
        "phase": """
            MATCH (n)
            WHERE n.phase IS NULL
            SET n.phase = 0.0
            RETURN count(n) AS cnt
        """,
        "last_propagation": """
            MATCH (n)
            WHERE n.last_propagation IS NULL
            SET n.last_propagation = NULL
            RETURN count(n) AS cnt
        """,
        "last_augmented": """
            MATCH (n)
            WHERE n.last_augmented IS NULL
            SET n.last_augmented = datetime()
            RETURN count(n) AS cnt
        """,
    }
    for key, query in queries.items():
        row = session.run(query).single()
        changed[key] = int(row["cnt"]) if row else 0
    return changed


def _augment_by_labels(session, mapping: dict[str, Any]) -> list[dict[str, Any]]:
    default_dims = mapping["default_dimensions"]
    overrides = mapping["label_overrides"]
    rows: list[dict[str, Any]] = []
    default_dims_json = json.dumps(default_dims, sort_keys=True, ensure_ascii=True)

    query_default = """
        MATCH (n)
        WHERE n.cognitive_dimensions IS NULL
        SET n.cognitive_dimensions = $dims_json
        RETURN count(n) AS cnt
    """
    default_count = session.run(query_default, dims_json=default_dims_json).single()["cnt"]
    rows.append(
        {
            "target": "__default__",
            "updated_nodes": int(default_count),
            "dims": default_dims,
        }
    )

    for label, dims in overrides.items():
        safe_label = _safe_label(label)
        if not isinstance(dims, dict):
            raise ValueError(f"Invalid dims for label {safe_label}: expected dict")
        query = f"""
            MATCH (n:{safe_label})
            SET n.cognitive_dimensions = $dims_json,
                n.last_augmented = datetime()
            RETURN count(n) AS cnt
        """
        dims_json = json.dumps(dims, sort_keys=True, ensure_ascii=True)
        count = session.run(query, dims_json=dims_json).single()["cnt"]
        rows.append(
            {
                "target": safe_label,
                "updated_nodes": int(count),
                "dims": dims,
            }
        )
    return rows


def _rollback_quantum_props(session) -> dict[str, int]:
    query = """
    MATCH (n)
    WITH n,
         (
            n.cognitive_state IS NOT NULL OR
            n.cognitive_dimensions IS NOT NULL OR
            n.amplitude IS NOT NULL OR
            n.phase IS NOT NULL OR
            n.last_propagation IS NOT NULL OR
            n.last_augmented IS NOT NULL
         ) AS had_quantum
    REMOVE n.cognitive_state, n.cognitive_dimensions, n.amplitude, n.phase, n.last_propagation, n.last_augmented
    RETURN count(n) AS scanned, sum(CASE WHEN had_quantum THEN 1 ELSE 0 END) AS changed
    """
    row = session.run(query).single()
    return {
        "scanned_nodes": int(row["scanned"]) if row else 0,
        "changed_nodes": int(row["changed"]) if row and row["changed"] else 0,
    }


def preview_plan(mapping_path: Path | None = None) -> dict[str, Any]:
    mapping = _load_mapping(mapping_path or DEFAULT_MAPPING_PATH)
    result = _new_result("preview", "augment")
    _record_step(
        result,
        "plan",
        {
            "global_properties": list(_QUANTUM_PROPS),
            "mapping_path": str(mapping_path or DEFAULT_MAPPING_PATH),
            "label_overrides": sorted(mapping["label_overrides"].keys()),
        },
    )
    return result


def run_augmentation(execute: bool, mapping_path: Path | None = None) -> dict[str, Any]:
    cfg = resolve_neo4j_config()
    mapping = _load_mapping(mapping_path or DEFAULT_MAPPING_PATH)

    if not execute:
        result = preview_plan(mapping_path=mapping_path)
        result["neo4j_config"] = {
            "uri": cfg.uri,
            "user": cfg.user,
            "password_set": bool(cfg.password),
        }
        return result

    result = _new_result("success", "augment")
    result["neo4j_config"] = {
        "uri": cfg.uri,
        "user": cfg.user,
        "password_set": bool(cfg.password),
    }

    try:
        driver = _driver_from_config(cfg)
        with driver.session() as session:
            before = _read_label_distribution(session)
            index_queries = _ensure_index_for_labels(
                session, sorted(mapping["label_overrides"].keys())
            )
            changed_global = _augment_global(session)
            changed_by_label = _augment_by_labels(session, mapping)
            after = _read_label_distribution(session)

        _record_step(result, "label_distribution_before", {"rows": before})
        _record_step(result, "index", {"queries": index_queries})
        _record_step(result, "global_augmentation", {"changed": changed_global})
        _record_step(result, "label_augmentation", {"rows": changed_by_label})
        _record_step(result, "label_distribution_after", {"rows": after})
        return result
    except (Neo4jError, ValueError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        try:
            driver.close()  # type: ignore[name-defined]
        except Exception:
            pass


def run_rollback(execute: bool) -> dict[str, Any]:
    cfg = resolve_neo4j_config()
    result = _new_result("success" if execute else "preview", "rollback")
    result["neo4j_config"] = {
        "uri": cfg.uri,
        "user": cfg.user,
        "password_set": bool(cfg.password),
    }

    if not execute:
        _record_step(
            result,
            "plan",
            {"remove_properties": list(_QUANTUM_PROPS), "mode": "dry_run"},
        )
        return result

    try:
        driver = _driver_from_config(cfg)
        with driver.session() as session:
            stats = _rollback_quantum_props(session)
        _record_step(result, "rollback", stats)
        return result
    except (Neo4jError, ValueError) as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result
    finally:
        try:
            driver.close()  # type: ignore[name-defined]
        except Exception:
            pass


def emit_result(result: dict[str, Any]) -> None:
    level = "INFO" if result.get("status") in {"success", "preview"} else "ERROR"
    _log(level, "phase1_quantum_result", result=result)
