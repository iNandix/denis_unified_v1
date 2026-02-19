// =============================================================================
// INTENT SYSTEM GRAPH SEEDS - SSoT for Intent Resolution
// =============================================================================
// This script creates the baseline graph topology for the IntentSystem.
// M2: Seeds equivalentes a lo que ya funciona en Client Runtime
// =============================================================================

// -----------------------------------------------------------------------------
// JOURNEY STATES - Lifecycle states for bot interactions
// -----------------------------------------------------------------------------

MERGE (js:JourneyState {name: 'DISCOVERY'})
SET js.description = 'Explorando requirements, sin specs locking',
    js.default_phase = 'local',
    js.priority = 1;

MERGE (js2:JourneyState {name: 'SPEC_LOCKED'})
SET js2.description = 'Specs definidos, solo building',
    js2.default_phase = 'shallow_scan',
    js2.priority = 2;

MERGE (js3:JourneyState {name: 'BUILDING'})
SET js3.description = 'Implementando código, puede necesitar análisis',
    js3.default_phase = 'shallow_scan',
    js3.priority = 3;

MERGE (js4:JourneyState {name: 'INCIDENT'})
SET js4.description = 'Sistema caído/error crítico, respuesta rápida',
    js4.default_phase = 'local',
    js4.priority = 5;

MERGE (js5:JourneyState {name: 'DELIVERED'})
SET js5.description = 'Entregado, solo mantenimiento',
    js5.default_phase = 'local',
    js5.priority = 4;

// -----------------------------------------------------------------------------
// BOT PROFILES - Multi-bot support (future: support/builder/sales/ops)
// -----------------------------------------------------------------------------

MERGE (bp:BotProfile {name: 'builder'})
SET bp.description = 'Desarrollador/coder, focus en código',
    bp.default_phase = 'shallow_scan',
    bp.allows_intents = ['fix_bug', 'write_code', 'write_tests', 'refactor', 'repo_explore', 'search_code', 'explain_code', 'build', 'run_code'];

MERGE (bp2:BotProfile {name: 'support'})
SET bp2.description = 'Soporte técnico, focus en diagnóstico',
    bp2.default_phase = 'local',
    bp2.allows_intents = ['system_process_query', 'system_port_check', 'system_resource_check', 'service_status_check', 'log_inspect', 'fix_bug'];

MERGE (bp3:BotProfile {name: 'ops'})
SET bp3.description = 'DevOps/SRE, focus en infraestructura',
    bp3.default_phase = 'local',
    bp3.allows_intents = ['system_process_query', 'system_port_check', 'system_resource_check', 'service_status_check', 'log_inspect', 'deploy', 'container_work', 'ci_cd', 'db_migration'];

// -----------------------------------------------------------------------------
// PHASE POLICIES - Phase selection rules
// -----------------------------------------------------------------------------

MERGE (pp1:PhasePolicy {name: 'local_only'})
SET pp1.phase = 'local',
    pp1.max_cost = 'low',
    pp1.needs_repo = false,
    pp1.description = 'Ejecución local, sin acceso a repo';

MERGE (pp2:PhasePolicy {name: 'shallow_scan'})
SET pp2.phase = 'shallow_scan',
    pp2.max_cost = 'medium',
    pp2.needs_repo = true,
    pp2.description = 'Escaneo superficial del repo, análisis básico';

MERGE (pp3:PhasePolicy {name: 'escalate'})
SET pp3.phase = 'escalate',
    pp3.max_cost = 'high',
    pp3.needs_repo = true,
    pp3.description = 'Escalado a Sprint Orchestrator, análisis profundo';

// -----------------------------------------------------------------------------
// GATE POLICIES - Escalation gate rules
// -----------------------------------------------------------------------------

MERGE (gp1:GatePolicy {name: 'always_escalate'})
SET gp1.rule = 'phase = escalate',
    gp1.should_confirm = true,
    gp1.reason_override = 'high_cost_operation';

