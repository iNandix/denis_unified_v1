// Skill: pro_search - Research OS for DENIS
// Version: 2.0.0
// Full graph-centric, zero hardcode

MERGE (s:Skill:ExecutableSkill {skill_id: 'pro_search'})
SET s.name = 'pro_search',
    s.version = '2.0.0',
    s.description = 'Research OS - Multi-depth, multi-mode web research framework',
    s.capability = 'web_research',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.gating = 'fast_band',
    s.installed_at = datetime(),
    s.updated_at = datetime()
WITH s

// ENGINE TYPES
MERGE (et1:EngineType {type_id: 'llm'}) ON CREATE SET et1.description = 'Language model for synthesis'
MERGE (et2:EngineType {type_id: 'search'}) ON CREATE SET et2.description = 'Web search engine'
MERGE (et3:EngineType {type_id: 'scraper'}) ON CREATE SET et3.description = 'Web content extractor'
MERGE (et4:EngineType {type_id: 'verifier'}) ON CREATE SET et4.description = 'Fact verification engine'

// SEARCH MODES
MERGE (mode1:SearchMode {mode_id: 'user_pure'})
ON CREATE SET mode1.name = 'user_pure', mode1.description = 'Natural language for end users',
    mode1.query_type = 'user', mode1.language = 'natural', mode1.synthesis_style = 'conversational',
    mode1.citations = true, mode1.streaming = true, mode1.approval_required = false
MERGE (s)-[:HAS_MODE]->(mode1)

MERGE (mode2:SearchMode {mode_id: 'hybrid'})
ON CREATE SET mode2.name = 'hybrid', mode2.description = 'Natural + structured for denis-agent',
    mode2.query_type = 'agent', mode2.language = 'hybrid', mode2.synthesis_style = 'detailed',
    mode2.citations = true, mode2.context_aware = true, mode2.learning_enabled = true,
    mode2.approval_required = false
MERGE (s)-[:HAS_MODE]->(mode2)

MERGE (mode3:SearchMode {mode_id: 'machine_only'})
ON CREATE SET mode3.name = 'machine_only', mode3.description = 'Structured JSON for internal learning',
    mode3.query_type = 'system', mode3.language = 'structured', mode3.synthesis_style = 'json',
    mode3.citations = true, mode3.learning_enabled = true, mode3.feeds_graph = true,
    mode3.output_format = 'json', mode3.approval_required = false
MERGE (s)-[:HAS_MODE]->(mode3)

// DEPTHS
MERGE (depth1:SearchDepth {depth_id: 'quick'})
ON CREATE SET depth1.name = 'quick', depth1.time_limit_ms = 30000, depth1.max_sources = 5,
    depth1.max_cost_units = 1, depth1.expanded_queries = 3
MERGE (s)-[:HAS_DEPTH]->(depth1)

MERGE (depth2:SearchDepth {depth_id: 'standard'})
ON CREATE SET depth2.name = 'standard', depth2.time_limit_ms = 180000, depth2.max_sources = 15,
    depth2.max_cost_units = 5, depth2.expanded_queries = 7
MERGE (s)-[:HAS_DEPTH]->(depth2)

MERGE (depth3:SearchDepth {depth_id: 'deep'})
ON CREATE SET depth3.name = 'deep', depth3.time_limit_ms = 900000, depth3.max_sources = 50,
    depth3.max_cost_units = 20, depth3.expanded_queries = 15, depth3.cross_verify_min = 3,
    depth3.rerank = true
MERGE (s)-[:HAS_DEPTH]->(depth3)

MERGE (depth4:SearchDepth {depth_id: 'continuous'})
ON CREATE SET depth4.name = 'continuous', depth4.time_limit_ms = 0, depth4.max_sources = 999,
    depth4.max_cost_units = 100, depth4.continuous = true, depth4.alert_threshold = 0.8
MERGE (s)-[:HAS_DEPTH]->(depth4)

// CATEGORIES
MERGE (cat1:SearchCategory {category_id: 'general'})
ON CREATE SET cat1.name = 'general', cat1.engines = ['google','bing','duckduckgo'], cat1.priority = 1
MERGE (s)-[:HAS_CATEGORY]->(cat1)

MERGE (cat2:SearchCategory {category_id: 'academic'})
ON CREATE SET cat2.name = 'academic', cat2.engines = ['arxiv','scholar','pubmed'], cat2.priority = 2,
    cat2.min_cross_verify = 3
MERGE (s)-[:HAS_CATEGORY]->(cat2)

