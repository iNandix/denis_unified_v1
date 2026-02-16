// Skill: code_craft - Code Generation with Reuse-First Policy
// Version: 1.0.0
// Graph-centric, consumes PRO_SEARCH chunks

MERGE (s:Skill:ExecutableSkill {skill_id: 'code_craft'})
SET s.name = 'code_craft',
    s.version = '1.0.0',
    s.description = 'Code generation with reuse-first policy - consumes research chunks',
    s.capability = 'code_generation',
    s.policy = 'reuse_first',
    s.risk_level = 'medium',
    s.requires_approval = false,
    s.gating = 'fast_band',
    s.installed_at = datetime(),
    s.updated_at = datetime()
WITH s

// STRATEGIES
MERGE (strat1:GenerationStrategy {strategy_id: 'reuse'})
SET strat1.name = 'reuse', strat1.description = 'Reuse existing code from research chunks',
    strat1.priority = 1, strat1.license_check = true, strat1.risk_check = true
MERGE (s)-[:USES_STRATEGY]->(strat1)

MERGE (strat2:GenerationStrategy {strategy_id: 'adapt'})
SET strat2.name = 'adapt', strat2.description = 'Adapt existing code with modifications',
    strat2.priority = 2, strat2.license_check = true
MERGE (s)-[:USES_STRATEGY]->(strat2)

MERGE (strat3:GenerationStrategy {strategy_id: 'generate'})
SET strat3.name = 'generate', strat3.description = 'Generate new code from scratch',
    strat3.priority = 3
MERGE (s)-[:USES_STRATEGY]->(strat3)

// INPUTS (consumes from PRO_SEARCH)
MERGE (s)-[:CONSUMES]->(ps:InputSkill {skill_id: 'pro_search'})
MERGE (ps)-[:PRODUCES]->(:OutputType {type: 'chunk'})

// DATA TYPES (what code_craft prefers)
MERGE (dt1:PreferredDataType {data_type: 'CODE'})
MERGE (dt1)-[:HAS_PREFERENCE {score: 1.0}]->(strat1)
MERGE (dt1)-[:HAS_PREFERENCE {score: 0.9}]->(strat2)

MERGE (dt2:PreferredDataType {data_type: 'API_REF'})
MERGE (dt2)-[:HAS_PREFERENCE {score: 0.95}]->(strat1)
MERGE (dt2)-[:HAS_PREFERENCE {score: 0.8}]->(strat2)

MERGE (dt3:PreferredDataType {data_type: 'CONFIG'})
MERGE (dt3)-[:HAS_PREFERENCE {score: 0.9}]->(strat1)

MERGE (dt4:PreferredDataType {data_type: 'TUTORIAL'})
MERGE (dt4)-[:HAS_PREFERENCE {score: 0.7}]->(strat2)

// QUALITY GATES
MERGE (gate1:QualityGate {gate_id: 'license_check'})
SET gate1.name = 'license_check', gate1.description = 'Verify chunk has acceptable license',
    gate1.required_for_strategies = ['reuse', 'adapt'],
    gate1.allowed_licenses = ['MIT', 'Apache-2.0', 'BSD-3-Clause', 'GPL-3.0', 'LGPL-3.0'],
    gate1.blocking = true
MERGE (strat1)-[:HAS_GATE]->(gate1)
MERGE (strat2)-[:HAS_GATE]->(gate1)

MERGE (gate2:QualityGate {gate_id: 'risk_check'})
SET gate2.name = 'risk_check', gate2.description = 'Check chunk for unsafe code patterns',
    gate2.risk_flags_block = ['unsafe_code', 'malware_risk'],
    gate2.required_for_strategies = ['reuse', 'adapt'],
    gate2.blocking = true
MERGE (strat1)-[:HAS_GATE]->(gate2)
MERGE (strat2)-[:HAS_GATE]->(gate2)

MERGE (gate3:QualityGate {gate_id: 'verification_check'})
SET gate3.name = 'verification_check', gate3.description = 'Prefer verified chunks',
    gate3.min_verification = 'cross_verified',
    gate3.preferred = true,
    gate3.blocking = false
MERGE (strat1)-[:HAS_GATE]->(gate3)

MERGE (gate4:QualityGate {gate_id: 'freshness_check'})
SET gate4.name = 'freshness_check', gate4.description = 'Prefer fresh code',
    gate4.min_freshness = 0.5,
    gate4.blocking = false
MERGE (strat1)-[:HAS_GATE]->(gate4)

// UTILITY THRESHOLDS
MERGE (thresh1:UtilityThreshold {threshold_id: 'reuse_threshold'})
SET thresh1.name = 'reuse_threshold', thresh1.min_utility = 0.7,
    thresh1.description = 'Minimum utility to attempt reuse'
MERGE (s)-[:HAS_THRESHOLD]->(thresh1)

MERGE (thresh2:UtilityThreshold {threshold_id: 'generation_threshold'})
SET thresh2.name = 'generation_threshold', thresh2.min_utility = 0.3,
    thresh2.description = 'Minimum utility to consider chunk as context'
MERGE (s)-[:HAS_THRESHOLD]->(thresh2)

// ENGINE PREFERENCES
MERGE (s)-[:PREFERS_ENGINE]->(e1:Engine {name: 'qwen_coder7b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'qwen3b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e3:Engine {name: 'groq_booster'})

// INTENT PATTERNS
MERGE (i1:Intent {intent_id: 'write_code'})
SET i1.name = 'write_code', i1.description = 'Write new code'
MERGE (i1)-[:ACTIVATES]->(s)

MERGE (i2:Intent {intent_id: 'fix_bug'})
SET i2.name = 'fix_bug', i2.description = 'Fix a bug in existing code'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {intent_id: 'refactor_code'})
SET i3.name = 'refactor_code', i3.description = 'Refactor existing code'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (i4:Intent {intent_id: 'implement_feature'})
SET i4.name = 'implement_feature', i4.description = 'Implement a new feature'
MERGE (i4)-[:ACTIVATES]->(s)

MERGE (i5:Intent {intent_id: 'find_code'})
SET i5.name = 'find_code', i5.description = 'Find existing code snippets'
MERGE (i5)-[:ACTIVATES]->(s)

// OUTPUT TYPES
MERGE (out1:OutputType {type: 'code_snippet'})
MERGE (out1)-[:HAS_LICENSE {license: 'same_as_source'}]->(s)

MERGE (out2:OutputType {type: 'generated_code'})
MERGE (out2)-[:HAS_LICENSE {license: 'MIT'}]->(s)

RETURN s.name, s.version
