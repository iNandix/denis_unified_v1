// =============================================================================
// CODECRAFT SKILL - Core Skill Definition
// =============================================================================

// Skill definition
MERGE (s:Skill {name: 'codecraft'})
SET s.version = '1.0.0',
    s.description = 'Enterprise code generation with reuse-first, chunk composition, and policy gating',
    s.status = 'active';

// Intents that activate codecraft
MERGE (i1:Intent {name: 'code_edit'})
MERGE (i1)-[:ACTIVATES]->(s);

MERGE (i2:Intent {name: 'implement_feature'})
MERGE (i2)-[:ACTIVATES]->(s);

MERGE (i3:Intent {name: 'refactor_code'})
MERGE (i3)-[:ACTIVATES]->(s);

MERGE (i4:Intent {name: 'add_tests'})
MERGE (i4)-[:ACTIVATES]->(s);

MERGE (i5:Intent {name: 'create_cli'})
MERGE (i5)-[:ACTIVATES]->(s);

MERGE (i6:Intent {name: 'integrate_api'})
MERGE (i6)-[:ACTIVATES]->(s);

MERGE (i7:Intent {name: 'improve_quality'})
MERGE (i7)-[:ACTIVATES]->(s);

MERGE (i8:Intent {name: 'scaffold_project'})
MERGE (i8)-[:ACTIVATES]->(s);

// =============================================================================
// CODE SPECIALTIES (4)
// =============================================================================

// Scaffold & Architecture
MERGE (sa:CodeSpecialty {id: 'scaffold_arch'})
SET sa.name = 'Scaffold & Architecture',
    sa.description = 'Project structure, modules, interfaces, boundaries, CI skeleton',
    sa.weight = 0.25;
MERGE (s)-[:HAS_SPECIALTY]->(sa);

// Implementation & Refactor
MERGE (ir:CodeSpecialty {id: 'impl_refactor'})
SET ir.name = 'Implementation & Refactor',
    ir.description = 'Feature implementation, refactoring, adapting existing code',
    ir.weight = 0.30;
MERGE (s)-[:HAS_SPECIALTY]->(ir);

// Integration & Tooling
MERGE (it:CodeSpecialty {id: 'integration_tooling'})
SET it.name = 'Integration & Tooling',
    it.description = 'APIs/SDKs, CLI, packaging, Docker, pipelines',
    it.weight = 0.25;
MERGE (s)-[:HAS_SPECIALTY]->(it);

// Quality & Reliability
MERGE (qr:CodeSpecialty {id: 'quality_reliability'})
SET qr.name = 'Quality & Reliability',
    qr.description = 'Tests, typing, lint, perf, security, observability',
    qr.weight = 0.20;
MERGE (s)-[:HAS_SPECIALTY]->(qr);

// =============================================================================
// TOOLCHAIN STEPS (10)
// =============================================================================

MERGE (ts1:ToolchainStep {step_id: 'cc_01_classify_request'})
SET ts1.name = 'classify_request',
    ts1.order = 1,
    ts1.required = true,
    ts1.output = 'classified_request_json';
MERGE (s)-[:HAS_STEP]->(ts1);

MERGE (ts2:ToolchainStep {step_id: 'cc_02_workspace_scan'})
SET ts2.name = 'workspace_scan',
    ts2.order = 2,
    ts2.required = true,
    ts2.output = 'workspace_index';
MERGE (s)-[:HAS_STEP]->(ts2);
MERGE (ts1)-[:NEXT_STEP]->(ts2);

MERGE (ts3:ToolchainStep {step_id: 'cc_03_retrieve_candidates'})
SET ts3.name = 'retrieve_candidates',
    ts3.order = 3,
    ts3.required = true,
    ts3.output = 'candidate_list',
    ts3.params = {sources: ['knowledge_base', 'local_repo', 'github', 'huggingface'], max_candidates: 50};
MERGE (s)-[:HAS_STEP]->(ts3);
MERGE (ts2)-[:NEXT_STEP]->(ts3);

