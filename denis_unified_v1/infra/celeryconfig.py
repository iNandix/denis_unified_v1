"""Celery configuration for Denis unified workers.

Queues:
  tts          - TTS synthesis tasks (nodo2 bound)
  tools_ro     - Read-only tool execution
  tools_mut    - Mutating tool execution (requires high confidence)
  ha_playback  - Home Assistant media playback
  graph_ingest - Neo4j graph projection writes
  housekeeping - Cleanup, stats, health checks

Idempotency: via Redis SET NX with TTL per request_id.
"""

import os

# Broker
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Serialization
accept_content = ["json"]
task_serializer = "json"
result_serializer = "json"

# Timeouts
task_soft_time_limit = 30  # seconds
task_time_limit = 60
result_expires = 300  # 5 min

# Acknowledgments
task_acks_late = True
task_reject_on_worker_lost = True

# Prefetch (1 = fair scheduling for mixed-latency tasks)
worker_prefetch_multiplier = 1

# Concurrency per worker type (overridden via CLI -c flag)
worker_concurrency = int(os.getenv("CELERY_CONCURRENCY", "4"))

# Queues
task_queues = {
    "tts": {
        "exchange": "denis",
        "routing_key": "denis.tts",
    },
    "tools_ro": {
        "exchange": "denis",
        "routing_key": "denis.tools.ro",
    },
    "tools_mut": {
        "exchange": "denis",
        "routing_key": "denis.tools.mut",
    },
    "ha_playback": {
        "exchange": "denis",
        "routing_key": "denis.ha",
    },
    "graph_ingest": {
        "exchange": "denis",
        "routing_key": "denis.graph",
    },
    "housekeeping": {
        "exchange": "denis",
        "routing_key": "denis.housekeeping",
    },
}

# Default queue
task_default_queue = "tools_ro"
task_default_exchange = "denis"
task_default_routing_key = "denis.tools.ro"

# Routing
task_routes = {
    "denis_unified_v1.infra.tasks.synthesize_tts": {"queue": "tts"},
    "denis_unified_v1.infra.tasks.project_to_graph": {"queue": "graph_ingest"},
    "denis_unified_v1.infra.tasks.play_ha_media": {"queue": "ha_playback"},
    "denis_unified_v1.infra.tasks.execute_tool_ro": {"queue": "tools_ro"},
    "denis_unified_v1.infra.tasks.execute_tool_mut": {"queue": "tools_mut"},
    "denis_unified_v1.infra.tasks.flush_deferred_graph": {"queue": "housekeeping"},
}

# Retry policy
task_default_retry_delay = 2  # seconds
task_max_retries = 3

# Beat schedule (periodic tasks)
beat_schedule = {
    "flush-deferred-graph-events": {
        "task": "denis_unified_v1.infra.tasks.flush_deferred_graph",
        "schedule": 60.0,  # every 60s
        "options": {"queue": "housekeeping"},
    },
}
