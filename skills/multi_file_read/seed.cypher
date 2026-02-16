// Skill: multi_file_read
// Version: 1.0.0
// Purpose: Read multiple files in parallel for context gathering
// Policy: read_only, no approval required

// Skill node
MERGE (s:Skill:ExecutableSkill {skill_id: 'multi_file_read'})
SET s.name = 'multi_file_read',
    s.version = '1.0.0',
    s.description = 'Read multiple files in parallel for context gathering',
    s.capability = 'file_reading',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.max_files = 50,
    s.timeout_ms = 30000,
    s.gating = 'fast_band',
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

// Intent patterns that trigger this skill
MERGE (i:Intent {name: 'read_multiple_files'})
SET i.description = 'Intent to read multiple source files'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'gather_context'})
SET i2.description = 'Intent to gather code context from multiple files'
MERGE (i2)-[:ACTIVATES]->(s)

// Toolchain definition
MERGE (chain:ToolchainStep {step_id: 'mfr_step_1', name: 'glob_files'})
SET chain.order = 1,
    chain.parallel = true,
    chain.timeout_ms = 5000
MERGE (s)-[:HAS_CHAIN]->(chain)

MERGE (t1:Tool {name: 'glob_files'})
SET t1.type = 'filesystem',
    t1.endpoint = 'local',
    t1.read_only = true,
    t1.timeout_ms = 5000
MERGE (chain)-[:USES_TOOL]->(t1)

MERGE (chain2:ToolchainStep {step_id: 'mfr_step_2', name: 'read_files'})
SET chain2.order = 2,
    chain2.parallel = true,
    chain2.timeout_ms = 25000
MERGE (s)-[:HAS_CHAIN]->(chain2)

MERGE (t2:Tool {name: 'read_file'})
SET t2.type = 'filesystem',
    t2.endpoint = 'local',
    t2.read_only = true,
    t2.timeout_ms = 5000
MERGE (chain2)-[:USES_TOOL]->(t2)

MERGE (t3:Tool {name: 'file_read'})
SET t3.type = 'filesystem',
    t3.endpoint = 'local',
    t3.read_only = true,
    t3.timeout_ms = 5000
MERGE (chain2)-[:USES_TOOL]->(t3)

// Engine preferences (local only for speed)
MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen_coder7b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'qwen3b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e3:Engine {name: 'smollm_node2'})

// Atlas collections for templates/knowledge
MERGE (ac:AtlasCollection {name: 'code_templates'})
MERGE (s)-[:USES_COLLECTION]->(ac)
MERGE (ac2:AtlasCollection {name: 'knowledge_base'})
MERGE (s)-[:USES_COLLECTION]->(ac2)
MERGE (ac3:AtlasCollection {name: 'system_config'})
MERGE (s)-[:USES_COLLECTION]->(ac3)

// Observability: write to Turn for context
MERGE (s)-[:WRITES_TO]->(:MemoryLayer {name: 'Turn'})
MERGE (s)-[:WRITES_TO]->(:MemoryLayer {name: 'Episode'})

RETURN s.name, s.version, s.policy
