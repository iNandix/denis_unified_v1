# Intent Router Contract

## Overview

The Intent Router is a universal router that consumes `MakinaOutput` and decides which model to route to based on intent, quota availability, and session context.

## Flow

```
prompt → makina_filter → MakinaOutput → IntentRouter → RoutedRequest → model
```

## Usage

```python
from denis_unified_v1.inference.intent_router import route_input

# Single call - filter + route + enrich
result = route_input(
    prompt="crea un endpoint en fastapi",
    session_id="user_123",
    context_refs=["file:///app/main.py"]
)

print(result.model)  # e.g., "groq", "llama_local", "claude"
print(result.implicit_tasks)  # ["READ target files before writing", ...]
```

## QuotaRegistry

Manages model quotas and availability.

### Models

| Model | Env Variable | Best For | Cost Tier |
|-------|-------------|----------|-----------|
| claude | ANTHROPIC_API_KEY | architecture, long_context, complex_reasoning | HIGH |
| groq | GROQ_API_KEY | fast_code, debug_repo, run_tests_ci | FREE |
| openrouter | OPENROUTER_API_KEY | reasoning, explain_concept | MEDIUM |
| llama_local | - | repetitive, private, toolchain_task | ZERO |

### Methods

```python
registry = get_quota_registry()
registry.get_available_models()  # → ["groq", "llama_local", ...]
registry.get_best_model_for("implement_feature")  # → "groq"
registry.mark_quota_exhausted("groq", 60)  # Mark as exhausted for 60s
registry.is_available("groq")  # → bool
```

## ImplicitTasks

Hygiene tasks automatically added based on intent.

### Task Map

| Intent | Implicit Tasks |
|--------|---------------|
| implement_feature | READ target files before writing, VERIFY imports, RUN tests, CHECK DO_NOT_TOUCH |
| debug_repo | READ error first, CHECK git diff, VERIFY fix |
| refactor_migration | SNAPSHOT behavior, VERIFY identical, CHECK imports |
| run_tests_ci | VERIFY test env, CHECK services |
| toolchain_task | VERIFY tool in PATH, CHECK dependencies |

### Session Enrichment

Queries Neo4j for files modified in the current session and adds them to `do_not_touch_auto`.

```python
context = enrich_with_session("implement_feature", "session_123")
# → EnrichedContext(implicit_tasks=[...], do_not_touch_auto=[...])
```

## IntentRouter

The main router class.

### Routing Logic

1. If `missing_inputs` not empty → block, ask for inputs
2. If confidence < 0.55 → route to `llama_local` (don't waste quota)
3. Query `quota_registry.get_best_model_for(intent)`
4. If optimal model unavailable → use fallback chain
5. **Always fail-open to llama_local**

### Fallback Chain

```python
FALLBACK_CHAIN = {
    "claude": ["openrouter", "groq", "llama_local"],
    "groq": ["llama_local"],
    "openrouter": ["groq", "llama_local"],
    "llama_local": ["llama_local"],
}
```

## RoutedRequest

The output of routing.

```python
@dataclass
class RoutedRequest:
    model: str                           # Selected model
    intent: str                          # Detected intent
    prompt: str                          # Original prompt
    implicit_tasks: List[str]            # Hygiene tasks
    context_prefilled: Dict[str, Any]   # Session context
    do_not_touch_auto: List[str]        # Inferred protected paths
    constraints: List[str]              # From makina_filter
    acceptance_criteria: List[str]       # From makina_filter
    routing_trace: Dict[str, Any]       # Debug info
    fallback_used: bool                  # Did we fallback?
    blocked: bool                       # Was request blocked?
    block_reason: Optional[str]          # Why blocked?
```

## route_input() - Unified API

The public entry point that combines filter + router in one call.

```python
def route_input(
    prompt: str,
    session_id: str = "default",
    context_refs: List[str] = None
) -> RoutedRequest
```

### Flow

1. `pre_execute_hook(prompt, context_refs)` - Check if blocked
2. `filter_input_safe({prompt, context_refs})` - Detect intent
3. If `missing_inputs` → block
4. `IntentRouter().route_safe(makina_output, prompt, session_id)`
5. Return `RoutedRequest`

## Example

```python
from denis_unified_v1.inference.intent_router import route_input

# User asks to create a feature
result = route_input(
    prompt="crea un endpoint GET /users en fastapi",
    session_id="sess_abc"
)

# Result
print(result.model)           # "groq" (best for implement_feature)
print(result.intent)          # "implement_feature"
print(result.implicit_tasks)  # ["READ target files before writing", ...]
print(result.constraints)     # ["python", "async"]
print(result.blocked)         # False

# If prompt is too short
result = route_input(prompt="haz algo")
print(result.blocked)         # True
print(result.block_reason)   # "Missing inputs: ['intent_unclear']"

# If confidence is low
result = route_input(prompt="test", context_refs=[])
print(result.model)           # "llama_local" (low confidence → local)
```
