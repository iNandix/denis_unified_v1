// Graph learning patterns seed - Production ready
// Creates initial learning patterns for common intents

// Intent patterns with default tasks
MERGE (p1:HygienePattern {name: 'pattern:implement_feature:create,new'})
SET p1.intent = 'implement_feature', p1.constraints = ['create', 'new'], p1.tasks = ['READ existing patterns', 'VERIFY tests pass'], p1.frequency = 5, p1.lastSeen = datetime()

MERGE (p2:HygienePattern {name: 'pattern:debug_repo:error,fix'})
SET p2.intent = 'debug_repo', p2.constraints = ['error', 'fix'], p2.tasks = ['READ error logs', 'VERIFY fix works'], p2.frequency = 3, p2.lastSeen = datetime()

MERGE (p3:HygienePattern {name: 'pattern:explain_concept:what,how'})
SET p3.intent = 'explain_concept', p3.constraints = ['what', 'how'], p3.tasks = ['SEARCH docs', 'VERIFY explanation clear'], p3.frequency = 8, p3.lastSeen = datetime()

// Provider performance tracking
MERGE (prov:Provider {name: 'llama_local'})
SET prov.tier = 'free_local', prov.endpoint = 'http://localhost:8084', prov.success_count = 0, prov.fail_count = 0, prov.avg_latency = 0

MERGE (prov2:Provider {name: 'groq'})
SET prov2.tier = 'free_remote', prov2.endpoint = 'https://api.groq.com', prov2.success_count = 0, prov2.fail_count = 0, prov2.avg_latency = 0

MERGE (prov3:Provider {name: 'openrouter'})
SET prov3.tier = 'premium', prov3.endpoint = 'https://openrouter.ai', prov3.success_count = 0, prov3.fail_count = 0, prov3.avg_latency = 0

// System identity
MERGE (sys:System {name: 'denis'})
SET sys.version = '2.0', sys.status = 'operational', sys.last_heartbeat = datetime()

RETURN 'Learning patterns seeded'
