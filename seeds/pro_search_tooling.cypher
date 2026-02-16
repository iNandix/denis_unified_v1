// ============================================================
// PRO_SEARCH v2.0 - Tooling Seed
// Tools used by toolchain steps with normalized properties
// ============================================================

// TOOLS FOR STEP 1: CLASSIFY
MERGE (t1:Tool {tool_id: 'query_classifier'})
SET t1.name = 'query_classifier',
    t1.type = 'classifier',
    t1.method = 'llm_classify',
    t1.engine_type = 'llm',
    t1.timeout_s = 1,
    t1.retries = 0,
    t1.risk_level = 'low',
    t1.read_only = true

// TOOLS FOR STEP 2: EXPAND
MERGE (t2:Tool {tool_id: 'query_expander'})
SET t2.name = 'query_expander',
    t2.type = 'llm_processor',
    t2.method = 'llm_expand',
    t2.engine_type = 'llm',
    t2.timeout_s = 5,
    t2.retries = 1,
    t2.risk_level = 'low',
    t2.read_only = true,
    t2.params = '{ "expansions": 5, "generate_variants": true }'

// TOOLS FOR STEP 3: SEARCH
MERGE (t3:Tool {tool_id: 'searxng_search'})
SET t3.name = 'searxng_search',
    t3.type = 'search',
    t3.method = 'http_api',
    t3.engine_type = 'search',
    t3.endpoint = 'searxng_local',
    t3.timeout_s = 10,
    t3.retries = 2,
    t3.risk_level = 'low',
    t3.read_only = true,
    t3.rate_limit_rpm = 60

MERGE (t4:Tool {tool_id: 'web_fetch'})
SET t4.name = 'web_fetch',
    t4.type = 'scraper',
    t4.method = 'http_fetch',
    t4.engine_type = 'scraper',
    t4.timeout_s = 8,
    t4.retries = 1,
    t4.risk_level = 'medium',
    t4.read_only = true,
    t4.max_content_size_mb = 5,
    t4.user_agent = 'Denis/1.0'

MERGE (t5:Tool {tool_id: 'brave_search'})
SET t5.name = 'brave_search',
    t5.type = 'search',
    t5.method = 'http_api',
    t5.engine_type = 'search',
    t5.endpoint = 'brave_api',
    t5.timeout_s = 10,
    t5.retries = 1,
    t5.risk_level = 'low',
    t5.read_only = true,
    t5.requires_api_key = true

// TOOLS FOR STEP 4: VERIFY
MERGE (t6:Tool {tool_id: 'reliability_scorer'})
SET t6.name = 'reliability_scorer',
    t6.type = 'verifier',
    t6.method = 'llm_score',
    t6.engine_type = 'llm',
    t6.timeout_s = 3,
    t6.retries = 0,
    t6.risk_level = 'low',
    t6.read_only = true,
    t6.scoring_criteria = 'domain_trust,https,author_verified,date_freshness,bias'

MERGE (t7:Tool {tool_id: 'fact_verifier'})
SET t7.name = 'fact_verifier',
    t7.type = 'verifier',
    t7.method = 'cross_reference',
    t7.engine_type = 'verifier',
    t7.timeout_s = 5,
    t7.retries = 0,
    t7.risk_level = 'low',
    t7.read_only = true,
    t7.min_sources_for_verify = 3

MERGE (t8:Tool {tool_id: 'bias_detector'})
SET t8.name = 'bias_detector',
    t8.type = 'verifier',
    t8.method = 'llm_analyze',
    t8.engine_type = 'llm',
    t8.timeout_s = 3,
    t8.retries = 0,
    t8.risk_level = 'low',
    t8.read_only = true

// TOOLS FOR STEP 5: SYNTHESIZE
MERGE (t9:Tool {tool_id: 'llm_synthesizer'})
SET t9.name = 'llm_synthesizer',
    t9.type = 'llm_processor',
    t9.method = 'llm_synthesize',
    t9.engine_type = 'llm',
    t9.timeout_s = 15,
    t9.retries = 1,
    t9.risk_level = 'low',
    t9.read_only = true,
    t9.streaming = true,
    t9.output_modes = 'conversational,detailed,json,summary,comparative,timeline'

// TOOLS FOR STEP 6: STORE
MERGE (t10:Tool {tool_id: 'knowledge_graph_writer'})
SET t10.name = 'knowledge_graph_writer',
    t10.type = 'graph_writer',
    t10.method = 'neo4j_write',
    t10.engine_type = 'llm',
    t10.timeout_s = 5,
    t10.retries = 1,
    t10.risk_level = 'medium',
    t10.read_only = false,
    t10.writes_nodes = 'SearchRequest,Result,Source,URL,Claim,Verification,ReliabilityScore'

// LINK TOOLS TO STEPS
MATCH (step1:ToolchainStep {step_id: 'ps_01_classify'})
MERGE (t1)-[:FOR_STEP]->(step1)

MATCH (step2:ToolchainStep {step_id: 'ps_02_expand'})
MERGE (t2)-[:FOR_STEP]->(step2)

MATCH (step3:ToolchainStep {step_id: 'ps_03_search'})
MERGE (t3)-[:FOR_STEP]->(step3)
MERGE (t4)-[:FOR_STEP]->(step3)
MERGE (t5)-[:FOR_STEP]->(step3)

MATCH (step4:ToolchainStep {step_id: 'ps_04_verify'})
MERGE (t6)-[:FOR_STEP]->(step4)
MERGE (t7)-[:FOR_STEP]->(step4)
MERGE (t8)-[:FOR_STEP]->(step4)

MATCH (step5:ToolchainStep {step_id: 'ps_05_synthesize'})
MERGE (t9)-[:FOR_STEP]->(step5)

MATCH (step6:ToolchainStep {step_id: 'ps_06_store'})
MERGE (t10)-[:FOR_STEP]->(step6)

RETURN 'tools seeded' as result
