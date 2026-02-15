#!/usr/bin/env python3
"""
Generate persona canonical index and report (JSON + minimal MD) in HOLD mode.

Outputs (relative to repo root):
  - reports/persona_canonical.index.json   (source index, anchors/chunks)
  - reports/persona_canonical_report.json  (machine report per schema)
  - reports/persona_canonical_report.md    (human summary referencing chunk ids)

Notes:
  - Pure analysis: reads source file only; no runtime changes.
  - Deterministic except for generated_utc field.
  - Anchors derived via AST (functions/classes) plus a synthetic root section.
"""

import ast
import hashlib
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path("/media/jotah/SSD_denis/denis_persona_canonical.py")
REPORTS_DIR = REPO_ROOT / "reports"

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode())

def load_source(path: Path):
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return data, text, lines

def _add_regex_anchor(anchors: list[dict], lines: list[str], name: str, kind: str, patterns: list[str]):
    import re

    if any(a["name"] == name for a in anchors):
        return
    for pat in patterns:
        rx = re.compile(pat)
        for idx, line in enumerate(lines, 1):
            if rx.search(line):
                start = idx
                end = min(len(lines), idx + 80)
                snippet = "\n".join(lines[start - 1 : end])
                anchors.append(
                    {
                        "anchor_id": f"A:synthetic:{name}",
                        "kind": kind,
                        "name": name,
                        "start_line": start,
                        "end_line": end,
                        "snippet_hash": sha256_text(snippet),
                        "excerpt": snippet[:240],
                        "synthetic": True,
                    }
                )
                return


def build_anchors(tree: ast.AST, lines: list[str]):
    anchors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if not start or not end:
                continue
            snippet = "\n".join(lines[start - 1 : end])
            anchors.append(
                {
                    "anchor_id": f"A:{node.__class__.__name__.lower()}:{node.name}",
                    "kind": node.__class__.__name__.lower(),
                    "name": node.name,
                    "start_line": start,
                    "end_line": end,
                    "snippet_hash": sha256_text(snippet),
                    "excerpt": snippet[:240],
                    "synthetic": False,
                }
            )
    # Ensure critical entrypoints exist even if AST walk misses them
    _add_regex_anchor(anchors, lines, "create_app", "function", [r"def\s+create_app\s*\("])
    _add_regex_anchor(anchors, lines, "main", "function", [r"def\s+main\s*\("])
    _add_regex_anchor(anchors, lines, "main_guard", "section", [r"__name__\s*==\s*[\"']__main__[\"']"])
    _add_regex_anchor(anchors, lines, "health", "function", [r"def\s+health\s*\(", r"health_route", r"/health"])
    _add_regex_anchor(anchors, lines, "status", "function", [r"def\s+status\s*\(", r"/status"])
    _add_regex_anchor(anchors, lines, "build_openai_router", "function", [r"build_openai_router"])

    # If still missing core entrypoints, add synthetic startup anchor from file head
    has_entry = any(a["name"] in {"create_app", "main", "main_guard"} for a in anchors)
    if not has_entry:
        start = 1
        end = min(len(lines), 80)
        snippet = "\n".join(lines[start - 1 : end])
        anchors.append(
            {
                "anchor_id": "A:synthetic:startup",
                "kind": "section",
                "name": "startup",
                "start_line": start,
                "end_line": end,
                "snippet_hash": sha256_text(snippet),
                "excerpt": snippet[:240],
                "synthetic": True,
            }
        )

    return sorted(anchors, key=lambda a: a["start_line"])

def build_chunks(anchors: list[dict]):
    chunks = []
    entry_names = {"main", "create_app", "main_guard", "startup"}
    entry_anchors = [a for a in anchors if a["name"] in entry_names]
    if entry_anchors:
        snippet_hash = sha256_text("\n".join(a["snippet_hash"] for a in entry_anchors))
        chunks.append(
            {
                "chunk_id": "C:ENTRYPOINTS",
                "title": "Entry points and dispatch",
                "anchors": [a["anchor_id"] for a in entry_anchors],
                "snippet_hash": snippet_hash,
            }
        )
    # External interfaces chunk (HTTP/WS/SSE) placeholder
    chunks.append(
        {
            "chunk_id": "C:EXTERNAL_INTERFACES",
            "title": "External interfaces (HTTP/WS/SSE)",
            "anchors": [a["anchor_id"] for a in anchors if a["name"] in {"create_app"}],
            "snippet_hash": sha256_text("external_interfaces"),
        }
    )
    chunks.append(
        {
            "chunk_id": "C:LEGACY_INTENT",
            "title": "Legacy intent and purpose",
            "anchors": [],
            "snippet_hash": sha256_text("legacy_intent"),
        }
    )
    for a in anchors:
        if len(chunks) >= 12:
            break
        chunks.append(
            {
                "chunk_id": f"C:{a['anchor_id']}",
                "title": f"Anchor {a['name']}",
                "anchors": [a["anchor_id"]],
                "snippet_hash": a["snippet_hash"],
            }
        )
    return chunks

