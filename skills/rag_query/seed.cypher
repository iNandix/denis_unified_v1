// Skill: rag_query
// Version: 1.0.0
// Purpose: Query knowledge base using RAG

MERGE (s:Skill:ExecutableSkill {skill_id: 'rag_query'})
SET s.name = 'rag_query',
    s.version = '1.0.0',
    s.description = 'Query knowledge base using Retrieval Augmented Generation',
    s.capability = 'information_retrieval',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.gating = 'fast_band',
    s.max_results = 10,
    s.timeout_ms = 15000,
    s.created_at = datetime(),
    s.updated_at = datetime()
WITH s

MERGE (i:Intent {name: 'query_knowledge'})
SET i.description = 'Intent to query knowledge base'
MERGE (i)-[:ACTIVATES]->(s)

MERGE (i2:Intent {name: 'rag_search'})
SET i2.description = 'Intent to search with RAG'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {name: 'find_info'})
SET i3.description = 'Intent to find information'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (chain1:ToolchainStep {step_id: 'rag_step_1'})
SET chain1.name = 'embed_query', chain1.order = 1, chain1.timeout_ms = 5000
MERGE (s)-[:HAS_CHAIN]->(chain1)
MERGE (t1:Tool {name: 'embed_text'})
MERGE (chain1)-[:USES_TOOL]->(t1)

MERGE (chain2:ToolchainStep {step_id: 'rag_step_2'})
SET chain2.name = 'retrieve_context', chain2.order = 2, chain2.timeout_ms = 8000
MERGE (s)-[:HAS_CHAIN]->(chain2)
MERGE (t2:Tool {name: 'rag_query'})
MERGE (chain2)-[:USES_TOOL]->(t2)

MERGE (s)-[:PREFERS_ENGINE]->(e:Engine {name: 'qwen3b_local'})
MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'smollm_node2'})

MERGE (ac:AtlasCollection {name: 'knowledge_base'})
MERGE (s)-[:USES_COLLECTION]->(ac)
MERGE (ac2:AtlasCollection {name: 'system_config'})
MERGE (s)-[:USES_COLLECTION]->(ac2)

MERGE (ml:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml)

RETURN s.name, s.version