MERGE (gp2:GatePolicy {name: 'cost_threshold'})
SET gp2.rule = 'cost = high AND needs_repo = true',
    gp2.should_confirm = true,
    gp2.reason_override = 'cost_budget_exceeded';

MERGE (gp3:GatePolicy {name: 'auto_approve'})
SET gp3.rule = 'default',
    gp3.should_confirm = false,
    gp3.reason_override = null;

// -----------------------------------------------------------------------------
// BUDGET POLICIES - Resource limits
// -----------------------------------------------------------------------------

MERGE (bp1:BudgetPolicy {name: 'default_local'})
SET bp1.tool_timeout_ms = 1500,
    bp1.max_output_chars = 8000,
    bp1.artifact_threshold_chars = 6000,
    bp1.max_output_tokens = 500;

MERGE (bp2:BudgetPolicy {name: 'default_shallow'})
SET bp2.tool_timeout_ms = 3000,
    bp2.max_output_chars = 15000,
    bp2.artifact_threshold_chars = 10000,
    bp2.max_output_tokens = 1000;

MERGE (bp3:BudgetPolicy {name: 'default_escalate'})
SET bp3.tool_timeout_ms = 10000,
    bp3.max_output_chars = 50000,
    bp3.artifact_threshold_chars = 30000,
    bp3.max_output_tokens = 3000;

// -----------------------------------------------------------------------------
// TOOL POLICIES - Allowed tools per intent
// -----------------------------------------------------------------------------

MERGE (tp1:ToolPolicy {name: 'system_readonly'})
SET tp1.allowed_tools = ['ps', 'pgrep', 'pidof', 'ss', 'lsof', 'netstat', 'free', 'df', 'top', 'systemctl', 'docker ps', 'docker images', 'journalctl', 'tail'],
    tp1.description = 'Solo herramientas de lectura del sistema';

MERGE (tp2:ToolPolicy {name: 'code_analysis'})
SET tp2.allowed_tools = ['grep', 'find', 'cat', 'ls', 'read'],
    tp2.description = 'Análisis de código fuente';

MERGE (tp3:ToolPolicy {name: 'code_write'})
SET tp3.allowed_tools = ['write', 'edit', 'create', 'delete'],
    tp3.requires_confirm = true,
    tp3.description = 'Modificación de archivos';

// -----------------------------------------------------------------------------
// FALLBACK POLICIES - Fallback rules
// -----------------------------------------------------------------------------

MERGE (fp1:FallbackPolicy {name: 'unclear_intent'})
SET fp1.action = 'ask_clarification',
    fp1.message = '¿Podrías ser más específico? No entiendo qué quieres hacer.';

MERGE (fp2:FallbackPolicy {name: 'high_cost_unknown'})
SET fp2.action = 'escalate_with_warning',
    fp2.message = 'No tengo claro el alcance. ¿Procedo con análisis completo?';

MERGE (fp3:FallbackPolicy {name: 'default_low'})
SET fp3.action = 'execute_local',
    fp3.message = null;

// -----------------------------------------------------------------------------
// INTENTS - Core intent definitions (M2: equivalent to Client Runtime)
// -----------------------------------------------------------------------------

// System/Ops intents (priority 25-30)
MERGE (i1:Intent {name: 'system_process_query'})
SET i1.cost = 'low', i1.priority = 30, i1.needs_repo = false,
    i1.description = 'Consulta de procesos del sistema';

MERGE (i2:Intent {name: 'system_port_check'})
SET i2.cost = 'low', i2.priority = 30, i2.needs_repo = false,
    i2.description = 'Verificación de puertos de red';

MERGE (i3:Intent {name: 'system_resource_check'})
SET i3.cost = 'low', i3.priority = 28, i3.needs_repo = false,
    i3.description = 'Consulta de recursos (CPU/RAM/disco)';

