// ============================================================
// PRO_SEARCH v2.0 - Complete Seed
// Skill catalog nodes and relationships
// ============================================================

// SKILL
MERGE (s:Skill:ExecutableSkill {skill_id: 'pro_search'})
SET s.name = 'pro_search',
    s.version = '2.0.0',
    s.description = 'Research OS graph-centric: multi-engine search, verification, synthesis, graph storage.',
    s.capability = 'web_research',
    s.policy = 'read_only',
    s.risk_level = 'low',
    s.requires_approval = false,
    s.status = 'stable',
    s.owner = 'denis',
    s.created_at = datetime(),
    s.updated_at = datetime()

// ============================================================
// SEARCH MODES (query_types)
// ============================================================

MERGE (mode1:SearchMode {mode_id: 'user_pure'})
SET mode1.name = 'user_pure',
    mode1.query_type = 'user',
    mode1.language = 'natural',
    mode1.synthesis_style = 'conversational',
    mode1.output = 'streamed_text + citations',
    mode1.example = 'Denis, qué opinas sobre las últimas noticias de IA?'
MERGE (s)-[:HAS_MODE]->(mode1)

MERGE (mode2:SearchMode {mode_id: 'hybrid'})
SET mode2.name = 'hybrid',
    mode2.query_type = 'agent',
    mode2.language = 'hybrid',
    mode2.synthesis_style = 'detailed',
    mode2.output = 'streamed_text + citations + internal_notes',
    mode2.context_aware = true,
    mode2.learning_enabled = true,
    mode2.example = 'Agent consultando + sintetizando con conocimiento existente'
MERGE (s)-[:HAS_MODE]->(mode2)

MERGE (mode3:SearchMode {mode_id: 'machine_only'})
SET mode3.name = 'machine_only',
    mode3.query_type = 'system',
    mode3.language = 'structured',
    mode3.synthesis_style = 'json',
    mode3.output = 'json',
    mode3.learning_enabled = true,
    mode3.feeds_graph = true,
    mode3.output_format = 'json',
    mode3.example = '{"query": "docker best practices", "mode": "learning", "store": true}'
MERGE (s)-[:HAS_MODE]->(mode3)

// ============================================================
// SEARCH DEPTHS
// ============================================================

MERGE (depth1:SearchDepth {depth_id: 'quick'})
SET depth1.name = 'quick',
    depth1.max_sources = 5,
    depth1.time_budget_ms = 30000,
    depth1.cross_verify_min = 1,
    depth1.use_case = 'Verificación rápida, preguntas simples'
MERGE (s)-[:HAS_DEPTH]->(depth1)

MERGE (depth2:SearchDepth {depth_id: 'standard'})
SET depth2.name = 'standard',
    depth2.max_sources = 15,
    depth2.time_budget_ms = 180000,
    depth2.cross_verify_min = 2,
    depth2.use_case = 'Investigación normal'
MERGE (s)-[:HAS_DEPTH]->(depth2)

MERGE (depth3:SearchDepth {depth_id: 'deep'})
SET depth3.name = 'deep',
    depth3.max_sources = 50,
    depth3.time_budget_ms = 900000,
    depth3.cross_verify_min = 3,
    depth3.rerank = true,
    depth3.use_case = 'Análisis exhaustivo'
MERGE (s)-[:HAS_DEPTH]->(depth3)

MERGE (depth4:SearchDepth {depth_id: 'continuous'})
SET depth4.name = 'continuous',
    depth4.max_sources = 0,
    depth4.time_budget_ms = 0,
    depth4.cross_verify_min = 2,
    depth4.schedule_enabled = false,
    depth4.rrule = 'FREQ=HOURLY',
    depth4.use_case = 'Monitoreo 24/7'
MERGE (s)-[:HAS_DEPTH]->(depth4)

// ============================================================
// SEARCH CATEGORIES
// ============================================================

MERGE (cat1:SearchCategory {category_id: 'general'})
SET cat1.name = 'general',
    cat1.engines = ['google','bing','duckduckgo'],
    cat1.priority = 1
MERGE (s)-[:HAS_CATEGORY]->(cat1)

MERGE (cat2:SearchCategory {category_id: 'academic'})
SET cat2.name = 'academic',
    cat2.engines = ['arxiv','scholar','pubmed'],
    cat2.priority = 2,
    cat2.min_cross_verify = 3
MERGE (s)-[:HAS_CATEGORY]->(cat2)

MERGE (cat3:SearchCategory {category_id: 'technical'})
SET cat3.name = 'technical',
    cat3.engines = ['stackoverflow','github','readthedocs'],
    cat3.priority = 2
MERGE (s)-[:HAS_CATEGORY]->(cat3)

