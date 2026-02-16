// =============================================================================
// CODECRAFT POLICIES
// =============================================================================

// License Policy
MERGE (lp:Policy {policy_id: 'license_policy_v1'})
SET lp.type = 'license',
    lp.name = 'License Policy',
    lp.allowlist = ['MIT', 'Apache-2.0', 'BSD-3-Clause', 'BSD-2-Clause', 'ISC', 'Python-2.0'],
    lp.denylist = ['GPL-3.0', 'AGPL-3.0', 'Proprietary', 'Unknown', 'CC-BY-NC-4.0'],
    lp.action_on_unknown = 'block_copy',
    lp.action_on_deny = 'block_copy';
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(lp);

// Reuse First Policy
MERGE (rp:Policy {policy_id: 'reuse_first_v1'})
SET rp.type = 'reuse',
    rp.name = 'Reuse First Policy',
    rp.description = 'Must run retrieval+ranking before generating new code',
    rp.threshold_reuse_score = 0.72,
    rp.block_generate_if_reuse_available = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(rp);

// Cost Policy
MERGE (cp:Policy {policy_id: 'cost_control_v1'})
SET cp.type = 'cost',
    cp.name = 'Cost Control Policy',
    cp.max_cost_units_per_request = 10,
    cp.prefer_light_engines_for_retrieval = true,
    cp.heavy_engine_only_for_synthesis = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(cp);

// Diff Policy (No Big Diff)
MERGE (dp:Policy {policy_id: 'no_big_diff_v1'})
SET dp.type = 'diff',
    dp.name = 'No Big Diff Policy',
    dp.max_added_lines = 300,
    dp.max_deleted_lines = 300,
    dp.require_approval_if_exceeded = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(dp);

// Test Gate Policy
MERGE (tg:Policy {policy_id: 'test_gate_v1'})
SET tg.type = 'test',
    tg.name = 'Test Gate Policy',
    tg.require_tests_pass = true,
    tg.allow_skip_with_approval = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(tg);

// Safety Policy (Tool Approval)
MERGE (sp:Policy {policy_id: 'safety_code_exec_v1'})
SET sp.type = 'safety',
    sp.name = 'Safety Code Exec Policy',
    sp.description = 'High-risk tools require human approval; read-only preferred',
    sp.enforce_tool_approval = true,
    sp.prefer_read_only = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(sp);

// Security Policy
MERGE (secp:Policy {policy_id: 'security_scan_v1'})
SET secp.type = 'security',
    secp.name = 'Security Scan Policy',
    secp.scan_for_vulnerabilities = true,
    secp.block_on_critical = true,
    secp.audit_dependencies = true;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(secp);

// Code Quality Policy
MERGE (qp:Policy {policy_id: 'code_quality_v1'})
SET qp.type = 'quality',
    qp.name = 'Code Quality Policy',
    qp.require_lint_clean = false,
    qp.require_type_hints = false,
    qp.min_coverage_percent = 0;
MERGE (:Skill {name: 'codecraft'})-[:HAS_POLICY]->(qp);

RETURN 'Codecraft policies created';
