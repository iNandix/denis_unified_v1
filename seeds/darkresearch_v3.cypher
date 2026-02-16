// ============================================================
// DARKRESEARCH v3.0 - Extension Seed
// Dark web research extension (DISABLED BY DEFAULT)
// ============================================================

// SCOPE: DARK
MERGE (scope:Scope {scope_id: 'dark'})
SET scope.name = 'dark',
    scope.description = 'Dark web research scope - requires approval and sandbox',
    scope.enabled = false,
    scope.default_policy = 'deny'

WITH scope
MERGE (scope)-[:REQUIRES_APPROVAL]->(Approval {type: 'dark_web_research'})

// EXECUTION ENV: WAYDROID_WESTON
MERGE (env:ExecutionEnv {env_id: 'waydroid_weston'})
SET env.type = 'waydroid_weston',
    env.description = 'Ephemeral sandboxed environment for dark web access',
    env.isolation_level = 'strong',
    env.ephemeral_session = true,
    env.isolated_network = true,
    env.no_personal_accounts = true,
    env.no_device_tracking = true,
    env.requires_approval = true,
    env.created_at = datetime()

WITH scope
MATCH (s:Skill {name: 'pro_search'})
MERGE (s)-[:SUPPORTS_SCOPE]->(scope)

// DARK WEB POLICY
MERGE (pol_dark:Policy {policy_id: 'dark_web_policy'})
SET pol_dark.name = 'dark_web_policy',
    pol_dark.description = 'Policy governing dark web research access',
    pol_dark.enabled = false,
    pol_dark.requires_approval = true,
    pol_dark.audit_log = 'mandatory',
    pol_dark.sandbox_required = true,
    pol_dark.read_only_default = true,
    pol_dark.no_accounts = true,
    pol_dark.no_interactive_actions = true,
    pol_dark.no_downloads = true,
    pol_dark.blocks_execution = true

WITH scope, pol_dark, env
MERGE (scope)-[:GOVERNED_BY]->(pol_dark)
MERGE (env)-[:GOVERNED_BY]->(pol_dark)

// ALLOWED PURPOSES
MERGE (purpose1:AllowedPurpose {purpose_id: 'defensive_research'})
SET purpose1.name = 'defensive_research', purpose1.description = 'Security research for defensive purposes', purpose1.risk_level = 'medium'

MERGE (purpose2:AllowedPurpose {purpose_id: 'academic_research'})
SET purpose2.name = 'academic_research', purpose2.description = 'Academic research on dark web phenomena', purpose2.risk_level = 'low'

MERGE (purpose3:AllowedPurpose {purpose_id: 'threat_intelligence'})
SET purpose3.name = 'threat_intelligence', purpose3.description = 'Threat intelligence gathering', purpose3.risk_level = 'medium'

WITH scope
MERGE (scope)-[:ALLOWS]->(purpose1)
MERGE (scope)-[:ALLOWS]->(purpose2)
MERGE (scope)-[:ALLOWS]->(purpose3)

// BLOCKED CATEGORIES
MERGE (blocked1:BlockedCategory {category_id: 'illicit_marketplaces'})
SET blocked1.name = 'illicit_marketplaces', blocked1.description = 'Illicit marketplaces'

MERGE (blocked2:BlockedCategory {category_id: 'credential_theft'})
SET blocked2.name = 'credential_theft', blocked2.description = 'Credential theft services'

MERGE (blocked3:BlockedCategory {category_id: 'exploit_kits'})
SET blocked3.name = 'exploit_kits', blocked3.description = 'Exploit kits and malware'

MERGE (blocked4:BlockedCategory {category_id: 'harmful_content'})
SET blocked4.name = 'harmful_content', blocked4.description = 'Harmful content'

WITH scope
MERGE (scope)-[:BLOCKS]->(blocked1)
MERGE (scope)-[:BLOCKS]->(blocked2)
MERGE (scope)-[:BLOCKS]->(blocked3)
MERGE (scope)-[:BLOCKS]->(blocked4)

// DARK SEARCH ENGINES
MERGE (de1:SearchEngine {engine_id: 'onion_search'})
SET de1.name = 'onion_search', de1.type = 'onion', de1.requires_tor = true, de1.timeout_s = 30, de1.risk_level = 'high'

MERGE (de2:SearchEngine {engine_id: 'darksearch'})
SET de2.name = 'darksearch', de2.type = 'darkweb', de2.requires_proxy = true, de2.timeout_s = 20, de2.risk_level = 'high'

MERGE (de3:SearchEngine {engine_id: 'ahmia'})
SET de3.name = 'ahmia', de3.type = 'onion', de3.requires_tor = true, de3.timeout_s = 25, de3.risk_level = 'medium'

// DARK TOOLCHAIN STEPS (DISABLED)
MERGE (step_d1:ToolchainStep {step_id: 'dr_01_tor_connect'})
SET step_d1.name = 'tor_connection', step_d1.order = 1, step_d1.enabled = false, step_d1.timeout_s = 30

MERGE (step_d2:ToolchainStep {step_id: 'dr_02_dark_search'})
SET step_d2.name = 'dark_web_search', step_d2.order = 2, step_d2.enabled = false, step_d2.timeout_s = 45, step_d2.requires_tor = true

MERGE (step_d3:ToolchainStep {step_id: 'dr_03_sanitize'})
SET step_d3.name = 'dark_content_sanitize', step_d3.order = 3, step_d3.enabled = false, step_d3.timeout_s = 15

MERGE (step_d4:ToolchainStep {step_id: 'dr_04_verify'})
SET step_d4.name = 'dark_source_verification', step_d4.order = 4, step_d4.enabled = false, step_d4.timeout_s = 10

WITH step_d1, step_d2, step_d3, step_d4
MATCH (s:Skill {name: 'pro_search'})
MERGE (s)-[:HAS_DARK_STEP]->(step_d1)
MERGE (s)-[:HAS_DARK_STEP]->(step_d2)
MERGE (s)-[:HAS_DARK_STEP]->(step_d3)
MERGE (s)-[:HAS_DARK_STEP]->(step_d4)

// TOR CONFIGURATION
MERGE (tor:TorConfig {config_id: 'default'})
SET tor.proxy_host = '127.0.0.1', tor.proxy_port = 9050, tor.control_port = 9051, tor.timeout_s = 60

// AUDIT EVENT SCHEMA
MERGE (ae:AuditEventType {event_type: 'dark_research_request'})
SET ae.description = 'Dark web research request'

MERGE (ae2:AuditEventType {event_type: 'dark_research_access'})
SET ae2.description = 'Dark web content accessed'

MERGE (ae3:AuditEventType {event_type: 'dark_research_blocked'})
SET ae3.description = 'Dark web access blocked'

// APPROVAL SCHEMA
MERGE (app:ApprovalType {type: 'dark_web_research'})
SET app.description = 'Approval required for dark web research',
    app.requires_manual_review = true,
    app.max_validity_hours = 4,
    app.audit_required = true

RETURN 'darkresearch_v3 seeded (disabled)' as result
