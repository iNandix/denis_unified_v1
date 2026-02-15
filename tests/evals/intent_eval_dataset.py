"""Intent evaluation dataset - Golden prompts for testing.

Format: list of dicts with:
- prompt: str
- expected_intent: str
- expected_confident: bool (whether confidence >= 0.72)
- notes: optional notes
"""

INTENT_EVAL_DATASET = [
    # === RUN_TESTS_CI (10 prompts) ===
    {
        "prompt": "Los tests están fallando en CI, puedes revisar?",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Clear test failure mention",
    },
    {
        "prompt": "pytest me da error en test_user.py",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Explicit pytest mention",
    },
    {
        "prompt": "Necesito correr los tests para validar mi cambio",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Run tests intent",
    },
    {
        "prompt": "CI está rojo, hay 3 tests failing",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "CI failure context",
    },
    {
        "prompt": "Failing test en la ruta denis_unified_v1/tests/",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Test failure with path",
    },
    {
        "prompt": "Quiero ejecutar pytest con coverage",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Explicit pytest command",
    },
    {
        "prompt": "Los unit tests no pasan después del refactor",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Unit tests failing",
    },
    {
        "prompt": "Verifica que todos los tests pasen antes del deploy",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Verify tests pass",
    },
    {
        "prompt": "Hay un test que falla intermitentemente",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Flaky test",
    },
    {
        "prompt": "Necesito debuggear por qué falla el test de integración",
        "expected_intent": "run_tests_ci",
        "expected_confident": True,
        "notes": "Debug test failure",
    },
    # === DEBUG_REPO (10 prompts) ===
    {
        "prompt": "Me da un error de importación cuando corro el servidor",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Import error",
    },
    {
        "prompt": "Hay un traceback en el log: ModuleNotFoundError",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Traceback mention",
    },
    {
        "prompt": "El servicio crashea al iniciar, puedes ver el error?",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Crash error",
    },
    {
        "prompt": "Exception en la línea 45 de router.py",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Exception with location",
    },
    {
        "prompt": "Stacktrace muestra error en la conexión a Redis",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Stacktrace mention",
    },
    {
        "prompt": "Hay un bug en el cálculo de latencia",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Bug mention",
    },
    {
        "prompt": "Debuggea por qué no responde el endpoint",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Debug request",
    },
    {
        "prompt": "Error 500 en el health endpoint",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "HTTP error",
    },
    {
        "prompt": "La excepción KeyError ocurre en ciertos requests",
        "expected_intent": "debug_repo",
        "expected_confident": True,
        "notes": "Specific exception",
    },
    {
        "prompt": "No entiendo por qué falla este código...",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Vague error description - es ambiguo",
    },
    # === REFACTOR_MIGRATION (8 prompts) ===
    {
        "prompt": "Necesito migrar de requests a httpx",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Migration intent",
    },
    {
        "prompt": "Refactoriza el handler para usar async/await",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Refactor request",
    },
    {
        "prompt": "Quiero reescribir el parser usando Pydantic v2",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Rewrite with new version",
    },
    {
        "prompt": "Moderniza el código legacy en denis_unified_v1/",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Modernize legacy",
    },
    {
        "prompt": "Upgrade a Python 3.12",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Version upgrade",
    },
    {
        "prompt": "Migrar de Flask a FastAPI",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Framework migration",
    },
    {
        "prompt": "Refactor para separar concerns mejor",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Architecture refactor",
    },
    {
        "prompt": "Cambia la estructura del proyecto a clean architecture",
        "expected_intent": "refactor_migration",
        "expected_confident": True,
        "notes": "Architecture migration",
    },
    # === IMPLEMENT_FEATURE (7 prompts) ===
    {
        "prompt": "Implementa un endpoint para health checks",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Implement endpoint",
    },
    {
        "prompt": "Necesito agregar autenticación JWT",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Add auth feature",
    },
    {
        "prompt": "Crea una feature para rate limiting",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Rate limiting feature",
    },
    {
        "prompt": "Build un sistema de caching para las respuestas",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Build caching system",
    },
    {
        "prompt": "Agrega soporte para WebSockets",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Add websocket support",
    },
    {
        "prompt": "Implementa un nuevo parser para CSV",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Implement parser",
    },
    {
        "prompt": "Necesito una feature para exportar reportes",
        "expected_intent": "implement_feature",
        "expected_confident": True,
        "notes": "Export feature",
    },
    # === OPS_HEALTH_CHECK (6 prompts) ===
    {
        "prompt": "Verifica el estado de salud del sistema",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Health check",
    },
    {
        "prompt": "Haz un probe de todos los engines",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Probe engines",
    },
    {
        "prompt": "Chequea si los servicios están up",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Check services up",
    },
    {
        "prompt": "Status del cluster de inference",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Cluster status",
    },
    {
        "prompt": "Health check del API gateway",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Gateway health",
    },
    {
        "prompt": "Monitorea el estado de Redis y Postgres",
        "expected_intent": "ops_health_check",
        "expected_confident": True,
        "notes": "Monitor services",
    },
    # === EXPLAIN_CONCEPT (6 prompts) ===
    {
        "prompt": "Explica cómo funciona el scheduler",
        "expected_intent": "explain_concept",
        "expected_confident": True,
        "notes": "Explain scheduler",
    },
    {
        "prompt": "Cómo se decide qué engine usar?",
        "expected_intent": "explain_concept",
        "expected_confident": True,
        "notes": "How it works",
    },
    {
        "prompt": "Qué es el internet gate?",
        "expected_intent": "explain_concept",
        "expected_confident": True,
        "notes": "What is X",
    },
    {
        "prompt": "Documenta cómo funciona el fallback...",
        "expected_intent": "write_docs",
        "expected_confident": True,
        "notes": "Document how it works - esto es write_docs, no explain",
    },
    {
        "prompt": "Por qué hay un canary switch?",
        "expected_intent": "explain_concept",
        "expected_confident": True,
        "notes": "Why question",
    },
    {
        "prompt": "Explica el plan-first approach",
        "expected_intent": "explain_concept",
        "expected_confident": True,
        "notes": "Explain approach",
    },
    # === INCIDENT_TRIAGE (5 prompts) ===
    {
        "prompt": "Hay un incidente en producción, el servicio está down",
        "expected_intent": "incident_triage",
        "expected_confident": True,
        "notes": "Production down",
    },
    {
        "prompt": "Sev1: No responde el API principal",
        "expected_intent": "incident_triage",
        "expected_confident": True,
        "notes": "Sev1 incident",
    },
    {
        "prompt": "Alerta crítica: latencia > 10s",
        "expected_intent": "incident_triage",
        "expected_confident": True,
        "notes": "Critical alert",
    },
    {
        "prompt": "Outage en el servicio de autenticación",
        "expected_intent": "incident_triage",
        "expected_confident": True,
        "notes": "Service outage",
    },
    {
        "prompt": "Incidente de seguridad detectado",
        "expected_intent": "incident_triage",
        "expected_confident": True,
        "notes": "Security incident",
    },
    # === TOOLCHAIN_TASK (5 prompts) ===
    {
        "prompt": "Actualiza la imagen de Docker",
        "expected_intent": "toolchain_task",
        "expected_confident": True,
        "notes": "Docker task",
    },
    {
        "prompt": "Configura el pipeline de CI/CD",
        "expected_intent": "toolchain_task",
        "expected_confident": True,
        "notes": "CI/CD pipeline",
    },
    {
        "prompt": "Despliega a Kubernetes",
        "expected_intent": "toolchain_task",
        "expected_confident": True,
        "notes": "K8s deploy",
    },
    {
        "prompt": "Actualiza terraform para el nuevo cluster",
        "expected_intent": "toolchain_task",
        "expected_confident": True,
        "notes": "Terraform task",
    },
    {
        "prompt": "Configura GitHub Actions para tests",
        "expected_intent": "toolchain_task",
        "expected_confident": True,
        "notes": "GitHub Actions",
    },
    # === WRITE_DOCS (4 prompts) ===
    {
        "prompt": "Escribe documentación para el nuevo endpoint",
        "expected_intent": "write_docs",
        "expected_confident": True,
        "notes": "Write endpoint docs",
    },
    {
        "prompt": "Actualiza el README con las nuevas instrucciones",
        "expected_intent": "write_docs",
        "expected_confident": True,
        "notes": "Update README",
    },
    {
        "prompt": "Agrega docstrings al módulo de scheduler",
        "expected_intent": "write_docs",
        "expected_confident": True,
        "notes": "Add docstrings",
    },
    {
        "prompt": "Documenta el proceso de deployment",
        "expected_intent": "write_docs",
        "expected_confident": True,
        "notes": "Document deployment",
    },
    # === AMBIGUOUS / LOW CONFIDENCE (8 prompts) ===
    {
        "prompt": "Necesito ayuda con el código",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Too vague",
    },
    {
        "prompt": "Hola",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Just greeting",
    },
    {
        "prompt": "Me puedes ayudar?",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "No specific task",
    },
    {
        "prompt": "Revisa esto",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "No context",
    },
    {
        "prompt": "Hay algo raro",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Vague description",
    },
    {
        "prompt": "Necesito cambiar cosas",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Too broad",
    },
    {
        "prompt": "El sistema",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Incomplete",
    },
    {
        "prompt": "Fix",
        "expected_intent": "unknown",
        "expected_confident": False,
        "notes": "Single word, no context",
    },
]

# Statistics
INTENT_COUNTS = {
    "run_tests_ci": 10,
    "debug_repo": 10,
    "refactor_migration": 8,
    "implement_feature": 7,
    "ops_health_check": 6,
    "explain_concept": 6,
    "incident_triage": 5,
    "toolchain_task": 5,
    "write_docs": 4,
    "unknown": 8,
}

TOTAL_PROMPTS = len(INTENT_EVAL_DATASET)
EXPECTED_ACCURACY = 0.90  # 90% target