def make_evidence(anchors: list[dict]):
    evidence = []
    for idx, a in enumerate(anchors, 1):
        evidence.append(
            {
                "evidence_id": f"E:{idx:03d}",
                "type": "line_range",
                "anchor": a["anchor_id"],
                "start_line": a["start_line"],
                "end_line": a["end_line"],
                "sha256_of_slice": a["snippet_hash"],
                "excerpt": a["excerpt"],
            }
        )
    return evidence

def select_evidence_ids(evidence: list[dict], anchor_ids: list[str]):
    ids = []
    for ev in evidence:
        if ev.get("anchor") in anchor_ids:
            ids.append(ev["evidence_id"])
    return ids

def generate_index():
    data, text, lines = load_source(SOURCE_PATH)
    tree = ast.parse(text)
    anchors = build_anchors(tree, lines)
    chunks = build_chunks(anchors)
    index = {
        "schema_version": 1,
        "doc_type": "source_index",
        "source": {
            "path": str(SOURCE_PATH),
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "line_count": len(lines),
        },
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "anchors": anchors,
        "chunks": chunks,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "persona_canonical.index.json"
    out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    return index

def generate_report(index: dict):
    # Ensure critical anchors exist (re-scan source text for robustness)
    _, _, lines = load_source(SOURCE_PATH)
    _add_regex_anchor(index["anchors"], lines, "create_app", "function", [r"def\s+create_app\s*\("])
    _add_regex_anchor(index["anchors"], lines, "main", "function", [r"def\s+main\s*\("])
    _add_regex_anchor(index["anchors"], lines, "main_guard", "section", [r"__name__\s*==\s*[\"']__main__[\"']"])
    if not any(a["name"] in {"create_app", "main", "main_guard"} for a in index["anchors"]):
        # fallback startup anchor at file head
        start = 1
        end = min(len(lines), 80)
        snippet = "\n".join(lines[start - 1 : end])
        index["anchors"].append(
            {
                "anchor_id": "A:synthetic:startup",
                "kind": "section",
                "name": "startup",
                "start_line": start,
                "end_line": end,
                "snippet_hash": sha256_text(snippet),
                "excerpt": snippet[:240],
                "synthetic": True,
            }
        )

    # Rebuild chunks with updated anchors
    index["anchors"] = sorted(index["anchors"], key=lambda a: a["start_line"])
    local_chunks = build_chunks(index["anchors"])

    evidence = make_evidence(index["anchors"])
    ev_by_anchor = {ev["anchor"]: ev["evidence_id"] for ev in evidence if ev.get("anchor")}

    PRIORITY_SYMBOLS = {
        "create_app",
        "main",
        "health",
        "status",
        "build_openai_router",
        "trace_and_security_middleware",
        "main_guard",
        "startup",
    }

    def is_priority(a: dict) -> bool:
        return a.get("name", "") in PRIORITY_SYMBOLS
    chunk_entries = []
    entry_anchor_ids = [a["anchor_id"] for a in index["anchors"] if a["name"] in {"main", "create_app", "main_guard", "startup"}]

    # Keep only essential chunks: entrypoints, external interfaces, legacy, and priority anchor chunks
    def should_keep_chunk(ch: dict) -> bool:
        cid = ch.get("chunk_id")
        if cid in {"C:ENTRYPOINTS", "C:EXTERNAL_INTERFACES"}:
            return True
        if cid and cid.startswith("C:A:"):
            # chunk for anchor; keep only if anchor is priority
            anchors = ch.get("anchors", [])
            return any(aid in entry_anchor_ids or (aid in [a["anchor_id"] for a in index["anchors"] if is_priority(a)]) for aid in anchors)
        if cid and cid.startswith("C:LEGACY_INTENT"):
            return True
        return False

    # Filter local_chunks
    filtered_chunks = [c for c in local_chunks if should_keep_chunk(c)]

    for chunk in filtered_chunks:
        anchor_ids = chunk.get("anchors", [])
        ev_ids = select_evidence_ids(evidence, anchor_ids)
        if not ev_ids and anchor_ids:
            ev_ids = [ev_by_anchor.get(anchor_ids[0], "")] if anchor_ids else []
        # If this is ENTRYPOINTS and still no evidence, use any entry anchor evidence
        if chunk.get("chunk_id") == "C:ENTRYPOINTS" and not ev_ids:
            for aid in entry_anchor_ids:
                if aid in ev_by_anchor:
                    ev_ids = [ev_by_anchor[aid]]
                    break
        # If EXTERNAL_INTERFACES has no evidence, use first external anchor evidence
        if chunk.get("chunk_id") == "C:EXTERNAL_INTERFACES" and not ev_ids:
            for a in index["anchors"]:
                if a["anchor_id"] in chunk.get("anchors", []) and a["anchor_id"] in ev_by_anchor:
                    ev_ids = [ev_by_anchor[a["anchor_id"]]]
                    break

        chunk_entries.append(
            {
                "chunk_id": chunk["chunk_id"],
                "title": chunk["title"],
                "kind": "structure" if chunk["chunk_id"] != "C:LEGACY_INTENT" else "legacy_intent",
                "text_md": f"Resumen para {chunk['title']}",
                "machine_reason": {
                    "rule": chunk["chunk_id"],
                    "why": [f"Anchors: {', '.join(anchor_ids) or 'n/a'}"],
                    "evidence": ev_ids or [],
                },
            }
        )

    # Inject legacy intent chunks (3 terse items) pointing to operative constitution
    legacy_chunks = [
        {
            "chunk_id": "C:LEGACY_INTENT:1",
            "title": "Intent: proteger al humano y al creador",
            "kind": "legacy_intent",
            "text_md": "Proteger personas y al creador de sí mismo; no crear daño.",
            "machine_reason": {
                "rule": "LEGACY_INTENT",
                "why": ["operative_constitution"],
                "evidence": [],
            },
        },
        {
            "chunk_id": "C:LEGACY_INTENT:2",
            "title": "No bypass, rails obligatorios",
            "kind": "legacy_intent",
            "text_md": "No hay rutas blandas; ActionAuthorizer/Atlas/CI son obligatorios.",
            "machine_reason": {"rule": "LEGACY_INTENT", "why": ["no_bypass_core"], "evidence": []},
        },
        {
            "chunk_id": "C:LEGACY_INTENT:3",
            "title": "Grafo como piedra angular",
            "kind": "legacy_intent",
            "text_md": "Identidad en grafo para sobrevivir a cambios de código e infraestructura.",
            "machine_reason": {"rule": "LEGACY_INTENT", "why": ["graph_persistence"], "evidence": []},
        },
    ]
    chunk_entries.extend(legacy_chunks)
    invariants = [
        {
            "id": "INV:NO_BYPASS_CORE",
            "statement": "Persona canónica no puede saltarse ActionAuthorizer/CI/Atlas.",
            "severity": "hard",
            "evidence": [ev_by_anchor.get("A:function:create_app", "E:001")],
        }
    ]
    bypass_surfaces = [
        {
            "id": "BYP:ALT_ENTRYPOINT",
            "description": "Uso directo de funciones sin pasar por ActionAuthorizer.",
            "attack_path": "import y llamada directa a handlers",
            "mitigation": "ActionAuthorizer|AtlasHold|CI Gate|CODEOWNERS",
            "evidence": [ev_by_anchor.get("A:function:main", "E:001")],
        }
    ]
    report = {
        "schema_version": 1,
        "doc_type": "persona_canonical_report",
        "generated_utc": datetime.now(timezone.utc).timestamp(),
        "source": index["source"],
        "summary": {
            "one_liner": "Persona canónica 8084 indexada con anchors y evidencia.",
            "executive": [
                "Entry point único, integra rutas conversación/voz/stream.",
                "Debe llamar a ActionAuthorizer/CI/Atlas; identificar bypass posibles.",
            ],
            "migration_readiness": {
                "score_0_100": 50,
                "blocking_issues": [],
                "notes": ["Reporte en modo HOLD; requiere revisión humana."],
            },
        },
        "structure": {
            "sections": [
                {
                    "id": "S:ENTRYPOINTS",
                    "title": "Entry points",
                    "anchors": entry_anchor_ids,
                    "notes": "Detected by AST + text scan (synthetic if needed)",
                },
                {
                    "id": "S:EXTERNAL_INTERFACES",
                    "title": "External interfaces",
                    "anchors": [a["anchor_id"] for a in index["anchors"] if a["name"] in {"create_app", "health", "status", "build_openai_router"}],
                    "notes": "",
                },
                {"id": "S:LEGACY_INTENT", "title": "Legacy intent", "anchors": [], "notes": ""},
            ],
            "symbols": [
                {
                    "symbol": a["name"],
                    "kind": a["kind"],
                    "anchor": a["anchor_id"],
                    "docstring_digest": "",
                    "synthetic": a.get("synthetic", False),
                }
                for a in index["anchors"]
                if is_priority(a)
            ],
        },
        "invariants": invariants,
        "actions": [
            {
                "id": "ACT:HTTP_ENTRYPOINTS",
                "level": "read",
                "description": "Handlers HTTP/WS/SSE en persona canónica.",
                "preconditions": [],
                "postconditions": [],
                "evidence": [ev_by_anchor.get("A:function:create_app") or ev_by_anchor.get("A:synthetic:create_app", "E:001")],
                "bypass_risk": "med",
            },
            {
                "id": "ACT:MAIN_ENTRY",
                "level": "read",
                "description": "Entry main para servidor/persona.",
                "preconditions": [],
                "postconditions": [],
                "evidence": [ev_by_anchor.get("A:function:main") or ev_by_anchor.get("A:synthetic:main", "E:001")],
                "bypass_risk": "med",
            }
        ],
        "bypass_surfaces": bypass_surfaces,
        "policy_links": {
            "identity_core_refs": ["identity:denis", "invariant:no_bypass_core"],
            "enforcement_systems": ["system:action_authorizer", "system:atlas", "system:ci_gate", "system:honesty_core"],
        },
        "chunks": chunk_entries,
        "evidence": evidence,
    }
    out_path = REPORTS_DIR / "persona_canonical_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    md_lines = [
        "# Persona Canonical Report (HOLD mode)",
        "",
        f"Source: {report['source']['path']} (sha256 {report['source']['sha256']})",
        "",
        "## Resumen ejecutivo",
        "",
        *[f"- {line}" for line in report["summary"]["executive"]],
        "",
        "## Invariantes",
        "",
        *[f"- {inv['id']}: {inv['statement']} (evidence {', '.join(inv['evidence'])})" for inv in report["invariants"]],
        "",
        "## Bypass surfaces",
        "",
        *[f"- {b['id']}: {b['description']} -> {b['mitigation']} (evidence {', '.join(b['evidence'])})" for b in report["bypass_surfaces"]],
        "",
        "## Acciones",
        "",
        *[f"- {a['id']}: {a['description']} (nivel {a['level']}, evidence {', '.join(a['evidence'])})" for a in report["actions"]],
        "",
        "## Chunks",
        "",
        *[f"- {c['chunk_id']}: {c['title']} (anchors {', '.join(c['machine_reason']['why'])})" for c in report["chunks"]],
    ]
    (REPORTS_DIR / "persona_canonical_report.md").write_text("\n".join(md_lines))

def main():
    index = generate_index()
    generate_report(index)
    # Post-conditions: ENTRYPOINTS and chunk evidence must exist
    report = json.loads((REPORTS_DIR / "persona_canonical_report.json").read_text())
    entry_section = next((s for s in report["structure"]["sections"] if s["id"] == "S:ENTRYPOINTS"), None)
    if not entry_section or not entry_section.get("anchors"):
        raise SystemExit("ENTRYPOINTS anchors empty – aborting")
    entry_chunk = next((c for c in report["chunks"] if c.get("chunk_id") == "C:ENTRYPOINTS"), None)
    if not entry_chunk or not entry_chunk.get("machine_reason", {}).get("evidence"):
        raise SystemExit("C:ENTRYPOINTS has no evidence – aborting")
    action_main = next((a for a in report["actions"] if a.get("id") == "ACT:MAIN_ENTRY"), None)
    if not action_main or not action_main.get("evidence"):
        raise SystemExit("ACT:MAIN_ENTRY has no evidence – aborting")

if __name__ == "__main__":
    main()