MERGE (ts4:ToolchainStep {step_id: 'cc_04_rank_select'})
SET ts4.name = 'rank_and_select',
    ts4.order = 4,
    ts4.required = true,
    ts4.output = 'selected_reuse_or_chunks';
MERGE (s)-[:HAS_STEP]->(ts4);
MERGE (ts3)-[:NEXT_STEP]->(ts4);

MERGE (ts5:ToolchainStep {step_id: 'cc_05_plan_decompose'})
SET ts5.name = 'plan_decompose',
    ts5.order = 5,
    ts5.required = true,
    ts5.output = 'code_plan';
MERGE (s)-[:HAS_STEP]->(ts5);
MERGE (ts4)-[:NEXT_STEP]->(ts5);

MERGE (ts6:ToolchainStep {step_id: 'cc_06_compose'})
SET ts6.name = 'compose_from_chunks',
    ts6.order = 6,
    ts6.required = true,
    ts6.output = 'proposed_diff';
MERGE (s)-[:HAS_STEP]->(ts6);
MERGE (ts5)-[:NEXT_STEP]->(ts6);

MERGE (ts7:ToolchainStep {step_id: 'cc_07_apply_changes'})
SET ts7.name = 'apply_changes',
    ts7.order = 7,
    ts7.required = true,
    ts7.policy_gated = ['no_big_diff_v1', 'safety_code_exec_v1'];
MERGE (s)-[:HAS_STEP]->(ts7);
MERGE (ts6)-[:NEXT_STEP]->(ts7);

MERGE (ts8:ToolchainStep {step_id: 'cc_08_verify'})
SET ts8.name = 'verify',
    ts8.order = 8,
    ts8.required = true,
    ts8.policy_gated = ['test_gate_v1'];
MERGE (s)-[:HAS_STEP]->(ts8);
MERGE (ts7)-[:NEXT_STEP]->(ts8);

MERGE (ts9:ToolchainStep {step_id: 'cc_09_store_knowledge'})
SET ts9.name = 'store_knowledge',
    ts9.order = 9,
    ts9.required = false,
    ts9.conditional = 'learning_enabled==true';
MERGE (s)-[:HAS_STEP]->(ts9);
MERGE (ts8)-[:NEXT_STEP]->(ts9);

MERGE (ts10:ToolchainStep {step_id: 'cc_10_emit_decision_trace'})
SET ts10.name = 'emit_decision_trace',
    ts10.order = 10,
    ts10.required = true;
MERGE (s)-[:HAS_STEP]->(ts10);
MERGE (ts9)-[:NEXT_STEP]->(ts10);

// =============================================================================
// SOURCES
// =============================================================================

MERGE (src1:Source {id: 'local_repo'})
SET src1.type = 'workspace',
    src1.description = 'Current working repository and indexed files',
    src1.cost_units = 1,
    src1.requires_network = false;
MERGE (s)-[:USES_SOURCE]->(src1);

MERGE (src2:Source {id: 'knowledge_base'})
SET src2.type = 'graph',
    src2.description = 'Stored templates/chunks/snippets and prior results',
    src2.cost_units = 1,
    src2.requires_network = false;
MERGE (s)-[:USES_SOURCE]->(src2);

MERGE (src3:Source {id: 'github'})
SET src3.type = 'remote_code',
    src3.description = 'GitHub repos, code search, issues, releases',
    src3.cost_units = 4,
    src3.requires_network = true,
    src3.policy_gated = true;
MERGE (s)-[:USES_SOURCE]->(src3);

MERGE (src4:Source {id: 'huggingface'})
SET src4.type = 'remote_code',
    src4.description = 'HF repos/spaces/model cards/datasets',
    src4.cost_units = 4,
    src4.requires_network = true,
    src4.policy_gated = true;
MERGE (s)-[:USES_SOURCE]->(src4);

RETURN 'Codecraft skill, specialties, toolchain, and sources created';