MERGE (i4:Intent {name: 'service_status_check'})
SET i4.cost = 'low', i4.priority = 28, i4.needs_repo = false,
    i4.description = 'Estado de servicios systemd/docker';

MERGE (i5:Intent {name: 'log_inspect'})
SET i5.cost = 'low', i5.priority = 25, i5.needs_repo = false,
    i5.description = 'Inspección de logs';

// Repo intents (priority 15-20)
MERGE (i6:Intent {name: 'repo_summary'})
SET i6.cost = 'medium', i6.priority = 20, i6.needs_repo = true,
    i6.description = 'Resumen del repositorio';

MERGE (i7:Intent {name: 'repo_explore'})
SET i7.cost = 'medium', i7.priority = 20, i7.needs_repo = true,
    i7.description = 'Explorar estructura del repo';

MERGE (i8:Intent {name: 'suggest_next_steps'})
SET i8.cost = 'low', i8.priority = 15, i8.needs_repo = false,
    i8.description = 'Sugerir próximos pasos';

// Code operations (priority 10-18)
MERGE (i9:Intent {name: 'fix_bug'})
SET i9.cost = 'medium', i9.priority = 18, i9.needs_repo = true,
    i9.description = 'Corrección de bugs';

MERGE (i10:Intent {name: 'refactor'})
SET i10.cost = 'high', i10.priority = 15, i10.needs_repo = true,
    i10.description = 'Refactorización de código';

MERGE (i11:Intent {name: 'write_code'})
SET i11.cost = 'medium', i11.priority = 12, i11.needs_repo = true,
    i11.description = 'Escribir nuevo código';

MERGE (i12:Intent {name: 'write_tests'})
SET i12.cost = 'medium', i12.priority = 12, i12.needs_repo = true,
    i12.description = 'Escribir tests';

// Analysis (priority 10)
MERGE (i13:Intent {name: 'code_review'})
SET i13.cost = 'high', i13.priority = 10, i13.needs_repo = true,
    i13.description = 'Auditoría/security review';

MERGE (i14:Intent {name: 'code_migration'})
SET i14.cost = 'high', i14.priority = 10, i14.needs_repo = true,
    i14.description = 'Migración de código';

MERGE (i15:Intent {name: 'performance_optim'})
SET i15.cost = 'medium', i15.priority = 10, i15.needs_repo = true,
    i15.description = 'Optimización de rendimiento';

// DevOps (priority 7-8)
MERGE (i16:Intent {name: 'deploy'})
SET i16.cost = 'medium', i16.priority = 8, i16.needs_repo = false,
    i16.description = 'Deploy/release';

MERGE (i17:Intent {name: 'db_migration'})
SET i17.cost = 'high', i17.priority = 8, i17.needs_repo = true,
    i17.description = 'Migración de base de datos';

MERGE (i18:Intent {name: 'container_work'})
SET i18.cost = 'medium', i18.priority = 7, i18.needs_repo = false,
    i18.description = 'Trabajo con containers';

MERGE (i19:Intent {name: 'git_work'})
SET i19.cost = 'low', i19.priority = 7, i19.needs_repo = false,
    i19.description = 'Operaciones git';

MERGE (i20:Intent {name: 'ci_cd'})
SET i20.cost = 'medium', i20.priority = 7, i20.needs_repo = false,
    i20.description = 'CI/CD pipelines';

// Utility (priority 1-10)
MERGE (i21:Intent {name: 'search_code'})
SET i21.cost = 'low', i21.priority = 6, i21.needs_repo = true,
    i21.description = 'Buscar código';

MERGE (i22:Intent {name: 'explain_code'})
SET i22.cost = 'low', i22.priority = 10, i22.needs_repo = true,
    i22.description = 'Explicar código';

MERGE (i23:Intent {name: 'help'})
SET i23.cost = 'low', i23.priority = 2, i23.needs_repo = false,
    i23.description = 'Ayuda general';

