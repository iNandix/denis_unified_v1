"""Symbol Ontology — Canon vocabulary for Python + TypeScript code analysis."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Symbol:
    name: str
    category: str
    aliases: List[str] = field(default_factory=list)
    implies: List[str] = field(default_factory=list)
    incompatible_with: List[str] = field(default_factory=list)
    framework_hints: Dict[str, str] = field(default_factory=dict)


SYMBOL_REGISTRY: Dict[str, Symbol] = {}


def _register(symbol: Symbol) -> None:
    SYMBOL_REGISTRY[symbol.name] = symbol
    for alias in symbol.aliases:
        SYMBOL_REGISTRY[alias.lower()] = symbol


def match_to_symbol(identifier: str) -> Optional[Symbol]:
    """Fuzzy match identifier to canonical symbol."""
    id_lower = identifier.lower().strip()
    if id_lower in SYMBOL_REGISTRY:
        return SYMBOL_REGISTRY[id_lower]
    for symbol in SYMBOL_REGISTRY.values():
        if any(alias in id_lower or id_lower in alias for alias in symbol.aliases):
            return symbol
    return None


# SECURITY symbols
_register(
    Symbol(
        name="AUTH",
        category="SECURITY",
        aliases=[
            "authenticate",
            "login",
            "verify",
            "check_auth",
            "validate_token",
            "auth",
        ],
        implies=["SESSION"],
        framework_hints={"fastapi": "Depends(auth)", "django": "@login_required"},
    )
)
_register(
    Symbol(
        name="JWT",
        category="SECURITY",
        aliases=[
            "jwt",
            "token",
            "access_token",
            "refresh_token",
            "bearer",
            "authorization",
        ],
        implies=["AUTH"],
        framework_hints={"python": "PyJWT", "fastapi": "OAuth2PasswordBearer"},
    )
)
_register(
    Symbol(
        name="SESSION",
        category="SECURITY",
        aliases=["session", "cookies", "session_id", "user_session"],
        implies=["AUTH"],
        framework_hints={"fastapi": "HTTP Cookie", "django": "SessionMiddleware"},
    )
)
_register(
    Symbol(
        name="OAUTH2",
        category="SECURITY",
        aliases=["oauth2", "oauth", "authorize", "provider", "google", "github"],
        implies=["AUTH"],
        framework_hints={"python": "Authlib"},
    )
)
_register(
    Symbol(
        name="PERMISSION",
        category="SECURITY",
        aliases=[
            "permission",
            "can",
            "has_permission",
            "check_permission",
            "authorize",
        ],
        incompatible_with=["ROLE"],
        framework_hints={"fastapi": "HTTPBearer", "rbac": "RBAC"},
    )
)
_register(
    Symbol(
        name="ROLE",
        category="SECURITY",
        aliases=["role", "user_role", "role_check", "admin", "superuser"],
        incompatible_with=["PERMISSION"],
        framework_hints={"django": "@group_required"},
    )
)
_register(
    Symbol(
        name="RATE_LIMIT",
        category="SECURITY",
        aliases=["rate_limit", "throttle", "limit", "rate", "max_requests"],
        framework_hints={"fastapi": "SlowAPI", "django": "django-ratelimit"},
    )
)
_register(
    Symbol(
        name="CSRF",
        category="SECURITY",
        aliases=["csrf", "csrf_token", "cross_site"],
        framework_hints={"django": "csrf_exempt", "fastapi": "CsrfProtect"},
    )
)
_register(
    Symbol(
        name="CORS",
        category="SECURITY",
        aliases=["cors", "cross_origin", "allow_origin", "access_control"],
        framework_hints={"fastapi": "add_middleware(CORSMiddleware)"},
    )
)

# DATA symbols
_register(
    Symbol(
        name="SCHEMA",
        category="DATA",
        aliases=[
            "schema",
            "model",
            "table",
            "entity",
            "dataclass",
            "pydantic",
            "basemodel",
        ],
        framework_hints={"python": "pydantic", "sqlalchemy": "Base", "django": "Model"},
    )
)
_register(
    Symbol(
        name="MODEL",
        category="DATA",
        aliases=["model", "orm", "entity", "record"],
        implies=["SCHEMA"],
        framework_hints={"sqlalchemy": "DeclarativeBase", "django": "models.Model"},
    )
)
_register(
    Symbol(
        name="MIGRATION",
        category="DATA",
        aliases=["migration", "alembic", "migrate", "schema_change"],
        framework_hints={"python": "Alembic"},
    )
)
_register(
    Symbol(
        name="QUERY",
        category="DATA",
        aliases=["query", "select", "filter", "where", "sql", "cypher"],
        framework_hints={"sqlalchemy": "select()", "django": "objects.filter()"},
    )
)
_register(
    Symbol(
        name="RELATION",
        category="DATA",
        aliases=[
            "relation",
            "relationship",
            "foreign_key",
            "many_to_many",
            "one_to_one",
        ],
        framework_hints={"sqlalchemy": "relationship()", "django": "ForeignKey"},
    )
)
_register(
    Symbol(
        name="INDEX",
        category="DATA",
        aliases=["index", "idx", "unique_index", "composite_index"],
        framework_hints={"sqlalchemy": "Index()", "django": "db_index=True"},
    )
)
_register(
    Symbol(
        name="CACHE",
        category="DATA",
        aliases=["cache", "redis", "memcached", "cached", "lru_cache"],
        framework_hints={"python": "functools.lru_cache", "redis": "RedisCache"},
    )
)
_register(
    Symbol(
        name="SERIALIZER",
        category="DATA",
        aliases=["serializer", "serialize", "deserialize", "to_json", "to_dict"],
        framework_hints={"fastapi": "BaseModel", "django": "serializers.JSONField"},
    )
)

# API symbols
_register(
    Symbol(
        name="ENDPOINT",
        category="API",
        aliases=[
            "endpoint",
            "route",
            "api_view",
            "handler",
            "view",
            "get",
            "post",
            "put",
            "delete",
        ],
        implies=["ROUTER"],
        framework_hints={"fastapi": "@app.get()", "flask": "@app.route()"},
    )
)
_register(
    Symbol(
        name="ROUTER",
        category="API",
        aliases=["router", "api_router", "blueprint", "app", "application"],
        implies=["ENDPOINT"],
        framework_hints={"fastapi": "APIRouter", "flask": "Blueprint"},
    )
)
_register(
    Symbol(
        name="MIDDLEWARE",
        category="API",
        aliases=["middleware", "interceptor", "before_request", "after_request"],
        framework_hints={"fastapi": "BaseHTTPMiddleware", "express": "app.use()"},
    )
)
_register(
    Symbol(
        name="REQUEST",
        category="API",
        aliases=["request", "req", "http_request", "input"],
        framework_hints={"fastapi": "Request", "flask": "request"},
    )
)
_register(
    Symbol(
        name="RESPONSE",
        category="API",
        aliases=["response", "res", "http_response", "output", "json_response"],
        framework_hints={"fastapi": "Response"},
    )
)
_register(
    Symbol(
        name="WEBHOOK",
        category="API",
        aliases=["webhook", "callback", "event_handler", "push_notification"],
        framework_hints={"stripe": "webhook", "github": "push event"},
    )
)
_register(
    Symbol(
        name="STREAM",
        category="API",
        aliases=["stream", "streaming", "sse", "server_sent_events", "websocket"],
        framework_hints={"fastapi": "StreamingResponse", "sse": "EventSourceResponse"},
    )
)

# LOGIC symbols
_register(
    Symbol(
        name="VALIDATOR",
        category="LOGIC",
        aliases=["validator", "validate", "check", "verify", "constraint", "rule"],
        framework_hints={"pydantic": "Field(validator)", "cerberus": "Validator"},
    )
)
_register(
    Symbol(
        name="TRANSFORMER",
        category="LOGIC",
        aliases=["transform", "convert", "map", "parse", "adapter"],
        framework_hints={"python": "map()", "pandas": "transform()"},
    )
)
_register(
    Symbol(
        name="CALCULATOR",
        category="LOGIC",
        aliases=["calculate", "compute", "sum", "aggregate", "metric", "score"],
        framework_hints={"pandas": "agg()", "numpy": "sum()"},
    )
)
_register(
    Symbol(
        name="AGGREGATOR",
        category="LOGIC",
        aliases=["aggregate", "group", "reduce", "accumulate", "combine"],
        framework_hints={"pandas": "groupby()", "sql": "GROUP BY"},
    )
)
_register(
    Symbol(
        name="FILTER",
        category="LOGIC",
        aliases=["filter", "where", "search", "find", "match"],
        framework_hints={"python": "filter()", "pandas": "df[df.col > 0]"},
    )
)
_register(
    Symbol(
        name="SORTER",
        category="LOGIC",
        aliases=["sort", "order", "order_by", "sorted"],
        framework_hints={"python": "sorted()", "pandas": "sort_values()"},
    )
)

# INFRA symbols
_register(
    Symbol(
        name="CONFIG",
        category="INFRA",
        aliases=["config", "settings", "configuration", "options", "params"],
        framework_hints={"python": "pydantic-settings", "django": "settings.py"},
    )
)
_register(
    Symbol(
        name="ENV",
        category="INFRA",
        aliases=["env", "environment", "environ", "os.environ", "dotenv"],
        framework_hints={"python": "python-dotenv", "docker": "ENV"},
    )
)
_register(
    Symbol(
        name="LOGGER",
        category="INFRA",
        aliases=["logger", "log", "logging", "debug", "info", "error"],
        framework_hints={"python": "logging", "structlog": "Logger"},
    )
)
_register(
    Symbol(
        name="MONITOR",
        category="INFRA",
        aliases=["monitor", "metrics", "prometheus", "grafana", "datadog", "observe"],
        framework_hints={"python": "prometheus-client", "opentelemetry": "Tracer"},
    )
)
_register(
    Symbol(
        name="HEALTH",
        category="INFRA",
        aliases=["health", "healthcheck", "liveness", "readiness", "status"],
        framework_hints={"k8s": "livenessProbe", "fastapi": "/health"},
    )
)
_register(
    Symbol(
        name="DEPLOY",
        category="INFRA",
        aliases=["deploy", "release", "ci_cd", "pipeline", "github_actions"],
        framework_hints={"github": ".github/workflows", "docker": "docker-compose"},
    )
)
_register(
    Symbol(
        name="DOCKER",
        category="INFRA",
        aliases=["docker", "container", "dockerfile", "compose", "podman"],
        framework_hints={"docker": "Dockerfile", "compose": "docker-compose.yml"},
    )
)

# TEST symbols
_register(
    Symbol(
        name="UNIT_TEST",
        category="TEST",
        aliases=["test", "unittest", "pytest", "spec", "case"],
        framework_hints={"python": "pytest", "unittest": "TestCase"},
    )
)
_register(
    Symbol(
        name="INTEGRATION_TEST",
        category="TEST",
        aliases=["integration", "e2e", "end_to_end", "functional_test"],
        framework_hints={"python": "pytest", "playwright": "test"},
    )
)
_register(
    Symbol(
        name="MOCK",
        category="TEST",
        aliases=["mock", "stub", "fake", "patch", "spy"],
        framework_hints={"python": "unittest.mock", "pytest-mock": "mocker"},
    )
)
_register(
    Symbol(
        name="FIXTURE",
        category="TEST",
        aliases=["fixture", "setup", "teardown", "factory", "seed"],
        framework_hints={"pytest": "@pytest.fixture"},
    )
)
_register(
    Symbol(
        name="ASSERTION",
        category="TEST",
        aliases=["assert", "expect", "should", "assertion", "assert_eq"],
        framework_hints={"python": "assert", "pytest": "assert"},
    )
)

# ASYNC symbols
_register(
    Symbol(
        name="WORKER",
        category="ASYNC",
        aliases=["worker", "background_task", "celery_task", "async_task"],
        framework_hints={"python": "celery", "fastapi": "BackgroundTasks"},
    )
)
_register(
    Symbol(
        name="QUEUE",
        category="ASYNC",
        aliases=["queue", "mq", "message_queue", "rabbitmq", "sqs", "redis_queue"],
        framework_hints={"python": "celery", "redis": "rpush/lpop"},
    )
)
_register(
    Symbol(
        name="TASK",
        category="ASYNC",
        aliases=["task", "job", "async", "await", "coroutine"],
        framework_hints={"python": "asyncio", "celery": "@celery.task"},
    )
)
_register(
    Symbol(
        name="SCHEDULER",
        category="ASYNC",
        aliases=["scheduler", "cron", "periodic", "timer", "beat"],
        framework_hints={"celery": "Celery Beat", " APScheduler": "Scheduler"},
    )
)
_register(
    Symbol(
        name="EVENT",
        category="ASYNC",
        aliases=["event", "signal", "emit", "on", "listener", "handler"],
        framework_hints={"python": "Event", "fastapi": "EventHandler"},
    )
)
_register(
    Symbol(
        name="PUBSUB",
        category="ASYNC",
        aliases=["pubsub", "publish", "subscribe", "topic", "channel"],
        framework_hints={"redis": "pub/sub", "nats": "JetStream"},
    )
)

# AI symbols
_register(
    Symbol(
        name="EMBEDDING",
        category="AI",
        aliases=["embedding", "vector", "embedding_model", "encode", "text_to_vector"],
        framework_hints={"python": "sentence-transformers", "openai": "ada-002"},
    )
)
_register(
    Symbol(
        name="INFERENCE",
        category="AI",
        aliases=["inference", "predict", "generate", "completion", "chat"],
        framework_hints={"openai": "openai.ChatCompletion", "llama": "inference"},
    )
)
_register(
    Symbol(
        name="CHUNK",
        category="AI",
        aliases=["chunk", "split", "tokenize", "segment", "fragment"],
        framework_hints={
            "python": "langchain",
            "RecursiveCharacterTextSplitter": "split_text()",
        },
    )
)
_register(
    Symbol(
        name="RETRIEVAL",
        category="AI",
        aliases=["retrieval", "search", "find_similar", "similarity", "rank"],
        framework_hints={"qdrant": "search()", "weaviate": "similarity_search()"},
    )
)
_register(
    Symbol(
        name="PROMPT",
        category="AI",
        aliases=["prompt", "template", "system_message", "few_shot", "chain"],
        framework_hints={"langchain": "PromptTemplate", "llamaindex": "Prompt"},
    )
)
_register(
    Symbol(
        name="AGENT",
        category="AI",
        aliases=["agent", "assistant", "assistant", "actor", "agentic"],
        framework_hints={"langchain": "Agent", "autogen": "AssistantAgent"},
    )
)


__all__ = [
    "Symbol",
    "SYMBOL_REGISTRY",
    "match_to_symbol",
]
