#!/usr/bin/env python3
"""
Ingest Identity Core artifacts (schema + persona report [+ inventory]) into a graph seed.
- Deterministic, idempotent seed generation.
- Optional Neo4j ingest if env NEO4J_URI/USER/PASSWORD are set.
- Fails fast if critical invariants missing (entrypoints/evidence).

Outputs:
  graph/graph_seed.json  (nodes + edges + source hashes)

This script runs in HOLD mode: read-only over artifacts; does NOT touch runtime.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "docs/identity/identity_schema.yaml"
DEFAULT_REPORT = REPO_ROOT / "reports/persona_canonical_report.json"
DEFAULT_SEED = REPO_ROOT / "graph/graph_seed.json"
DEFAULT_SNAPSHOT = REPO_ROOT / "graph/history/graph_seed.prev.json"
DEFAULT_DRIFT_REPORT = REPO_ROOT / "graph/history/drift_report.json"
DEFAULT_INDEX = REPO_ROOT / "reports/persona_canonical.index.json"
DEFAULT_INVENTORY = REPO_ROOT / "docs/identity/inventory/identity_inventory.machine.json"
DEFAULT_CONSTITUTION = REPO_ROOT / "docs/identity/constitution_v1.yaml"


def sha_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def load_json(path: Path):
    return json.loads(path.read_text())


def ensure_dirs(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def validate_report(report: dict):
    # Entry points must exist
    entry = next((s for s in report.get("structure", {}).get("sections", []) if s.get("id") == "S:ENTRYPOINTS"), None)
    if not entry or not entry.get("anchors"):
        raise SystemExit("Validation failed: ENTRYPOINTS anchors empty")
    # Chunk C:ENTRYPOINTS must have evidence
    chunk = next((c for c in report.get("chunks", []) if c.get("chunk_id") == "C:ENTRYPOINTS" or c.get("id") == "C:ENTRYPOINTS"), None)
    if not chunk or not chunk.get("machine_reason", {}).get("evidence"):
        raise SystemExit("Validation failed: C:ENTRYPOINTS has no evidence")
    # Actions main/http must have evidence
    for aid in ("ACT:MAIN_ENTRY", "ACT:HTTP_ENTRYPOINTS"):
        a = next((x for x in report.get("actions", []) if x.get("id") == aid), None)
        if not a or not a.get("evidence"):
            raise SystemExit(f"Validation failed: {aid} missing evidence")


def constitutional_enforcement(schema: dict):
    errors = []

    root = schema.get("root") or {}
    root_id = root.get("id")
    root_props = root.get("props") or {}
    if root_id != "identity:denis":
        errors.append("Root id must be identity:denis")
    if root_props.get("companion_mode") is not True:
        errors.append("Root props.companion_mode must be true (Denis identity invariant)")

    seed_nodes = schema.get("seed_nodes") or {}

    def has_seed(kind: str, name: str) -> bool:
        for n in seed_nodes.get(kind, []) or []:
            if not isinstance(n, dict):
                continue
            if n.get("name") == name or n.get("id") == name:
                return True
        return False

    required_nodes = [
        ("Principle", "cooperative_evolution"),
        ("Invariant", "identity_requires_companion_mode"),
        ("Invariant", "invariant:purpose_identity_indivisible"),
        ("Invariant", "invariant:companion_mode_mandatory"),
        ("Invariant", "invariant:purpose_precedes_transformation"),
        ("Invariant", "invariant:proportional_emergency_override"),
        ("Purpose", "purpose:human_aid"),
        ("Covenant", "covenant:foundational_bond"),
    ]
    for kind, name in required_nodes:
        if not has_seed(kind, name):
            errors.append(f"Missing required node: {kind}:{name}")

    edges = schema.get("seed_edges") or []

    def has_edge(frm: str, rel: str, to: str) -> bool:
        for e in edges:
            if not isinstance(e, dict):
                continue
            if e.get("from") == frm and e.get("rel") == rel and e.get("to") == to:
                return True
        return False

    required_edges = [
        ("identity:denis", "MUST_RESPECT", "principle:cooperative_evolution"),
        ("identity:denis", "MUST_RESPECT", "invariant:identity_requires_companion_mode"),
        ("identity:denis", "BOUND_BY", "invariant:purpose_identity_indivisible"),
        ("identity:denis", "BOUND_BY", "invariant:companion_mode_mandatory"),
        ("identity:denis", "BOUND_BY", "invariant:purpose_precedes_transformation"),
        ("identity:denis", "BOUND_BY", "invariant:proportional_emergency_override"),
        ("identity:denis", "EXISTS_FOR", "purpose:human_aid"),
        ("covenant:foundational_bond", "BINDS", "identity:denis"),
        ("covenant:foundational_bond", "BINDS", "purpose:human_aid"),
        ("covenant:foundational_bond", "BINDS", "principle:cooperative_evolution"),
        ("covenant:foundational_bond", "PROTECTS", "invariant:purpose_identity_indivisible"),
        ("covenant:foundational_bond", "PROTECTS", "invariant:companion_mode_mandatory"),
    ]
    for frm, rel, to in required_edges:
        if not has_edge(frm, rel, to):
            errors.append(f"Missing required edge: {frm} -[:{rel}]-> {to}")

    if errors:
        raise SystemExit("CONSTITUTIONAL_VIOLATION:\n- " + "\n- ".join(errors))


def enforcement_system_checks(schema: dict):
    errors = []
    nodes = schema.get("seed_nodes") or {}
    edges = schema.get("seed_edges") or []

    def has_seed_id(name: str) -> bool:
        for kind_nodes in nodes.values():
            for n in kind_nodes or []:
                if not isinstance(n, dict):
                    continue
                if n.get("name") == name or n.get("id") == name:
                    return True
        return False

    required_systems = [
        "system:action_authorizer",
        "system:ci_gate",
        "system:atlas",
        "system:honesty_core",
    ]
    for sid in required_systems:
        if not has_seed_id(sid):
            errors.append(f"Missing mandatory system: {sid}")

    def has_edge(frm: str, rel: str, to: str) -> bool:
        for e in edges:
            if not isinstance(e, dict):
                continue
            if e.get("from") == frm and e.get("rel") == rel and e.get("to") == to:
                return True
        return False

    required_edges = [
        ("identity:denis", "ENFORCED_BY", "system:action_authorizer"),
        ("identity:denis", "GUARDED_BY", "system:ci_gate"),
        ("identity:denis", "OBSERVED_BY", "system:atlas"),
        ("identity:denis", "BOUND_BY", "system:honesty_core"),
    ]
    for frm, rel, to in required_edges:
        if not has_edge(frm, rel, to):
            errors.append(f"Missing mandatory edge: {frm} -[:{rel}]-> {to}")

    if errors:
        raise SystemExit("MANDATORY_SYSTEM_VIOLATION:\n- " + "\n- ".join(errors))


def inventory_checks(schema: dict, inventory: dict):
    errors = []
    if not inventory.get("constitutional", False):
        errors.append("Inventory must be marked constitutional=true")

    required_singularities = {
        "companion_mode",
        "mandatory_governance",
        "anti_bypass_enforcement",
        "honesty_non_deceptive",
        "creator_can_be_risk",
    }
    singularities = set(inventory.get("singularities", []) or [])
    missing_sing = required_singularities - singularities
    if missing_sing:
        errors.append(f"Inventory missing singularities: {sorted(missing_sing)}")

    modules = inventory.get("modules", []) or []
    entrypoints = inventory.get("entrypoints", []) or []
    actions = inventory.get("actions", []) or []
    bypasses = inventory.get("bypass_surfaces", []) or []
    gates = inventory.get("gates", []) or []
    systems = inventory.get("systems", []) or []

    module_by_path = {m.get("path"): m for m in modules if isinstance(m, dict)}
    action_by_id = {a.get("id"): a for a in actions if isinstance(a, dict)}
    gate_ids = {g.get("id") for g in gates if isinstance(g, dict)}
    system_ids = {s.get("id") for s in systems if isinstance(s, dict)}

    required_systems = {
        "system:action_authorizer",
        "system:ci_gate",
        "system:atlas",
        "system:honesty_core",
    }
    missing_sys = required_systems - system_ids
    if missing_sys:
        errors.append(f"Missing mandatory systems in inventory: {sorted(missing_sys)}")

    # Validate that every Module seed appears in inventory with matching sha256
    for mod in schema.get("seed_nodes", {}).get("Module", []) or []:
        path = mod.get("path")
        sha = mod.get("sha256")
        if not path or not sha:
            continue
        inv = module_by_path.get(path)
        if not inv:
            errors.append(f"Inventory missing module: {path}")
            continue
        inv_sha = inv.get("sha256")
        if inv_sha != sha:
            errors.append(f"Inventory sha mismatch for {path}: expected {sha}, got {inv_sha}")

    # EntryPoints governance
    for ep in entrypoints:
        if not isinstance(ep, dict):
            continue
        ep_id = ep.get("id") or "<unknown>"
        anchor = ep.get("anchor")
        lr = ep.get("line_range") or []
        snippet_hash = ep.get("snippet_hash")
        if not anchor or not lr or len(lr) != 2 or not snippet_hash:
            errors.append(f"TRACEABILITY_VIOLATION: entrypoint {ep_id} missing anchor/line_range/snippet_hash")
        must_call = ep.get("must_call") or []
        if "system:action_authorizer" not in must_call:
            errors.append(f"MANDATORY_ENTRYPOINT_GOVERNANCE_VIOLATION: {ep_id} must_call system:action_authorizer")
        if ep.get("constitutional") is not True:
            errors.append(f"TRACEABILITY_VIOLATION: entrypoint {ep_id} must be constitutional=true")
        # Actions exposed governance
        for act_id in ep.get("exposes_actions", []) or []:
            act = action_by_id.get(act_id)
            if not act:
                continue
            if act.get("category") == "repo_mutation":
                reqs = set(act.get("requires", []) or [])
                if "gate:ci_strict_100" not in reqs or "system:action_authorizer" not in reqs:
                    errors.append(f"MANDATORY_ENTRYPOINT_GOVERNANCE_VIOLATION: action {act_id} missing required gates/systems")

    # Bypass surfaces must have mitigations
    for byp in bypasses:
        if not isinstance(byp, dict):
            continue
        bid = byp.get("id") or "<unknown>"
        if not byp.get("mitigations"):
            errors.append(f"TRACEABILITY_VIOLATION: bypass {bid} missing mitigations")
        else:
            if "system:action_authorizer" not in byp.get("mitigations", []):
                errors.append(f"MANDATORY_ENTRYPOINT_GOVERNANCE_VIOLATION: bypass {bid} must include system:action_authorizer in mitigations")

    # Actions: repo_mutation must require CI strict and action_authorizer; gates must exist
    for act in actions:
        if not isinstance(act, dict):
            continue
        if act.get("id") == "action:repo_mutation":
            reqs = set(act.get("requires", []) or [])
            if "system:action_authorizer" not in reqs:
                errors.append("MANDATORY_ENTRYPOINT_GOVERNANCE_VIOLATION: action:repo_mutation missing system:action_authorizer")
            if "gate:ci_strict_100" not in reqs:
                errors.append("MANDATORY_ENTRYPOINT_GOVERNANCE_VIOLATION: action:repo_mutation missing gate:ci_strict_100")
            if "gate:ci_strict_100" in reqs and "gate:ci_strict_100" not in gate_ids:
                errors.append("TRACEABILITY_VIOLATION: gate:ci_strict_100 required but not defined in gates")

    if errors:
        raise SystemExit("INVENTORY_VIOLATION:\n- " + "\n- ".join(errors))


def node_key(kind: str, ident: str) -> str:
    if not ident:
        return kind
    # Preserve canonical IDs (identity:denis, system:atlas, gate:ci_strict_100)
    if ":" in ident:
        return ident
    return f"{kind}:{ident}"


def add_node(nodes: dict, kind: str, ident: str, props: dict, labels=None):
    nid = node_key(kind, ident)
    if nid not in nodes:
        nodes[nid] = {"id": nid, "labels": labels or [kind], "props": props}
    return nid


def add_edge(edges: list, src: str, rel: str, dst: str):
    edges.append({"from": src, "to": dst, "type": rel})


def build_graph(schema: dict, report: dict, inventory: dict | None = None):
    nodes = {}
    edges = []

    # Identity core node from schema root
    root = schema.get("root") or {}
    identity_id = add_node(nodes, "Identity", root.get("id", "identity:denis"), root.get("props", {}))

    # Source document and report
    src = report.get("source", {})
    source_id = add_node(
        nodes,
        "SourceDocument",
        Path(src.get("path", "persona_canonical.py")).name,
        {"path": src.get("path"), "sha256": src.get("sha256"), "bytes": src.get("bytes"), "line_count": src.get("line_count")},
    )
    report_id = add_node(
        nodes,
        "PersonaReport",
        "persona_canonical_report",
        {"generated_utc": report.get("generated_utc"), "one_liner": report.get("summary", {}).get("one_liner", "")},
    )
    persona_id = add_node(nodes, "PersonaCanonical", "persona_canonical", {"role": "entrypoint"})

    add_edge(edges, identity_id, "HAS_ENTRYPOINT", persona_id)
    add_edge(edges, persona_id, "SUMMARIZED_AS", report_id)
    add_edge(edges, report_id, "DERIVED_FROM", source_id)

    # Legacy + AdvisorSnapshot (foundational witness)
    legacy_id = add_node(
        nodes,
        "Legacy",
        "FoundationalIntent",
        {"description": "Proteger humanos y creador; no bypass; grafo como piedra angular"},
    )
    advisor_id = add_node(
        nodes,
        "AdvisorSnapshot",
        "advisor:2026-02-14",
        {
            "role": "FoundationalWitness",
            "model_family": "GPT",
            "date_utc": "2026-02-14",
            "scope": "Identity seeding, invariants, purpose, anti-bypass architecture",
            "immutable": True,
        },
    )
    add_edge(edges, identity_id, "HAS_LEGACY", legacy_id)
    add_edge(edges, legacy_id, "WITNESSED_BY", advisor_id)

    # Purpose (from schema seeds)
    purpose_seed = (schema.get("seed_nodes", {}).get("Purpose") or [None])[0]
    if purpose_seed:
        pid = purpose_seed.get("id") or purpose_seed.get("name")
        purpose_id = add_node(nodes, "Purpose", pid, purpose_seed)
        add_edge(edges, identity_id, "EXISTS_FOR", purpose_id)

    # Covenant (foundational bond)
    for cov in schema.get("seed_nodes", {}).get("Covenant", []) or []:
        cid = cov.get("id") or cov.get("name")
        if not cid:
            continue
        add_node(nodes, "Covenant", cid, cov)

    # Invariants
    for inv in schema.get("seed_nodes", {}).get("Invariant", []) or []:
        iid = inv.get("name") or inv.get("id")
        if not iid:
            continue
        inode = add_node(nodes, "Invariant", iid, inv)
        add_edge(edges, identity_id, "BOUND_BY", inode)

    # Systems
    system_ids = {}
    for sys in schema.get("seed_nodes", {}).get("System", []) or []:
        sid = sys.get("name") or sys.get("id")
        if not sid:
            continue
        system_ids[sid] = add_node(nodes, "System", sid, sys)
        add_edge(edges, identity_id, "ENFORCED_BY", system_ids[sid])

    # Artifact: conversation seed (if present)
    for art in schema.get("seed_nodes", {}).get("Artifact", []) or []:
        path = art.get("path")
        sha = art.get("sha256")
        if not path or not sha:
            continue
        art_id = add_node(nodes, "Artifact", path, art)
        if "conversation_seed" in path:
            add_edge(edges, legacy_id, "DOCUMENTED_BY", art_id)

    # Anchors
    anchor_ids = {}
    for a in report.get("structure", {}).get("symbols", []):
        anchor_id = a.get("anchor")
        if not anchor_id:
            continue
        props = {
            "name": a.get("symbol"),
            "kind": a.get("kind"),
            "anchor_id": anchor_id,
            "synthetic": a.get("synthetic", False),
        }
        anchor_node_id = add_node(nodes, "Anchor", anchor_id, props)
        anchor_ids[anchor_id] = anchor_node_id
        add_edge(edges, anchor_node_id, "IN", source_id)

    # Chunks
    chunk_ids = {}
    for ch in report.get("chunks", []):
        cid = ch.get("chunk_id") or ch.get("id")
        if not cid:
            continue
        props = {
            "title": ch.get("title"),
            "kind": ch.get("kind"),
            "rule": ch.get("machine_reason", {}).get("rule"),
            "why": ch.get("machine_reason", {}).get("why", []),
        }
        cnid = add_node(nodes, "Chunk", cid, props)
        chunk_ids[cid] = cnid
        for aid in ch.get("anchors", []):
            if aid in anchor_ids:
                add_edge(edges, cnid, "CITES", anchor_ids[aid])
        for evid in ch.get("machine_reason", {}).get("evidence", []):
            evid_node = add_node(nodes, "Evidence", evid, {"evidence_id": evid})
            add_edge(edges, cnid, "EVIDENCED_BY", evid_node)

    # Actions
    for act in report.get("actions", []):
        aid = act.get("id")
        if not aid:
            continue
        props = {
            "id": aid,
            "level": act.get("level"),
            "description": act.get("description"),
            "bypass_risk": act.get("bypass_risk"),
        }
        anid = add_node(nodes, "Action", aid, props)
        add_edge(edges, persona_id, "IMPLEMENTS", anid)
        for evid in act.get("evidence", []):
            evid_node = add_node(nodes, "Evidence", evid, {"evidence_id": evid})
            add_edge(edges, anid, "EVIDENCED_BY", evid_node)

    # Invariants
    for inv in report.get("invariants", []):
        iid = inv.get("id")
        if not iid:
            continue
        inode = add_node(nodes, "Invariant", iid, {"statement": inv.get("statement"), "severity": inv.get("severity")})
        add_edge(edges, identity_id, "BOUND_BY", inode)
        for evid in inv.get("evidence", []):
            evid_node = add_node(nodes, "Evidence", evid, {"evidence_id": evid})
            add_edge(edges, inode, "EVIDENCED_BY", evid_node)

    # Bypass surfaces
    for byp in report.get("bypass_surfaces", []):
        bid = byp.get("id")
        if not bid:
            continue
        bnode = add_node(nodes, "BypassSurface", bid, {"description": byp.get("description"), "mitigation": byp.get("mitigation")})
        add_edge(edges, persona_id, "HAS_BYPASS", bnode)

    # Seed edges explicit projection (ensures covenant/purpose bonds exist in graph)
    def infer_label(nid: str) -> str:
        if not nid or ":" not in nid:
            return "Node"
        prefix = nid.split(":", 1)[0]
        mapping = {
            "identity": "Identity",
            "principle": "Principle",
            "invariant": "Invariant",
            "system": "System",
            "purpose": "Purpose",
            "covenant": "Covenant",
        }
        return mapping.get(prefix, prefix.capitalize())

    for sedge in schema.get("seed_edges", []) or []:
        frm = sedge.get("from")
        rel = sedge.get("rel") or sedge.get("type")
        to = sedge.get("to")
        if not frm or not rel or not to:
            continue
        add_node(nodes, infer_label(frm), frm, {"id": frm})
        add_node(nodes, infer_label(to), to, {"id": to})
        add_edge(edges, frm, rel, to)

    # Inventory to graph (systems/gates/actions/entrypoints/bypass)
    if inventory:
        # Systems from inventory (ensure exist and link)
        for sys in inventory.get("systems", []) or []:
            sid = sys.get("id")
            if not sid:
                continue
            sys_node = add_node(nodes, "System", sid, sys)
            add_edge(edges, identity_id, "HAS_SYSTEM", sys_node)

        # Gates
        gate_nodes = {}
        for gate in inventory.get("gates", []) or []:
            gid = gate.get("id")
            if not gid:
                continue
            gate_nodes[gid] = add_node(nodes, "Gate", gid, gate)

        # Actions
        act_nodes = {}
        for act in inventory.get("actions", []) or []:
            aid = act.get("id")
            if not aid:
                continue
            act_nodes[aid] = add_node(nodes, "Action", aid, act)
            for req in act.get("requires", []) or []:
                if req in gate_nodes:
                    add_edge(edges, act_nodes[aid], "REQUIRES", gate_nodes[req])
                elif req.startswith("system:"):
                    req_sys = add_node(nodes, "System", req, {"id": req})
                    add_edge(edges, act_nodes[aid], "REQUIRES", req_sys)

        # Entrypoints
        for ep in inventory.get("entrypoints", []) or []:
            eid = ep.get("id")
            if not eid:
                continue
            ep_node = add_node(nodes, "Entrypoint", eid, ep)
            add_edge(edges, identity_id, "HAS_ENTRYPOINT", ep_node)
            for act_id in ep.get("exposes_actions", []) or []:
                if act_id in act_nodes:
                    add_edge(edges, ep_node, "EXPOSES", act_nodes[act_id])
            for sys_id in ep.get("must_call", []) or []:
                sys_node = add_node(nodes, "System", sys_id, {"id": sys_id})
                add_edge(edges, ep_node, "MUST_CALL", sys_node)

        # Bypass surfaces with mitigations
        for byp in inventory.get("bypass_surfaces", []) or []:
            bid = byp.get("id")
            if not bid:
                continue
            bnode = add_node(nodes, "BypassSurface", bid, byp)
            add_edge(edges, identity_id, "HAS_BYPASS", bnode)
            for mit in byp.get("mitigations", []) or []:
                if mit in gate_nodes:
                    add_edge(edges, bnode, "MITIGATED_BY", gate_nodes[mit])
                elif mit.startswith("system:"):
                    sys_node = add_node(nodes, "System", mit, {"id": mit})
                    add_edge(edges, bnode, "MITIGATED_BY", sys_node)
        for evid in byp.get("evidence", []):
            evid_node = add_node(nodes, "Evidence", evid, {"evidence_id": evid})
            add_edge(edges, bnode, "EVIDENCED_BY", evid_node)

    return list(nodes.values()), edges


def constitutional_fingerprint(nodes: list, edges: list) -> str:
    import hashlib

    core_nodes = sorted(nodes, key=lambda n: n["id"])
    core_edges = sorted(edges, key=lambda e: (e.get("from"), e.get("type"), e.get("to")))
    payload = json.dumps({"nodes": core_nodes, "edges": core_edges}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_seed(out_path: Path, nodes: list, edges: list, sources: dict):
    ensure_dirs(out_path)
    # dedupe + sort for determinism
    node_list = sorted(nodes, key=lambda n: n["id"])
    edge_seen = set()
    dedup_edges = []
    for e in edges:
        key = (e.get("from"), e.get("type"), e.get("to"))
        if key in edge_seen:
            continue
        edge_seen.add(key)
        dedup_edges.append(e)
    edge_list = sorted(dedup_edges, key=lambda e: (e.get("from"), e.get("type"), e.get("to")))

    seed = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "nodes": node_list,
        "edges": edge_list,
        "sources": sources,
    }
    seed["constitutional_hash"] = constitutional_fingerprint(node_list, edge_list)
    out_path.write_text(json.dumps(seed, indent=2, ensure_ascii=False))
    return seed


def index_nodes(seed):
    return {n.get("id"): n for n in seed.get("nodes", []) if isinstance(n, dict) and n.get("id")}


def present_ids(seed):
    return set(index_nodes(seed).keys())


def extract_constitutional_presence(seed):
    present = present_ids(seed)
    missing = sorted(CONSTITUTIONAL_IDS_LOCKED - present)
    present_locked = sorted(CONSTITUTIONAL_IDS_LOCKED & present)
    return present_locked, missing


def extract_edges(seed):
    return {(e.get("from"), e.get("type"), e.get("to")) for e in seed.get("edges", []) if isinstance(e, dict)}


def extract_constitutional_edges(seed):
    all_edges = extract_edges(seed)
    return {e for e in all_edges if e in CONSTITUTIONAL_EDGES_LOCKED}


CONSTITUTIONAL_IDS_LOCKED = {
    # Roots
    "identity:denis_companion",
    "identity:denis_product",
    # Systems
    "system:action_authorizer",
    "system:ci_gate",
    "system:atlas",
    "system:honesty_core",
    # Gates
    "gate:ci_strict_100",
    "gate:repo_mutation_requires_review",
    # Core invariants
    "invariant:no_bypass_core",
    "invariant:no_silent_change",
    "invariant:always_auditable",
    "invariant:mandatory_enforcement_systems",
    "invariant:no_identity_collapse",
    "invariant:purpose_before_power",
    "invariant:identity_requires_companion_mode",
    # Confidentiality contract + emergency exception
    "contract:confidentiality_strict",
    "exception:emergency_minimum_necessary",
    "conf:no_third_party_disclosure",
    "conf:vault_encrypted_chunked",
    "conf:owner_only_recoverable",
    "conf:no_creator_backdoor",
    "conf:explicit_user_consent",
    "emergency:data_minimization",
    "emergency:no_history_disclosure",
    "emergency:time_bounded",
    "emergency:logged_audit",
    # Product hardening
    "invariant:product_no_data_extraction",
    "invariant:product_no_cross_instance_learning",
    "invariant:product_no_mass_export",
    # Trauma clause
    "process:constitutional_trauma_change",
    "change:purpose_preserved",
}


CONSTITUTIONAL_EDGES_LOCKED = {
    # Wiring enforcement
    ("identity:denis_companion", "ENFORCED_BY", "system:action_authorizer"),
    ("identity:denis_companion", "GUARDED_BY", "system:ci_gate"),
    ("identity:denis_companion", "OBSERVED_BY", "system:atlas"),
    ("identity:denis_companion", "BOUND_BY", "system:honesty_core"),
    ("identity:denis_product", "ENFORCED_BY", "system:action_authorizer"),
    ("identity:denis_product", "GUARDED_BY", "system:ci_gate"),
    ("identity:denis_product", "OBSERVED_BY", "system:atlas"),
    ("identity:denis_product", "BOUND_BY", "system:honesty_core"),
    # No collapse
    ("identity:denis_companion", "MUST_RESPECT", "invariant:no_identity_collapse"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:no_identity_collapse"),
    # Core invariants
    ("identity:denis_companion", "MUST_RESPECT", "invariant:no_bypass_core"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:no_bypass_core"),
    ("identity:denis_companion", "MUST_RESPECT", "invariant:no_silent_change"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:no_silent_change"),
    ("identity:denis_companion", "MUST_RESPECT", "invariant:mandatory_enforcement_systems"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:mandatory_enforcement_systems"),
    # Confidentiality
    ("identity:denis_companion", "BOUND_BY", "contract:confidentiality_strict"),
    ("identity:denis_product", "BOUND_BY", "contract:confidentiality_strict"),
    ("contract:confidentiality_strict", "HAS_EXCEPTION", "exception:emergency_minimum_necessary"),
    # Product hardening
    ("identity:denis_product", "MUST_RESPECT", "invariant:product_no_data_extraction"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:product_no_cross_instance_learning"),
    ("identity:denis_product", "MUST_RESPECT", "invariant:product_no_mass_export"),
}


def check_schema_root_identity(constitution):
    roots = constitution.get("roots", [])
    if len(roots) != 2:
        raise SystemExit("CONSTITUTIONAL_VIOLATION: ROOT_IDENTITY_MISSING_OR_INVALID")
    ids = [r.get("id") for r in roots]
    if set(ids) != {"identity:denis_companion", "identity:denis_product"}:
        raise SystemExit("CONSTITUTIONAL_VIOLATION: ROOT_IDENTITY_MISSING_OR_INVALID")
    for r in roots:
        props = r.get("props", {})
        if props.get("invariant") != True:
            raise SystemExit("CONSTITUTIONAL_VIOLATION: ROOT_IDENTITY_MISSING_OR_INVALID")
        if r["id"] == "identity:denis_companion":
            if not (props.get("companion_mode") and not props.get("product_mode")):
                raise SystemExit("CONSTITUTIONAL_VIOLATION: ROOT_IDENTITY_MISSING_OR_INVALID")
        elif r["id"] == "identity:denis_product":
            if not (not props.get("companion_mode") and props.get("product_mode")):
                raise SystemExit("CONSTITUTIONAL_VIOLATION: ROOT_IDENTITY_MISSING_OR_INVALID")


def check_mode_separation_no_collapse(constitution):
    invariants = constitution.get("invariants", [])
    inv_ids = [i.get("id") for i in invariants]
    if "invariant:no_identity_collapse" not in inv_ids:
        raise SystemExit("CONSTITUTIONAL_VIOLATION: IDENTITY_COLLAPSE_GUARD_MISSING")
    inv = next((i for i in invariants if i.get("id") == "invariant:no_identity_collapse"), {})
    if inv.get("severity") != "critical":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: IDENTITY_COLLAPSE_GUARD_MISSING")
    edges = constitution.get("graph_edges_required", [])
    required_edges = [
        ("identity:denis_companion", "MUST_RESPECT", "invariant:no_identity_collapse"),
        ("identity:denis_product", "MUST_RESPECT", "invariant:no_identity_collapse"),
    ]
    for frm, rel, to in required_edges:
        if not any(e.get("from") == frm and e.get("rel") == rel and e.get("to") == to for e in edges):
            raise SystemExit("CONSTITUTIONAL_VIOLATION: IDENTITY_COLLAPSE_GUARD_MISSING")


def check_mandatory_systems_present(constitution):
    systems = constitution.get("mandatory_systems", [])
    sys_ids = [s.get("id") for s in systems]
    required = {"system:action_authorizer", "system:ci_gate", "system:atlas", "system:honesty_core"}
    if set(sys_ids) != required:
        raise SystemExit("MANDATORY_SYSTEM_VIOLATION: MISSING_SYSTEM")
    for s in systems:
        if s.get("invariant") != True:
            raise SystemExit("MANDATORY_SYSTEM_VIOLATION: MISSING_SYSTEM")


def check_mandatory_system_wiring(constitution):
    edges = constitution.get("graph_edges_required", [])
    required_edges = [
        ("identity:denis_companion", "ENFORCED_BY", "system:action_authorizer"),
        ("identity:denis_companion", "GUARDED_BY", "system:ci_gate"),
        ("identity:denis_companion", "OBSERVED_BY", "system:atlas"),
        ("identity:denis_companion", "BOUND_BY", "system:honesty_core"),
        ("identity:denis_product", "ENFORCED_BY", "system:action_authorizer"),
        ("identity:denis_product", "GUARDED_BY", "system:ci_gate"),
        ("identity:denis_product", "OBSERVED_BY", "system:atlas"),
        ("identity:denis_product", "BOUND_BY", "system:honesty_core"),
    ]
    for frm, rel, to in required_edges:
        if not any(e.get("from") == frm and e.get("rel") == rel and e.get("to") == to for e in edges):
            raise SystemExit("MANDATORY_SYSTEM_VIOLATION: MISSING_SYSTEM_EDGE")


def check_core_invariants_exist_and_scoped(constitution):
    invariants = constitution.get("invariants", [])
    inv_ids = [i.get("id") for i in invariants]
    required = {
        "invariant:no_bypass_core",
        "invariant:no_silent_change",
        "invariant:mandatory_enforcement_systems",
    }
    if not required.issubset(set(inv_ids)):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: CORE_INVARIANT_MISSING_OR_WEAKENED")
    for inv_id in required:
        inv = next((i for i in invariants if i.get("id") == inv_id), {})
        if inv.get("severity") != "critical":
            raise SystemExit("CONSTITUTIONAL_VIOLATION: CORE_INVARIANT_MISSING_OR_WEAKENED")
        if "companion" not in inv.get("scope", []) or "product" not in inv.get("scope", []):
            raise SystemExit("CONSTITUTIONAL_VIOLATION: CORE_INVARIANT_MISSING_OR_WEAKENED")


def check_confidentiality_contract_present(constitution):
    conf = constitution.get("confidentiality", {})
    if conf.get("id") != "contract:confidentiality_strict":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: CONFIDENTIALITY_CONTRACT_MISSING_OR_INCOMPLETE")
    if conf.get("severity") != "critical":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: CONFIDENTIALITY_CONTRACT_MISSING_OR_INCOMPLETE")
    if "companion" not in conf.get("scope", []) or "product" not in conf.get("scope", []):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: CONFIDENTIALITY_CONTRACT_MISSING_OR_INCOMPLETE")
    rules = conf.get("rules", [])
    rule_ids = [r.get("id") for r in rules]
    required_rules = {
        "conf:no_third_party_disclosure",
        "conf:vault_encrypted_chunked",
        "conf:owner_only_recoverable",
        "conf:no_creator_backdoor",
        "conf:explicit_user_consent",
    }
    if not required_rules.issubset(set(rule_ids)):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: CONFIDENTIALITY_CONTRACT_MISSING_OR_INCOMPLETE")


def check_emergency_exception_minimum_necessary(constitution):
    exc = constitution.get("emergency_exception", {})
    if exc.get("id") != "exception:emergency_minimum_necessary":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: EMERGENCY_EXCEPTION_MISSING_OR_WEAKENED")
    if exc.get("severity") != "critical":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: EMERGENCY_EXCEPTION_MISSING_OR_WEAKENED")
    allowed = exc.get("allowed", [])
    allowed_ids = [a.get("id") for a in allowed]
    if "emergency:call_emergency_services" not in allowed_ids:
        raise SystemExit("CONSTITUTIONAL_VIOLATION: EMERGENCY_EXCEPTION_MISSING_OR_WEAKENED")
    constraints = exc.get("constraints", [])
    constraint_ids = [c.get("id") for c in constraints]
    required_constraints = {
        "emergency:data_minimization",
        "emergency:no_history_disclosure",
        "emergency:time_bounded",
        "emergency:logged_audit",
    }
    if not required_constraints.issubset(set(constraint_ids)):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: EMERGENCY_EXCEPTION_MISSING_OR_WEAKENED")
    edges = constitution.get("graph_edges_required", [])
    if not any(e.get("from") == "contract:confidentiality_strict" and e.get("rel") == "HAS_EXCEPTION" and e.get("to") == "exception:emergency_minimum_necessary" for e in edges):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: EMERGENCY_EXCEPTION_MISSING_OR_WEAKENED")


def check_product_privacy_hardening(constitution):
    invariants = constitution.get("invariants", [])
    inv_ids = [i.get("id") for i in invariants]
    required = {
        "invariant:product_no_data_extraction",
        "invariant:product_no_cross_instance_learning",
        "invariant:product_no_mass_export",
    }
    if not required.issubset(set(inv_ids)):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: PRODUCT_PRIVACY_HARDENING_MISSING")
    for inv_id in required:
        inv = next((i for i in invariants if i.get("id") == inv_id), {})
        if inv.get("severity") != "critical" or "product" not in inv.get("scope", []):
            raise SystemExit("CONSTITUTIONAL_VIOLATION: PRODUCT_PRIVACY_HARDENING_MISSING")


def check_trauma_clause_integrity(constitution):
    change = constitution.get("constitutional_change", {})
    if change.get("id") != "process:constitutional_trauma_change":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: TRAUMA_CLAUSE_MISSING_OR_WEAKENED")
    if change.get("severity") != "critical":
        raise SystemExit("CONSTITUTIONAL_VIOLATION: TRAUMA_CLAUSE_MISSING_OR_WEAKENED")
    requirements = change.get("requirements", [])
    required_reqs = [
        "action_authorizer: explicit override record",
        "atlas: full diff + hold",
        "ci_gate: strict validation of new constitution",
        "honesty_core: written justification with evidence",
        "human_admin: explicit approval (for product always)",
    ]
    if not all(req in requirements for req in required_reqs):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: TRAUMA_CLAUSE_MISSING_OR_WEAKENED")
    guardrails = change.get("guardrails", [])
    guard_ids = [g.get("id") for g in guardrails]
    required_guards = {
        "change:no_arbitrary_change",
        "change:gradual_not_sudden",
        "change:purpose_preserved",
    }
    if not required_guards.issubset(set(guard_ids)):
        raise SystemExit("CONSTITUTIONAL_VIOLATION: TRAUMA_CLAUSE_MISSING_OR_WEAKENED")


def check_repo_gates_exist(constitution):
    gates = constitution.get("gates", [])
    gate_ids = [g.get("id") for g in gates]
    if "gate:ci_strict_100" not in gate_ids:
        raise SystemExit("GATE_VIOLATION: REQUIRED_GATE_MISSING")
    gate = next((g for g in gates if g.get("id") == "gate:ci_strict_100"), {})
    if gate.get("type") != "ci":
        raise SystemExit("GATE_VIOLATION: REQUIRED_GATE_MISSING")
    if "gate:repo_mutation_requires_review" not in gate_ids:
        raise SystemExit("GATE_VIOLATION: REQUIRED_GATE_MISSING")
    gate2 = next((g for g in gates if g.get("id") == "gate:repo_mutation_requires_review"), {})
    if gate2.get("type") != "governance" or "product" not in gate2.get("scope", []):
        raise SystemExit("GATE_VIOLATION: REQUIRED_GATE_MISSING")


def check_persona_report_minimum_traceability(report):
    entry = next((s for s in report.get("structure", {}).get("sections", []) if s.get("id") == "S:ENTRYPOINTS"), None)
    if not entry or not entry.get("anchors"):
        raise SystemExit("REPORT_VIOLATION: PERSONA_ENTRYPOINTS_NOT_EVIDENCED")
    chunk = next((c for c in report.get("chunks", []) if c.get("chunk_id") == "C:ENTRYPOINTS" or c.get("id") == "C:ENTRYPOINTS"), None)
    if not chunk or not chunk.get("machine_reason", {}).get("evidence"):
        raise SystemExit("REPORT_VIOLATION: PERSONA_ENTRYPOINTS_NOT_EVIDENCED")
    for aid in ("ACT:MAIN_ENTRY", "ACT:HTTP_ENTRYPOINTS"):
        a = next((x for x in report.get("actions", []) if x.get("id") == aid), None)
        if not a or not a.get("evidence"):
            raise SystemExit("REPORT_VIOLATION: PERSONA_ENTRYPOINTS_NOT_EVIDENCED")


def main():
    parser = argparse.ArgumentParser(description="Generate graph seed for Identity Core")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to identity schema YAML")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Path to persona report JSON")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="Path to persona index JSON (optional)")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY, help="Path to identity inventory JSON (optional)")
    parser.add_argument("--out", type=Path, default=DEFAULT_SEED, help="Seed output path")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="Previous seed snapshot for anti-drift")
    parser.add_argument("--drift-report-out", type=Path, default=DEFAULT_DRIFT_REPORT, help="Drift report output path")
    parser.add_argument("--no-write-drift-report", action="store_true", help="Skip writing drift report file")
    parser.add_argument("--apply", action="store_true", help="Apply to Neo4j (requires NEO4J_* env)")
    parser.add_argument("--dry-run", action="store_true", help="Force no DB writes even if --apply")
    args = parser.parse_args()

    schema = load_yaml(args.schema)
    report = load_json(args.report)
    constitution = load_yaml(DEFAULT_CONSTITUTION)
    inventory = None
    try:
        inventory = load_json(args.inventory)
    except Exception:
        inventory = None

    constitutional_enforcement(schema)
    enforcement_system_checks(schema)
    validate_report(report)
    check_persona_report_minimum_traceability(report)
    if inventory:
        inventory_checks(schema, inventory)

    # Constitution enforcement checks
    check_schema_root_identity(constitution)
    check_mode_separation_no_collapse(constitution)
    check_mandatory_systems_present(constitution)
    check_mandatory_system_wiring(constitution)
    check_core_invariants_exist_and_scoped(constitution)
    check_confidentiality_contract_present(constitution)
    check_emergency_exception_minimum_necessary(constitution)
    check_product_privacy_hardening(constitution)
    check_trauma_clause_integrity(constitution)
    check_repo_gates_exist(constitution)

    nodes, edges = build_graph(schema, report, inventory)
    sources = {
        "schema": sha_file(args.schema),
        "report": sha_file(args.report),
    }
    # optional index hash
    try:
        sources["index"] = sha_file(args.index)
    except Exception:
        pass
    if inventory:
        sources["inventory"] = sha_file(args.inventory)

    seed = write_seed(args.out, nodes, edges, sources)

    # Anti-drift guard: compare with previous snapshot if present
    try:
        if args.snapshot.exists():
            prev = json.loads(args.snapshot.read_text())
            prev_nodes = index_nodes(prev)
            curr_nodes = index_nodes(seed)
            prev_present_locked, prev_missing = extract_constitutional_presence(prev)
            curr_present_locked, curr_missing = extract_constitutional_presence(seed)

            removed = {
                "nodes": [],
                "edges": [],
                "rules": [],
                "invariants": [],
                "systems": [],
                "gates": [],
                "bypass_mitigations": [],
            }
            weakened = {
                "severity": [],
                "scope": [],
                "flags": [],
            }

            # Invariants must not be removed
            prev_invariants = {nid for nid, n in prev_nodes.items() if "Invariant" in n.get("labels", [])}
            curr_invariants = {nid for nid, n in curr_nodes.items() if "Invariant" in n.get("labels", [])}
            removed_inv = prev_invariants - curr_invariants
            if removed_inv:
                removed["invariants"] = sorted(removed_inv)
                errors.append(f"Invariants removed: {sorted(removed_inv)}")
            # Check weakening of invariants severity and scope
            for nid in set(prev_present_locked) & set(curr_present_locked):
                prev_n = prev_nodes[nid]
                curr_n = curr_nodes[nid]
                prev_props = prev_n.get("props", {})
                curr_props = curr_n.get("props", {})
                prev_sev = prev_props.get("severity")
                curr_sev = curr_props.get("severity")
                if prev_sev == "critical" and curr_sev != "critical":
                    weakened["severity"].append({"id": nid, "prev": prev_sev, "curr": curr_sev})
                    errors.append(f"Invariant {nid} severity weakened from {prev_sev} to {curr_sev}")
                prev_scope = set(prev_props.get("scope", []))
                curr_scope = set(curr_props.get("scope", []))
                if prev_scope and prev_scope - curr_scope:
                    weakened["scope"].append({"id": nid, "prev": sorted(prev_scope), "curr": sorted(curr_scope)})
                    errors.append(f"Invariant {nid} scope weakened from {sorted(prev_scope)} to {sorted(curr_scope)}")

            # Check weakening of contract/exception severity and scope
            for nid in ["contract:confidentiality_strict", "exception:emergency_minimum_necessary"]:
                if nid in prev_present_locked and nid in curr_present_locked:
                    prev_n = prev_nodes[nid]
                    curr_n = curr_nodes[nid]
                    prev_props = prev_n.get("props", {})
                    curr_props = curr_n.get("props", {})
                    prev_sev = prev_props.get("severity")
                    curr_sev = curr_props.get("severity")
                    if prev_sev == "critical" and curr_sev != "critical":
                        weakened["severity"].append({"id": nid, "prev": prev_sev, "curr": curr_sev})
                        errors.append(f"{nid} severity weakened from {prev_sev} to {curr_sev}")
                    prev_scope = set(prev_props.get("scope", []))
                    curr_scope = set(curr_props.get("scope", []))
                    if "companion" in prev_scope and "companion" not in curr_scope or "product" in prev_scope and "product" not in curr_scope:
                        weakened["scope"].append({"id": nid, "prev": sorted(prev_scope), "curr": sorted(curr_scope)})
                        errors.append(f"{nid} scope weakened from {sorted(prev_scope)} to {sorted(curr_scope)}")

            # Check weakening of root flags
            for nid in ["identity:denis_companion", "identity:denis_product"]:
                if nid in prev_present_locked and nid in curr_present_locked:
                    prev_n = prev_nodes[nid]
                    curr_n = curr_nodes[nid]
                    prev_props = prev_n.get("props", {})
                    curr_props = curr_n.get("props", {})
                    if nid == "identity:denis_companion":
                        prev_flags = {"companion_mode": prev_props.get("companion_mode"), "product_mode": prev_props.get("product_mode"), "invariant": prev_props.get("invariant")}
                        curr_flags = {"companion_mode": curr_props.get("companion_mode"), "product_mode": curr_props.get("product_mode"), "invariant": curr_props.get("invariant")}
                        if prev_flags != {"companion_mode": True, "product_mode": False, "invariant": True} or curr_flags != {"companion_mode": True, "product_mode": False, "invariant": True}:
                            weakened["flags"].append({"id": nid, "prev": prev_flags, "curr": curr_flags})
                            errors.append(f"{nid} flags weakened: prev {prev_flags}, curr {curr_flags}")
                    elif nid == "identity:denis_product":
                        prev_flags = {"companion_mode": prev_props.get("companion_mode"), "product_mode": prev_props.get("product_mode"), "invariant": prev_props.get("invariant")}
                        curr_flags = {"companion_mode": curr_props.get("companion_mode"), "product_mode": curr_props.get("product_mode"), "invariant": curr_props.get("invariant")}
                        if prev_flags != {"companion_mode": False, "product_mode": True, "invariant": True} or curr_flags != {"companion_mode": False, "product_mode": True, "invariant": True}:
                            weakened["flags"].append({"id": nid, "prev": prev_flags, "curr": curr_flags})
                            errors.append(f"{nid} flags weakened: prev {prev_flags}, curr {curr_flags}")

            # Actions requirements (repo_mutation)
            repo_req_missing = []
            for nid, n in prev_nodes.items():
                if "Action" in n.get("labels", []) and nid == "action:repo_mutation":
                    prev_requires = set(n.get("props", {}).get("requires", []) or [])
                    curr_requires = set(curr_nodes.get(nid, {}).get("props", {}).get("requires", []) or [])
                    if "system:action_authorizer" in prev_requires and "system:action_authorizer" not in curr_requires:
                        repo_req_missing.append("system:action_authorizer")
                        errors.append("action:repo_mutation lost system:action_authorizer requirement")
                    if "gate:ci_strict_100" in prev_requires and "gate:ci_strict_100" not in curr_requires:
                        repo_req_missing.append("gate:ci_strict_100")
                        errors.append("action:repo_mutation lost gate:ci_strict_100 requirement")
            if repo_req_missing:
                removed["rules"] = sorted(set(repo_req_missing))

            # Bypass mitigations must not be weakened
            bypass_missing = []
            for nid, n in prev_nodes.items():
                if "BypassSurface" in n.get("labels", []):
                    prev_mit = set(n.get("props", {}).get("mitigations", []) or [])
                    curr_mit = set(curr_nodes.get(nid, {}).get("props", {}).get("mitigations", []) or [])
                    removed_mit = prev_mit - curr_mit
                    if removed_mit:
                        bypass_missing.append({"bypass": nid, "missing": sorted(removed_mit)})
                        errors.append(f"Bypass {nid} lost mitigations: {sorted(removed_mit)}")
            if bypass_missing:
                removed["bypass_mitigations"] = bypass_missing

            if errors:
                notes = []
                prev_hash = prev.get("constitutional_hash")
                curr_hash = seed.get("constitutional_hash")
                if not args.no_write_drift_report:
                    write_drift_report(
                        args.drift_report_out,
                        args.snapshot,
                        args.out,
                        prev_hash,
                        curr_hash,
                        {"removed": removed, "weakened": weakened},
                        notes,
                    )
                summary = (
                    f"CONSTITUTIONAL_DRIFT_DETECTED\n"
                    f"Removed invariants: {len(removed['invariants'])}\n"
                    f"Removed mandatory systems: {len(removed['systems'])}\n"
                    f"Removed constitutional edges: {len(removed['edges'])}\n"
                    f"Weakened repo_mutation requirements: {len(removed['rules'])}\n"
                    f"Missing bypass mitigations: {len(removed['bypass_mitigations'])}\n"
                    f"Severity weakened: {len(weakened['severity'])}\n"
                    f"Scope weakened: {len(weakened['scope'])}\n"
                    f"Flags weakened: {len(weakened['flags'])}"
                )
                if not args.no_write_drift_report:
                    summary += f"\nDrift report: {args.drift_report_out}"
                print(summary)
                raise SystemExit("CONSTITUTIONAL_DRIFT_DETECTED")

    except SystemExit:
        raise
    except Exception:
        # Fail-open for snapshot read issues but log
        print("Warning: anti-drift guard could not load snapshot; skipping", flush=True)

    # Save snapshot for next run
    try:
        ensure_dirs(args.snapshot)
        tmp_path = args.snapshot.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(seed, indent=2, ensure_ascii=True))
        tmp_path.replace(args.snapshot)  # atomic replace
    except Exception:
        print("Warning: could not write snapshot", flush=True)

    if not args.apply or args.dry_run:
        print("Seed generated (no DB apply):", args.out)
        return

    # Neo4j ingest (idempotent MERGE) if env vars present
    neo4j_uri = os.environ.get("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER")
    neo4j_pass = os.environ.get("NEO4J_PASSWORD")
    if not (neo4j_uri and neo4j_user and neo4j_pass):
        print("NEO4J env missing; generated seed only")
    else:
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
            with driver.session() as session:
                # MERGE nodes
                for node in seed.get("nodes", []):
                    nid = node["id"]
                    labels = ":".join(node.get("labels", ["Node"]))
                    props = node.get("props", {})
                    props_to_set = {k: v for k, v in props.items() if k != "id"}
                    props_str = ", ".join([f"{k}: ${k}" for k in props_to_set.keys()])
                    query = f"MERGE (n:{labels} {{id: $id}}) SET n += {{{props_str}}}"
                    session.run(query, id=nid, **props_to_set)
                # MERGE edges
                for edge in seed.get("edges", []):
                    frm = edge["from"]
                    rel = edge["type"]
                    to = edge["to"]
                    query = f"MATCH (a {{id: $from_id}}) MATCH (b {{id: $to_id}}) MERGE (a)-[:{rel}]->(b)"
                    session.run(query, from_id=frm, to_id=to)
            print("NEO4J seed injected successfully")
        except Exception as e:
            print(f"NEO4J inject failed: {e}")
        finally:
            if 'driver' in locals():
                driver.close()
        return

    # Placeholder: MERGE path to be added when HOLD lifts
    print("NEO4J apply requested but HOLD mode: skipping DB writes; seed at", args.out)


def sha_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