MERGE (cat3:SearchCategory {category_id: 'technical'})
ON CREATE SET cat3.name = 'technical', cat3.engines = ['stackoverflow','github','readthedocs'], cat3.priority = 2
MERGE (s)-[:HAS_CATEGORY]->(cat3)

MERGE (cat4:SearchCategory {category_id: 'news'})
ON CREATE SET cat4.name = 'news', cat4.engines = ['newsapi','newsgoogle'], cat4.priority = 1,
    cat4.recency_weight = 0.8
MERGE (s)-[:HAS_CATEGORY]->(cat4)

MERGE (cat5:SearchCategory {category_id: 'video'})
ON CREATE SET cat5.name = 'video', cat5.engines = ['youtube','vimeo'], cat5.priority = 1
MERGE (s)-[:HAS_CATEGORY]->(cat5)

MERGE (cat6:SearchCategory {category_id: 'reddit'})
ON CREATE SET cat6.name = 'reddit', cat6.engines = ['reddit'], cat6.priority = 1,
    cat6.sentiment_analysis = true
MERGE (s)-[:HAS_CATEGORY]->(cat6)

// POLICIES
MERGE (pol1:Policy {policy_id: 'deep_mode_policy'})
ON CREATE SET pol1.name = 'deep_mode_policy', pol1.description = 'Deep mode requires cross-verification',
    pol1.rule = 'cross_verify_min >= 3', pol1.blocks_execution = true
MERGE (mode3)-[:HAS_POLICY]->(pol1)
MERGE (depth3)-[:HAS_POLICY]->(pol1)

MERGE (pol2:Policy {policy_id: 'cost_control'})
ON CREATE SET pol2.name = 'cost_control', pol2.description = 'Limit cost units per search',
    pol2.rule = 'cost_units <= max_cost_units', pol2.blocks_execution = true
MERGE (s)-[:HAS_POLICY]->(pol2)

MERGE (pol3:Policy {policy_id: 'source_diversity'})
ON CREATE SET pol3.name = 'source_diversity', pol3.description = 'Require diverse sources for academic',
    pol3.rule = 'min_unique_domains >= 3', pol3.category_filter = 'academic'
MERGE (cat2)-[:HAS_POLICY]->(pol3)

// TOOLCHAIN
MERGE (step1:ToolchainStep {step_id: 'ps_01_classify'})
ON CREATE SET step1.name = 'classify_query', step1.order = 1, step1.timeout_ms = 1000,
    step1.required = true, step1.retry_on_fail = false
MERGE (s)-[:HAS_STEP]->(step1)

MERGE (t1:Tool {tool_id: 'intent_classifier'})
ON CREATE SET t1.name = 'intent_classifier', t1.type = 'classifier', t1.engine_type = 'llm', t1.timeout_ms = 1000
MERGE (step1)-[:USES_TOOL]->(t1)

MERGE (step2:ToolchainStep {step_id: 'ps_02_expand'})
ON CREATE SET step2.name = 'expand_query', step2.order = 2, step2.timeout_ms = 5000,
    step2.required = true, step2.retry_on_fail = true
MERGE (s)-[:HAS_STEP]->(step2)

MERGE (t2:Tool {tool_id: 'query_expander'})
ON CREATE SET t2.name = 'query_expander', t2.type = 'llm_processor', t2.engine_type = 'llm', t2.timeout_ms = 5000
MERGE (step2)-[:USES_TOOL]->(t2)

MERGE (step3:ToolchainStep {step_id: 'ps_03_search'})
ON CREATE SET step3.name = 'multi_engine_search', step3.order = 3, step3.timeout_ms = 15000,
    step3.required = true, step3.retry_on_fail = true, step3.parallel = true
MERGE (s)-[:HAS_STEP]->(step3)

MERGE (t3:Tool {tool_id: 'searxng_search'})
ON CREATE SET t3.name = 'searxng_search', t3.type = 'search', t3.engine_type = 'search', t3.timeout_ms = 10000
MERGE (step3)-[:USES_TOOL]->(t3)

MERGE (t4:Tool {tool_id: 'web_fetch'})
ON CREATE SET t4.name = 'web_fetch', t4.type = 'scraper', t4.engine_type = 'scraper', t4.timeout_ms = 8000
MERGE (step3)-[:USES_TOOL]->(t4)

