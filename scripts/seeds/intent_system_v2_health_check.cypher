// =============================================================================
// INTENT SYSTEM SEEDS v2 - TriggerPacks + project_health_check
// =============================================================================

// -----------------------------------------------------------------------------
// NEW INTENT: project_health_check
// -----------------------------------------------------------------------------

MERGE (i:Intent {name: 'project_health_check'})
SET i.description = 'Auditar estado de un proyecto local y sugerir próximos pasos',
    i.expected_cost = 'medium',
    i.default_phase = 'shallow_scan',
    i.needs_repo_access = true,
    i.default_tool_policy = 'read_only',
    i.priority = 19;

// Connect to policies
MATCH (pp:PhasePolicy {name: 'shallow_scan'})
MATCH (gp:GatePolicy {name: 'cost_threshold'})
MATCH (bp:BudgetPolicy {name: 'default_shallow'})
MATCH (i:Intent {name: 'project_health_check'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_GATE_POLICY]->(gp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp);

// -----------------------------------------------------------------------------
// TRIGGER PACK: pack_repo_health
// -----------------------------------------------------------------------------

MERGE (p:TriggerPack {name: 'pack_repo_health'})
SET p.priority = 20,
    p.enabled = true,
    p.description = 'Paquete para análisis de salud de proyecto';

// Connect pack to intent
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MATCH (i:Intent {name: 'project_health_check'})
MERGE (p)-[:CONTAINS_TRIGGER_FOR]->(i);

// -----------------------------------------------------------------------------
// POSITIVE TRIGGERS (ES)
// -----------------------------------------------------------------------------

// Trigger: analiza el directorio
MERGE (t1:Trigger {id: 't_repo_health_1'})
SET t1.type = 'keyword',
    t1.pattern = 'analiza el directorio',
    t1.weight = 5,
    t1.lang = 'es',
    t1.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t1);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t1)-[:VOTES_FOR]->(i);

// Trigger: estado del proyecto
MERGE (t2:Trigger {id: 't_repo_health_2'})
SET t2.type = 'keyword',
    t2.pattern = 'estado del proyecto',
    t2.weight = 5,
    t2.lang = 'es',
    t2.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t2);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t2)-[:VOTES_FOR]->(i);

// Trigger: estado del repo
MERGE (t3:Trigger {id: 't_repo_health_3'})
SET t3.type = 'keyword',
    t3.pattern = 'estado del repo',
    t3.weight = 4,
    t3.lang = 'es',
    t3.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t3);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t3)-[:VOTES_FOR]->(i);

// Trigger: próximos pasos
MERGE (t4:Trigger {id: 't_repo_health_4'})
SET t4.type = 'keyword',
    t4.pattern = 'próximos pasos',
    t4.weight = 4,
    t4.lang = 'es',
    t4.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t4);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t4)-[:VOTES_FOR]->(i);

// Trigger: repositorio
MERGE (t5:Trigger {id: 't_repo_health_5'})
SET t5.type = 'keyword',
    t5.pattern = 'repositorio',
    t5.weight = 2,
    t5.lang = 'es',
    t5.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t5);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t5)-[:VOTES_FOR]->(i);

// Trigger: dime el estado
MERGE (t6:Trigger {id: 't_repo_health_6'})
SET t6.type = 'keyword',
    t6.pattern = 'dime el estado',
    t6.weight = 4,
    t6.lang = 'es',
    t6.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t6);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t6)-[:VOTES_FOR]->(i);

// Trigger: revisa el proyecto
MERGE (t10:Trigger {id: 't_repo_health_10'})
SET t10.type = 'keyword',
    t10.pattern = 'revisa el proyecto',
    t10.weight = 5,
    t10.lang = 'es',
    t10.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t10);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t10)-[:VOTES_FOR]->(i);

// Trigger: audita repo / audita el repo
MERGE (t11:Trigger {id: 't_repo_health_11'})
SET t11.type = 'keyword',
    t11.pattern = 'audita',
    t11.weight = 4,
    t11.lang = 'es',
    t11.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t11);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t11)-[:VOTES_FOR]->(i);

// Trigger: revisar el repositorio
MERGE (t12:Trigger {id: 't_repo_health_12'})
SET t12.type = 'keyword',
    t12.pattern = 'revisar el repositorio',
    t12.weight = 5,
    t12.lang = 'es',
    t12.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t12);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t12)-[:VOTES_FOR]->(i);

// Trigger: estado del repositorio
MERGE (t13:Trigger {id: 't_repo_health_13'})
SET t13.type = 'keyword',
    t13.pattern = 'estado del repositorio',
    t13.weight = 5,
    t13.lang = 'es',
    t13.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t13);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t13)-[:VOTES_FOR]->(i);

// -----------------------------------------------------------------------------
// POSITIVE TRIGGERS (EN)
// -----------------------------------------------------------------------------