MERGE (cat4:SearchCategory {category_id: 'news'})
SET cat4.name = 'news',
    cat4.engines = ['newsapi','newsgoogle'],
    cat4.priority = 1,
    cat4.recency_weight = 0.8
MERGE (s)-[:HAS_CATEGORY]->(cat4)

MERGE (cat5:SearchCategory {category_id: 'video'})
SET cat5.name = 'video',
    cat5.engines = ['youtube','vimeo'],
    cat5.priority = 1
MERGE (s)-[:HAS_CATEGORY]->(cat5)

MERGE (cat6:SearchCategory {category_id: 'reddit'})
SET cat6.name = 'reddit',
    cat6.engines = ['reddit'],
    cat6.priority = 1,
    cat6.sentiment_analysis = true
MERGE (s)-[:HAS_CATEGORY]->(cat6)

MERGE (cat7:SearchCategory {category_id: 'competitive'})
SET cat7.name = 'competitive',
    cat7.engines = ['google','newsapi'],
    cat7.priority = 1
MERGE (s)-[:HAS_CATEGORY]->(cat7)

// ============================================================
// POLICIES
// ============================================================

MERGE (pol1:Policy {policy_id: 'deep_mode_policy'})
SET pol1.name = 'deep_mode_policy',
    pol1.description = 'Blocks deep if cross-verification < 3.',
    pol1.rule = 'cross_verify_min >= 3',
    pol1.blocks_execution = true,
    pol1.required_for_depths = ['deep']
MERGE (s)-[:HAS_POLICY]->(pol1)
MERGE (depth3)-[:GOVERNED_BY]->(pol1)

MERGE (pol2:Policy {policy_id: 'cost_control'})
SET pol2.name = 'cost_control',
    pol2.description = 'Limits cost units per request; prefers cheap engines for light tasks.',
    pol2.rule = 'cost_units <= max_cost_units',
    pol2.blocks_execution = true
MERGE (s)-[:HAS_POLICY]->(pol2)

MERGE (pol3:Policy {policy_id: 'source_diversity'})
SET pol3.name = 'source_diversity',
    pol3.description = 'Requires minimum unique domains.',
    pol3.rule = 'min_unique_domains >= 3',
    pol3.min_unique_domains = 3,
    pol3.category_filter = 'academic'
MERGE (s)-[:HAS_POLICY]->(pol3)
MERGE (cat2)-[:GOVERNED_BY]->(pol3)

MERGE (pol4:Policy {policy_id: 'bias_detection'})
SET pol4.name = 'bias_detection',
    pol4.description = 'Flags bias and requests counter-sources.',
    pol4.rule = 'bias_score > 0.5',
    pol4.enabled = true
MERGE (s)-[:HAS_POLICY]->(pol4)

// ============================================================
// TOOLCHAIN STEPS
// ============================================================

MERGE (step1:ToolchainStep {step_id: 'ps_01_classify'})
SET step1.name = 'classify_query',
    step1.order = 1,
    step1.required = true,
    step1.timeout_ms = 1000
MERGE (s)-[:HAS_STEP]->(step1)

MERGE (step2:ToolchainStep {step_id: 'ps_02_expand'})
SET step2.name = 'expand_query',
    step2.order = 2,
    step2.required = true,
    step2.conditional = "query_type in ['hybrid','machine_only'] or depth in ['standard','deep','continuous']",
    step2.params = '{ "expansions": 5 }',
    step2.timeout_ms = 5000
MERGE (s)-[:HAS_STEP]->(step2)

MERGE (step3:ToolchainStep {step_id: 'ps_03_search'})
SET step3.name = 'multi_engine_search',
    step3.order = 3,
    step3.required = true,
    step3.streaming = true,
    step3.timeout_ms = 15000
MERGE (s)-[:HAS_STEP]->(step3)

MERGE (step4:ToolchainStep {step_id: 'ps_04_verify'})
SET step4.name = 'evaluate_sources',
    step4.order = 4,
    step4.required = true,
    step4.params = '{ "cross_verify": true, "min_sources": 3 }',
    step4.timeout_ms = 8000
MERGE (s)-[:HAS_STEP]->(step4)

MERGE (step5:ToolchainStep {step_id: 'ps_05_synthesize'})
SET step5.name = 'synthesize_results',
    step5.order = 5,
    step5.required = true,
    step5.streaming = true,
    step5.params = '{ "mode": "analysis|summary|comparative" }',
    step5.timeout_ms = 15000
MERGE (s)-[:HAS_STEP]->(step5)

MERGE (step6:ToolchainStep {step_id: 'ps_06_store'})
SET step6.name = 'store_knowledge',
    step6.order = 6,
    step6.required = false,
    step6.conditional = 'learning_enabled == true',
    step6.timeout_ms = 5000
