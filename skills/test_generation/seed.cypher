// Skill: test_generation
// Version: 1.0.0
// Purpose: Generate unit and integration tests from source code

MERGE (s:Skill:ExecutableSkill {skill_id: 'test_generation'})
SET s.name = 'test_generation',
    s.version = '1.0.0',
    s.description = 'Generate unit and integration tests from source code',
    s.capability = 'code_testing',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.gating = 'fast_band',
    s.test_types = ['unit', 'integration', 'e2e'],
    s.timeout_ms = 60000,
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

MERGE (i:Intent {name: 'write_tests'})
SET i.description = 'Intent to write tests for code'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'generate_tests'})
SET i2.description = 'Intent to generate test cases'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {name: 'add_test_coverage'})
SET i3.description = 'Intent to add test coverage'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (chain1:ToolchainStep {step_id: 'tg_step_1'})
SET chain1.name = 'analyze_code', chain1.order = 1, chain1.timeout_ms = 10000
MERGE (s)-[:HAS_CHAIN]->(chain1)
MERGE (t1:Tool {name: 'glob_files'})
MERGE (chain1)-[:USES_TOOL]->(t1)
MERGE (t2:Tool {name: 'file_read'})
MERGE (chain1)-[:USES_TOOL]->(t2)

MERGE (chain2:ToolchainStep {step_id: 'tg_step_2'})
SET chain2.name = 'generate_tests', chain2.order = 2, chain2.timeout_ms = 40000
MERGE (s)-[:HAS_CHAIN]->(chain2)
MERGE (t3:Tool {name: 'python_exec'})
MERGE (chain2)-[:USES_TOOL]->(t3)
MERGE (t4:Tool {name: 'code_executor'})
MERGE (chain2)-[:USES_TOOL]->(t4)

MERGE (chain3:ToolchainStep {step_id: 'tg_step_3'})
SET chain3.name = 'write_test_files', chain3.order = 3, chain3.timeout_ms = 10000
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

RETURN s.name, s.version