MERGE (step4:ToolchainStep {step_id: 'ps_04_verify'})
ON CREATE SET step4.name = 'evaluate_sources', step4.order = 4, step4.timeout_ms = 8000,
    step4.required = true, step4.retry_on_fail = false
MERGE (s)-[:HAS_STEP]->(step4)

MERGE (t5:Tool {tool_id: 'reliability_scorer'})
ON CREATE SET t5.name = 'reliability_scorer', t5.type = 'verifier', t5.engine_type = 'verifier', t5.timeout_ms = 3000
MERGE (step4)-[:USES_TOOL]->(t5)

MERGE (t6:Tool {tool_id: 'fact_verifier'})
ON CREATE SET t6.name = 'fact_verifier', t6.type = 'verifier', t6.engine_type = 'verifier', t6.timeout_ms = 5000
MERGE (step4)-[:USES_TOOL]->(t6)

MERGE (step5:ToolchainStep {step_id: 'ps_05_synthesize'})
ON CREATE SET step5.name = 'synthesize_results', step5.order = 5, step5.timeout_ms = 15000,
    step5.required = true, step5.retry_on_fail = true, step5.streaming = true
MERGE (s)-[:HAS_STEP]->(step5)

MERGE (t7:Tool {tool_id: 'llm_synthesizer'})
ON CREATE SET t7.name = 'llm_synthesizer', t7.type = 'llm_processor', t7.engine_type = 'llm',
    t7.timeout_ms = 15000, t7.streaming = true
MERGE (step5)-[:USES_TOOL]->(t7)

MERGE (step6:ToolchainStep {step_id: 'ps_06_store'})
ON CREATE SET step6.name = 'store_knowledge', step6.order = 6, step6.timeout_ms = 5000,
    step6.required = false, step6.conditional = 'learning_enabled = true'
MERGE (s)-[:HAS_STEP]->(step6)

MERGE (t8:Tool {tool_id: 'knowledge_graph_writer'})
ON CREATE SET t8.name = 'knowledge_graph_writer', t8.type = 'graph_writer', t8.engine_type = 'llm', t8.timeout_ms = 5000
MERGE (step6)-[:USES_TOOL]->(t8)

// ENGINE PREFERENCES
MERGE (s)-[:PREFERS_ENGINE]->(e1:Engine {name: 'qwen3b_local'})
MERGE (e1)-[:HAS_TYPE]->(et1)

MERGE (s)-[:PREFERS_ENGINE]->(e2:Engine {name: 'smollm_node2'})
MERGE (e2)-[:HAS_TYPE]->(et1)

MERGE (s)-[:PREFERS_ENGINE]->(e3:Engine {name: 'groq_booster'})
MERGE (e3)-[:HAS_TYPE]->(et1)

MERGE (s)-[:USES_SEARCH_ENGINE]->(se1:SearchEngine {name: 'searxng_local'})
MERGE (se1)-[:HAS_TYPE]->(et2)

MERGE (s)-[:USES_SEARCH_ENGINE]->(se2:SearchEngine {name: 'brave_search'})
MERGE (se2)-[:HAS_TYPE]->(et2)

// INTENTS
MERGE (i1:Intent {intent_id: 'research'})
ON CREATE SET i1.name = 'research', i1.description = 'General research intent'
MERGE (i1)-[:ACTIVATES]->(s)

MERGE (i2:Intent {intent_id: 'find_info'})
ON CREATE SET i2.name = 'find_information', i2.description = 'Find specific information'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {intent_id: 'learn_topic'})
ON CREATE SET i3.name = 'learn_topic', i3.description = 'Learn and store in graph'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (i4:Intent {intent_id: 'analyze_market'})
ON CREATE SET i4.name = 'analyze_market', i4.description = 'Market/competitive analysis'
MERGE (i4)-[:ACTIVATES]->(s)

MERGE (i5:Intent {intent_id: 'verify_fact'})
ON CREATE SET i5.name = 'verify_fact', i5.description = 'Fact verification'
MERGE (i5)-[:ACTIVATES]->(s)

// COLLECTIONS & MEMORY
MERGE (ac1:AtlasCollection {name: 'knowledge_base'})
MERGE (s)-[:USES_COLLECTION]->(ac1)

MERGE (ml1:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml1)

MERGE (ml2:MemoryLayer {name: 'L3_EPISODIC'})
MERGE (s)-[:WRITES_TO]->(ml2)

MERGE (ml3:MemoryLayer {name: 'L5_SEMANTIC'})
MERGE (s)-[:WRITES_TO]->(ml3)

RETURN s.name, s.version
