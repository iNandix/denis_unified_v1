// Skill: git_operations
// Version: 1.0.0
// Purpose: Full git workflow (commit, branch, merge, PR)

MERGE (s:Skill:ExecutableSkill {skill_id: 'git_operations'})
SET s.name = 'git_operations',
    s.version = '1.0.0',
    s.description = 'Full git workflow operations (commit, branch, merge, PR)',
    s.capability = 'version_control',
    s.policy = 'mutating',
    s.risk_level = 'medium',
    s.requires_approval = true,
    s.gating = 'quality_band',
    s.operations = ['commit', 'branch', 'merge', 'rebase', 'pr'],
    s.timeout_ms = 30000,
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

MERGE (i:Intent {name: 'git_commit'})
SET i.description = 'Intent to commit changes'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'create_branch'})
SET i2.description = 'Intent to create a branch'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {name: 'git_merge'})
SET i3.description = 'Intent to merge branches'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (i4:Intent {name: 'git_pr'})
SET i4.description = 'Intent to create pull request'
MERGE (i4)-[:ACTIVATES]->(s)

MERGE (chain1:ToolchainStep {step_id: 'git_step_1'})
SET chain1.name = 'git_status', chain1.order = 1, chain1.timeout_ms = 5000
MERGE (s)-[:HAS_CHAIN]->(chain1)
MERGE (t1:Tool {name: 'git'})
MERGE (chain1)-[:USES_TOOL]->(t1)
MERGE (t2:Tool {name: 'git_exec'})
MERGE (chain1)-[:USES_TOOL]->(t2)

MERGE (chain2:ToolchainStep {step_id: 'git_step_2'})
SET chain2.name = 'git_diff', chain2.order = 2, chain2.timeout_ms = 5000
MERGE (s)-[:HAS_CHAIN]->(chain2)
MERGE (t3:Tool {name: 'git'})
MERGE (chain2)-[:USES_TOOL]->(t3)

MERGE (chain3:ToolchainStep {step_id: 'git_step_3'})
SET chain3.name = 'git_operation', chain3.order = 3, chain3.timeout_ms = 20000
MERGE (s)-[:HAS_CHAIN]->(chain3)
MERGE (t4:Tool {name: 'git_exec'})
MERGE (chain3)-[:USES_TOOL]->(t4)

MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen_coder7b_local'})

MERGE (ml:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml)
MERGE (ml2:MemoryLayer {name: 'L3_EPISODIC'})
MERGE (s)-[:WRITES_TO]->(ml2)
MERGE (ml3:MemoryLayer {name: 'audit_trail'})
MERGE (s)-[:WRITES_TO]->(ml3)

RETURN s.name, s.version