// Trigger: analyze directory
MERGE (t7:Trigger {id: 't_repo_health_7'})
SET t7.type = 'keyword',
    t7.pattern = 'analyze the directory',
    t7.weight = 5,
    t7.lang = 'en',
    t7.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t7);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t7)-[:VOTES_FOR]->(i);

// Trigger: project status
MERGE (t8:Trigger {id: 't_repo_health_8'})
SET t8.type = 'keyword',
    t8.pattern = 'project status',
    t8.weight = 5,
    t8.lang = 'en',
    t8.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t8);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t8)-[:VOTES_FOR]->(i);

// Trigger: next steps
MERGE (t9:Trigger {id: 't_repo_health_9'})
SET t9.type = 'keyword',
    t9.pattern = 'next steps',
    t9.weight = 4,
    t9.lang = 'en',
    t9.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t9);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t9)-[:VOTES_FOR]->(i);

// Trigger: repo health
MERGE (t14:Trigger {id: 't_repo_health_14'})
SET t14.type = 'keyword',
    t14.pattern = 'repo health',
    t14.weight = 5,
    t14.lang = 'en',
    t14.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t14);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t14)-[:VOTES_FOR]->(i);

// Trigger: health check
MERGE (t15:Trigger {id: 't_repo_health_15'})
SET t15.type = 'keyword',
    t15.pattern = 'health check',
    t15.weight = 4,
    t15.lang = 'en',
    t15.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t15);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t15)-[:VOTES_FOR]->(i);

// Trigger: audit the repo
MERGE (t16:Trigger {id: 't_repo_health_16'})
SET t16.type = 'keyword',
    t16.pattern = 'audit the repo',
    t16.weight = 5,
    t16.lang = 'en',
    t16.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(t16);
MATCH (i:Intent {name: 'project_health_check'})
MERGE (t16)-[:VOTES_FOR]->(i);

// -----------------------------------------------------------------------------
// NEGATIVE TRIGGERS (anti git_work)
// -----------------------------------------------------------------------------

// Anti-trigger: pull request
MERGE (a1:Trigger {id: 't_gitwork_anti_1'})
SET a1.type = 'keyword',
    a1.pattern = 'pull request',
    a1.weight = 5,
    a1.lang = 'en',
    a1.polarity = 'negative';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(a1);
MATCH (i:Intent {name: 'git_work'})
MERGE (a1)-[:VOTES_FOR]->(i);

// Anti-trigger: PR
MERGE (a2:Trigger {id: 't_gitwork_anti_2'})
SET a2.type = 'keyword',
    a2.pattern = ' PR ',
    a2.weight = 5,
    a2.lang = 'en',
    a2.polarity = 'negative';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(a2);
MATCH (i:Intent {name: 'git_work'})
MERGE (a2)-[:VOTES_FOR]->(i);

// Anti-trigger: merge
MERGE (a3:Trigger {id: 't_gitwork_anti_3'})
SET a3.type = 'keyword',
    a3.pattern = 'merge',
    a3.weight = 4,
    a3.lang = 'en',
    a3.polarity = 'negative';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(a3);
MATCH (i:Intent {name: 'git_work'})
MERGE (a3)-[:VOTES_FOR]->(i);

// Anti-trigger: push
MERGE (a4:Trigger {id: 't_gitwork_anti_4'})
SET a4.type = 'keyword',
    a4.pattern = 'push',
    a4.weight = 4,
    a4.lang = 'en',
    a4.polarity = 'negative';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(a4);
MATCH (i:Intent {name: 'git_work'})
MERGE (a4)-[:VOTES_FOR]->(i);

// Anti-trigger: commit
MERGE (a5:Trigger {id: 't_gitwork_anti_5'})
SET a5.type = 'keyword',
    a5.pattern = 'commit',
    a5.weight = 3,
    a5.lang = 'en',
    a5.polarity = 'negative';
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (p)-[:CONTAINS]->(a5);
MATCH (i:Intent {name: 'git_work'})
MERGE (a5)-[:VOTES_FOR]->(i);

// -----------------------------------------------------------------------------
// TASK PROFILE MAPPING
// -----------------------------------------------------------------------------

MERGE (tp:TaskProfile {name: 'incident_triage'})
SET tp.description = 'Análisis de salud de proyecto y sugerencias',
    tp.max_output_tokens = 800,
    tp.timeout_ms = 2000,
    tp.tool_policy = 'read_only';

MATCH (i:Intent {name: 'project_health_check'})
MATCH (tp:TaskProfile {name: 'incident_triage'})
MERGE (i)-[:MAPS_TO_TASK_PROFILE]->(tp);

// -----------------------------------------------------------------------------
// JOURNEY STATE DEFAULTS
// -----------------------------------------------------------------------------

MATCH (s:JourneyState {name: 'DISCOVERY'})
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (s)-[:DEFAULT_PACKS]->(p);

MATCH (s:JourneyState {name: 'INCIDENT'})
MATCH (p:TriggerPack {name: 'pack_repo_health'})
MERGE (s)-[:DEFAULT_PACKS]->(p);
