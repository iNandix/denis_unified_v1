// Skill: refactor_code
// Version: 1.0.0
// Purpose: Refactor existing code for better quality

MERGE (s:Skill:ExecutableSkill {skill_id: 'refactor_code'})
SET s.name = 'refactor_code',
    s.version = '1.0.0',
    s.description = 'Refactor existing code for better quality, readability and performance',
    s.capability = 'code_refactoring',
    s.policy = 'mutating',
    s.risk_level = 'medium',
    s.requires_approval = true,
    s.gating = 'quality_band',
    s.refactor_types = ['extract_method', 'rename', 'simplify', 'optimize'],
    s.timeout_ms = 90000,
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

MERGE (i:Intent {name: 'refactor'})
SET i.description = 'Intent to refactor code'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'improve_code'})
SET i2.description = 'Intent to improve code quality'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (chain1:ToolchainStep {step_id: 'ref_step_1'})
SET chain1.name = 'analyze_code', chain1.order = 1, chain1.timeout_ms = 15000
MERGE (s)-[:HAS_CHAIN]->(chain1)
MERGE (t1:Tool {name: 'glob_files'})
MERGE (chain1)-[:USES_TOOL]->(t1)
MERGE (t2:Tool {name: 'file_read'})
MERGE (chain1)-[:USES_TOOL]->(t2)

MERGE (chain2:ToolchainStep {step_id: 'ref_step_2'})
SET chain2.name = 'generate_refactor', chain2.order = 2, chain2.timeout_ms = 60000
MERGE (s)-[:HAS_CHAIN]->(chain2)
MERGE (t3:Tool {name: 'python_exec'})
MERGE (chain2)-[:USES_TOOL]->(t3)
MERGE (t4:Tool {name: 'code_executor'})
MERGE (chain2)-[:USES_TOOL]->(t4)

MERGE (chain3:ToolchainStep {step_id: 'ref_step_3'})
SET chain3.name = 'apply_refactor', chain3.order = 3, chain3.timeout_ms = 15000
MERGE (s)-[:HAS_CHAIN]->(chain3)
MERGE (t5:Tool {name: 'write_file'})
MERGE (chain3)-[:USES_TOOL]->(t5)

MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen_coder7b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'qwen15b_node2'})
MERGE (s)-[:PREFERS_ENGINE]->(e3:Engine {name: 'gemma_node2'})

MERGE (ac:AtlasCollection {name: 'code_templates'})
MERGE (s)-[:USES_COLLECTION]->(ac)

MERGE (ml:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml)
MERGE (ml2:MemoryLayer {name: 'L3_EPISODIC'})
MERGE (s)-[:WRITES_TO]->(ml2)
MERGE (ml3:MemoryLayer {name: 'audit_trail'})
MERGE (s)-[:WRITES_TO]->(ml3)

RETURN s.name, s.version
