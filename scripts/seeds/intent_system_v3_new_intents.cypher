// =============================================================================
// INTENT SYSTEM SEEDS v3 - system_health_check + repo_structure_explore
// =============================================================================

// -----------------------------------------------------------------------------
// NEW INTENT: system_health_check
// -----------------------------------------------------------------------------

MERGE (i:Intent {name: 'system_health_check'})
SET i.description = 'Análisis comprehensivo del estado del sistema operativo',
    i.expected_cost = 'medium',
    i.default_phase = 'local',
    i.needs_repo_access = false,
    i.default_tool_policy = 'system_readonly',
    i.priority = 25;

MATCH (pp:PhasePolicy {name: 'local_only'})
MATCH (gp:GatePolicy {name: 'auto_approve'})
MATCH (bp:BudgetPolicy {name: 'default_local'})
MATCH (i:Intent {name: 'system_health_check'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_GATE_POLICY]->(gp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp);

// -----------------------------------------------------------------------------
// NEW INTENT: repo_structure_explore
// -----------------------------------------------------------------------------

MERGE (i2:Intent {name: 'repo_structure_explore'})
SET i2.description = 'Exploración detallada de la estructura de directorios del repo',
    i2.expected_cost = 'medium',
    i2.default_phase = 'shallow_scan',
    i2.needs_repo_access = true,
    i2.default_tool_policy = 'code_analysis',
    i2.priority = 22;

MATCH (pp2:PhasePolicy {name: 'shallow_scan'})
MATCH (gp2:GatePolicy {name: 'cost_threshold'})
MATCH (bp2:BudgetPolicy {name: 'default_shallow'})
MATCH (i2:Intent {name: 'repo_structure_explore'})
MERGE (i2)-[:USES_PHASE_POLICY]->(pp2)
MERGE (i2)-[:USES_GATE_POLICY]->(gp2)
MERGE (i2)-[:USES_BUDGET_POLICY]->(bp2);

// -----------------------------------------------------------------------------
// TRIGGER PACK: pack_system_health
// -----------------------------------------------------------------------------

MERGE (p:TriggerPack {name: 'pack_system_health'})
SET p.priority = 25,
    p.enabled = true,
    p.description = 'Paquete para análisis de salud del sistema';

MATCH (p:TriggerPack {name: 'pack_system_health'})
MATCH (i:Intent {name: 'system_health_check'})
MERGE (p)-[:CONTAINS_TRIGGER_FOR]->(i);

// Spanish triggers
MERGE (t1:Trigger {id: 't_sys_health_1'})
SET t1.type = 'keyword',
    t1.pattern = 'salud del sistema',
    t1.weight = 5,
    t1.lang = 'es',
    t1.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (p)-[:CONTAINS]->(t1);
MATCH (i:Intent {name: 'system_health_check'})
MERGE (t1)-[:VOTES_FOR]->(i);

MERGE (t2:Trigger {id: 't_sys_health_2'})
SET t2.type = 'keyword',
    t2.pattern = 'estado del sistema',
    t2.weight = 5,
    t2.lang = 'es',
    t2.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (p)-[:CONTAINS]->(t2);
MATCH (i:Intent {name: 'system_health_check'})
MERGE (t2)-[:VOTES_FOR]->(i);

MERGE (t3:Trigger {id: 't_sys_health_3'})
SET t3.type = 'keyword',
    t3.pattern = 'verificar sistema',
    t3.weight = 4,
    t3.lang = 'es',
    t3.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (p)-[:CONTAINS]->(t3);
MATCH (i:Intent {name: 'system_health_check'})
MERGE (t3)-[:VOTES_FOR]->(i);

// English triggers
MERGE (t4:Trigger {id: 't_sys_health_4'})
SET t4.type = 'keyword',
    t4.pattern = 'system health',
    t4.weight = 5,
    t4.lang = 'en',
    t4.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (p)-[:CONTAINS]->(t4);
MATCH (i:Intent {name: 'system_health_check'})
MERGE (t4)-[:VOTES_FOR]->(i);

MERGE (t5:Trigger {id: 't_sys_health_5'})
SET t5.type = 'keyword',
    t5.pattern = 'system status',
    t5.weight = 5,
    t5.lang = 'en',
    t5.polarity = 'positive';
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (p)-[:CONTAINS]->(t5);
MATCH (i:Intent {name: 'system_health_check'})
MERGE (t5)-[:VOTES_FOR]->(i);

// -----------------------------------------------------------------------------
// TRIGGER PACK: pack_repo_structure
// -----------------------------------------------------------------------------

MERGE (p2:TriggerPack {name: 'pack_repo_structure'})
SET p2.priority = 22,
    p2.enabled = true,
    p2.description = 'Paquete para exploración de estructura del repo';

MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (p2)-[:CONTAINS_TRIGGER_FOR]->(i);

// Spanish triggers
MERGE (t6:Trigger {id: 't_repo_struct_1'})
SET t6.type = 'keyword',
    t6.pattern = 'estructura del repositorio',
    t6.weight = 5,
    t6.lang = 'es',
    t6.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t6);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t6)-[:VOTES_FOR]->(i);

MERGE (t7:Trigger {id: 't_repo_struct_2'})
SET t7.type = 'keyword',
    t7.pattern = 'qué hay en el proyecto',
    t7.weight = 4,
    t7.lang = 'es',
    t7.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t7);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t7)-[:VOTES_FOR]->(i);

MERGE (t8:Trigger {id: 't_repo_struct_3'})
SET t8.type = 'keyword',
    t8.pattern = 'muestra las carpetas',
    t8.weight = 4,
    t8.lang = 'es',
    t8.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t8);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t8)-[:VOTES_FOR]->(i);

// English triggers
MERGE (t9:Trigger {id: 't_repo_struct_4'})
SET t9.type = 'keyword',
    t9.pattern = 'repo structure',
    t9.weight = 5,
    t9.lang = 'en',
    t9.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t9);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t9)-[:VOTES_FOR]->(i);

MERGE (t10:Trigger {id: 't_repo_struct_5'})
SET t10.type = 'keyword',
    t10.pattern = 'file structure',
    t10.weight = 5,
    t10.lang = 'en',
    t10.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t10);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t10)-[:VOTES_FOR]->(i);

MERGE (t11:Trigger {id: 't_repo_struct_6'})
SET t11.type = 'keyword',
    t11.pattern = 'what is in the project',
    t11.weight = 4,
    t11.lang = 'en',
    t11.polarity = 'positive';
MATCH (p2:TriggerPack {name: 'pack_repo_structure'})
MERGE (p2)-[:CONTAINS]->(t11);
MATCH (i:Intent {name: 'repo_structure_explore'})
MERGE (t11)-[:VOTES_FOR]->(i);

// -----------------------------------------------------------------------------
// JOURNEY STATE DEFAULTS
// -----------------------------------------------------------------------------

MATCH (s:JourneyState {name: 'DISCOVERY'})
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (s)-[:DEFAULT_PACKS]->(p);

MATCH (s:JourneyState {name: 'DISCOVERY'})
MATCH (p:TriggerPack {name: 'pack_repo_structure'})
MERGE (s)-[:DEFAULT_PACKS]->(p);

MATCH (s:JourneyState {name: 'INCIDENT'})
MATCH (p:TriggerPack {name: 'pack_system_health'})
MERGE (s)-[:DEFAULT_PACKS]->(p);