MERGE (i24:Intent {name: 'greeting'})
SET i24.cost = 'low', i24.priority = 1, i24.needs_repo = false,
    i24.description = 'Saludo';

// -----------------------------------------------------------------------------
// RELATIONSHIPS - Connect intents to policies
// -----------------------------------------------------------------------------

// System intents -> local + tool_policy
MATCH (i:Intent {name: 'system_process_query'})
MATCH (pp:PhasePolicy {name: 'local_only'})
MATCH (tp:ToolPolicy {name: 'system_readonly'})
MATCH (bp:BudgetPolicy {name: 'default_local'})
MATCH (gp:GatePolicy {name: 'auto_approve'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:ALLOWS_TOOL_POLICY]->(tp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

MATCH (i:Intent {name: 'system_port_check'})
MATCH (pp:PhasePolicy {name: 'local_only'})
MATCH (tp:ToolPolicy {name: 'system_readonly'})
MATCH (bp:BudgetPolicy {name: 'default_local'})
MATCH (gp:GatePolicy {name: 'auto_approve'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:ALLOWS_TOOL_POLICY]->(tp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

// Repo intents -> shallow_scan
MATCH (i:Intent {name: 'repo_summary'})
MATCH (pp:PhasePolicy {name: 'shallow_scan'})
MATCH (tp:ToolPolicy {name: 'code_analysis'})
MATCH (bp:BudgetPolicy {name: 'default_shallow'})
MATCH (gp:GatePolicy {name: 'cost_threshold'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:ALLOWS_TOOL_POLICY]->(tp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

MATCH (i:Intent {name: 'fix_bug'})
MATCH (pp:PhasePolicy {name: 'shallow_scan'})
MATCH (tp:ToolPolicy {name: 'code_analysis'})
MATCH (bp:BudgetPolicy {name: 'default_shallow'})
MATCH (gp:GatePolicy {name: 'cost_threshold'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:ALLOWS_TOOL_POLICY]->(tp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

// High-cost intents -> escalate
MATCH (i:Intent {name: 'refactor'})
MATCH (pp:PhasePolicy {name: 'escalate'})
MATCH (bp:BudgetPolicy {name: 'default_escalate'})
MATCH (gp:GatePolicy {name: 'always_escalate'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

MATCH (i:Intent {name: 'code_review'})
MATCH (pp:PhasePolicy {name: 'escalate'})
MATCH (bp:BudgetPolicy {name: 'default_escalate'})
MATCH (gp:GatePolicy {name: 'always_escalate'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

// Low-cost intents -> local
MATCH (i:Intent {name: 'help'})
MATCH (pp:PhasePolicy {name: 'local_only'})
MATCH (bp:BudgetPolicy {name: 'default_local'})
MATCH (gp:GatePolicy {name: 'auto_approve'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

MATCH (i:Intent {name: 'greeting'})
MATCH (pp:PhasePolicy {name: 'local_only'})
MATCH (bp:BudgetPolicy {name: 'default_local'})
MATCH (gp:GatePolicy {name: 'auto_approve'})
MERGE (i)-[:USES_PHASE_POLICY]->(pp)
MERGE (i)-[:USES_BUDGET_POLICY]->(bp)
MERGE (i)-[:USES_GATE_POLICY]->(gp);

// -----------------------------------------------------------------------------
// BOT PROFILE -> JOURNEY STATE relationships
// -----------------------------------------------------------------------------

MATCH (bp:BotProfile {name: 'builder'})
MATCH (js:JourneyState {name: 'BUILDING'})
MERGE (bp)-[:DEFAULTS_TO]->(js);

MATCH (bp:BotProfile {name: 'support'})
MATCH (js:JourneyState {name: 'INCIDENT'})
MERGE (bp)-[:DEFAULTS_TO]->(js);

MATCH (bp:BotProfile {name: 'ops'})
MATCH (js:JourneyState {name: 'DISCOVERY'})
MERGE (bp)-[:DEFAULTS_TO]->(js);
