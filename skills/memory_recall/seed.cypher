// Skill: memory_recall
// Version: 1.0.0
// Purpose: Recall information from episodic memory

MERGE (s:Skill:ExecutableSkill {skill_id: 'memory_recall'})
SET s.name = 'memory_recall',
    s.version = '1.0.0',
    s.description = 'Recall information from episodic memory and past conversations',
    s.capability = 'memory_retrieval',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.gating = 'fast_band',
    s.max_memories = 20,
    s.timeout_ms = 10000,
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

MERGE (i:Intent {name: 'remember'})
SET i.description = 'Intent to remember past conversations'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'recall_context'})
SET i2.description = 'Intent to recall context from memory'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (chain1:ToolchainStep {step_id: 'mem_step_1'})
SET chain1.name = 'query_memory', chain1.order = 1, chain1.timeout_ms = 10000
MERGE (s)-[:HAS_CHAIN]->(chain1)
MERGE (t1:Tool {name: 'neo4j_query'})
MERGE (chain1)-[:USES_TOOL]->(t1)

MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen3b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'smollm_node2'})

MERGE (ac:AtlasCollection {name: 'episodic_memory'})
MERGE (s)-[:USES_COLLECTION]->(ac)
MERGE (ac2:AtlasCollection {name: 'conversations'})
MERGE (s)-[:USES_COLLECTION]->(ac2)

MERGE (ml:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml)
MERGE (ml2:MemoryLayer {name: 'L3_EPISODIC'})
MERGE (s)-[:READS_FROM]->(ml2)

RETURN s.name, s.version