MERGE (s)-[:HAS_STEP]->(step6)

// NEXT_STEP relationships
MERGE (step1)-[:NEXT_STEP]->(step2)
MERGE (step2)-[:NEXT_STEP]->(step3)
MERGE (step3)-[:NEXT_STEP]->(step4)
MERGE (step4)-[:NEXT_STEP]->(step5)
MERGE (step5)-[:NEXT_STEP]->(step6)

// ============================================================
// INTENTS
// ============================================================

MERGE (i1:Intent {intent_id: 'research'})
SET i1.name = 'research', i1.description = 'General research intent'
MERGE (i1)-[:ACTIVATES]->(s)

MERGE (i2:Intent {intent_id: 'find_information'})
SET i2.name = 'find_information', i2.description = 'Find specific information'
MERGE (i2)-[:ACTIVATES]->(s)

MERGE (i3:Intent {intent_id: 'learn_topic'})
SET i3.name = 'learn_topic', i3.description = 'Learn and store in graph'
MERGE (i3)-[:ACTIVATES]->(s)

MERGE (i4:Intent {intent_id: 'analyze_market'})
SET i4.name = 'analyze_market', i4.description = 'Market/competitive analysis'
MERGE (i4)-[:ACTIVATES]->(s)

MERGE (i5:Intent {intent_id: 'verify_fact'})
SET i5.name = 'verify_fact', i5.description = 'Fact verification'
MERGE (i5)-[:ACTIVATES]->(s)

// ============================================================
// ENGINE PREFERENCES
// ============================================================

MERGE (e1:Engine {name: 'qwen3b_local'})
SET e1.role = 'primary', e1.tier = 'heavy', e1.priority_base = 10
MERGE (s)-[:PREFERS_ENGINE]->(e1)

MERGE (e2:Engine {name: 'qwen_coder7b_local'})
SET e2.role = 'primary', e2.tier = 'heavy', e2.priority_base = 15
MERGE (s)-[:PREFERS_ENGINE]->(e2)

MERGE (e3:Engine {name: 'smollm_node2'})
SET e3.role = 'primary', e3.tier = 'light', e3.priority_base = 5
MERGE (s)-[:PREFERS_ENGINE]->(e3)

MERGE (e4:Engine {name: 'gemma_node2'})
SET e4.role = 'primary', e4.tier = 'light', e4.priority_base = 5
MERGE (s)-[:PREFERS_ENGINE]->(e4)

MERGE (e5:Engine {name: 'qwen15b_node2'})
SET e5.role = 'primary', e5.tier = 'light', e5.priority_base = 8
MERGE (s)-[:PREFERS_ENGINE]->(e5)

MERGE (e6:Engine {name: 'groq_booster'})
SET e6.role = 'booster', e6.tier = 'cloud', e6.priority_base = 20
MERGE (s)-[:PREFERS_ENGINE]->(e6)

MERGE (e7:Engine {name: 'openrouter_cloud'})
SET e7.role = 'booster', e7.tier = 'cloud', e7.priority_base = 25
MERGE (s)-[:PREFERS_ENGINE]->(e7)

// ============================================================
// COLLECTIONS & MEMORY
// ============================================================

MERGE (ac1:AtlasCollection {name: 'knowledge_base'})
MERGE (s)-[:USES_COLLECTION]->(ac1)

MERGE (ml1:MemoryLayer {name: 'L2_SHORT_TERM'})
MERGE (s)-[:WRITES_TO]->(ml1)

MERGE (ml2:MemoryLayer {name: 'L3_EPISODIC'})
MERGE (s)-[:WRITES_TO]->(ml2)

// ============================================================
// DECISION TRACE
// ============================================================

MERGE (dt_root:DecisionTrace {id: 'decision_trace_root'})
SET dt_root.description = 'Root for decision trace events',
    dt_root.created_at = datetime()
MERGE (s)-[:TRACKS_DECISIONS]->(dt_root)

MERGE (dt1:DecisionType {type: 'engine_selection'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'engine_selection'}]->(dt1)

MERGE (dt2:DecisionType {type: 'policy_evaluation'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'policy_evaluation'}]->(dt2)

MERGE (dt3:DecisionType {type: 'mode_selection'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'mode_selection'}]->(dt3)

MERGE (dt4:DecisionType {type: 'depth_selection'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'depth_selection'}]->(dt4)

MERGE (dt5:DecisionType {type: 'source_ranking'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'source_ranking'}]->(dt5)

MERGE (dt6:DecisionType {type: 'synthesis_mode'})
MERGE (s)-[:TRACKS_DECISION {decision_type: 'synthesis_mode'}]->(dt6)

RETURN s.name, s.version
