// Skill: multi_file_write
// Version: 1.0.0
// Purpose: Write multiple files in parallel for code generation
// Policy: mutating, requires approval for new files

// Skill node
MERGE (s:Skill:ExecutableSkill {skill_id: 'multi_file_write'})
SET s.name = 'multi_file_write',
    s.version = '1.0.0',
    s.description = 'Write multiple files in parallel for code generation',
    s.capability = 'file_writing',
    s.policy = 'mutating',
    s.risk_level = 'medium',
    s.requires_approval = true,
    s.max_files = 20,
    s.atomic = false,
    s.timeout_ms = 60000,
    s.gating = 'quality_band',
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

// Intent patterns that trigger this skill
MERGE (i:Intent {name: 'write_multiple_files'})
SET i.description = 'Intent to write multiple files'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'generate_code'})
SET i2.description = 'Intent to generate code files'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {name: 'scaffold_project'})
SET i3.description = 'Intent to scaffold a project structure'
MERGE (i3)-[:ACTIVATES]->(s)

// Toolchain definition
MERGE (chain:ToolchainStep {step_id: 'mfw_step_1', name: 'validate_paths'})
SET chain.order = 1,
    chain.timeout_ms = 3000
MERGE (s)-[:HAS_CHAIN]->(chain)

MERGE (t1:Tool {name: 'glob_files'})
SET t1.type = 'filesystem',
    t1.endpoint = 'local',
    t1.read_only = true,
    t1.timeout_ms = 3000
MERGE (chain)-[:USES_TOOL]->(t1)

MERGE (chain2:ToolchainStep {step_id: 'mfw_step_2', name: 'write_files'})
SET chain2.order = 2,
    chain2.parallel = true,
    chain2.timeout_ms = 30000
MERGE (s)-[:HAS_CHAIN]->(chain2)

MERGE (t2:Tool {name: 'write_file'})
SET t2.type = 'filesystem',
    t2.endpoint = 'local',
    t2.read_only = false,
    t2.mutating = true,
    t2.timeout_ms = 10000
MERGE (chain2)-[:USES_TOOL]->(t2)

MERGE (t3:Tool {name: 'file_write'})
SET t3.type = 'filesystem',
    t3.endpoint = 'local',
    t3.read_only = false,
    t3.mutating = true,
    t3.timeout_ms = 10000
MERGE (chain2)-[:USES_TOOL]->(t3)

MERGE (t4:Tool {name: 'edit_file'})
SET t4.type = 'filesystem',
    t4.endpoint = 'local',
    t4.read_only = false,
    t4.mutating = true,
    t4.timeout_ms = 10000
MERGE (chain2)-[:USES_TOOL]->(t4)

MERGE (chain3:ToolchainStep {step_id: 'mfw_step_3', name: 'verify_writes'})
SET chain3.order = 3,
    chain3.timeout_ms = 20000
MERGE (s)-[:HAS_CHAIN]->(chain3)

MERGE (t5:Tool {name: 'read_file'})
SET t5.type = 'filesystem',
    t5.endpoint = 'local',
    t5.read_only = true,
    t5.timeout_ms = 5000
MERGE (chain3)-[:USES_TOOL]->(t5)

// Engine preferences (quality models for code gen)
MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen_coder7b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'qwen15b_node2'})
MERGE (s)-[:PREFERS_ENGINE]->(e3:Engine {name: 'gemma_node2'})

// Atlas collections for templates
MERGE (ac:AtlasCollection {name: 'code_templates'})
MERGE (s)-[:USES_COLLECTION]->(ac)
MERGE (ac2:AtlasCollection {name: 'system_config'})
MERGE (s)-[:USES_COLLECTION]->(ac2)

// Observability: write to Turn and create audit trail
MERGE (s)-[:WRITES_TO]->(:MemoryLayer {name: 'Turn'})
MERGE (s)-[:WRITES_TO]->(:MemoryLayer {name: 'Episode'})
MERGE (s)-[:WRITES_TO]->(:MemoryLayer {name: 'audit_trail'})

RETURN s.name, s.version, s.policy
