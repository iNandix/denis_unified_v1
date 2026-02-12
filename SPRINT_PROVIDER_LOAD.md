# Sprint Provider Load (Real Tools Only)

## Objective
Configure real providers for sprint workers and adapt request JSON to each API format automatically.

## 1. Configure Providers
Use:

```bash
python3 scripts/sprintctl.py providers-template --out .env.sprint.providers.example
```

Then copy required keys into `.env` (never commit secrets).

Slot-1 provider pin:
- Set `DENIS_SPRINT_PRIMARY_PROVIDER=denis_canonical` (default).
- Configure canonical endpoint via `DENIS_CANONICAL_URL` (default: `http://127.0.0.1:9999/v1/chat/completions`).

## 2. Verify Real Provider Status

```bash
python3 scripts/sprintctl.py providers
```

`configured=yes` means provider can be assigned to workers.

## 3. JSON Adaptation Per Model/API
Show adapted payload without sending request:

```bash
python3 scripts/sprintctl.py adapt claude --message "resume el sprint"
python3 scripts/sprintctl.py adapt groq --message "analiza este cambio"
python3 scripts/sprintctl.py adapt llama_node2 --message "compila este plan"
```

Formats supported:
- `openai_chat`: OpenAI-compatible chat payload.
- `anthropic_messages`: Claude native `messages` format.
- `celery_task`: queue dispatch payload for worker execution.

## 4. Dispatch Real Calls
Direct API or Celery queue dispatch based on provider mode:

```bash
python3 scripts/sprintctl.py dispatch <session_id> groq --message "estado gate"
python3 scripts/sprintctl.py dispatch <session_id> llama_node2 --message "ejecuta tarea B"
```

- `llama_node1/2` in `MODE=celery` will enqueue tasks to `DENIS_SPRINT_LLAMA_NODE*_QUEUE`.
- `MODE=direct` sends HTTP request to `DENIS_SPRINT_LLAMA_NODE*_URL`.

Automatic dispatch for all workers in session:

```bash
python3 scripts/sprintctl.py start --prompt "Sprint A/B kickoff" --workers 2 --autodispatch
python3 scripts/sprintctl.py autodispatch <session_id>
```

Live UX during sprint:

```bash
python3 scripts/sprintctl.py dashboard <session_id>
python3 scripts/sprintctl.py tail <session_id> --worker worker-1 --kind worker.dispatch --follow
```

Fallback behavior:
- If assigned provider is terminal-only or unavailable, dispatcher retries with real providers.
- Preferred fallback order: `celery_crewai -> llama_node1 -> llama_node2 -> legacy_core -> groq -> openrouter -> vllm -> claude`.

## 5. MCP Tools Visibility
Use real MCP endpoint (not file catalogs by default):

```bash
python3 scripts/sprintctl.py mcp-tools
```

And during an active session:

```bash
python3 scripts/sprintctl.py mcp-tools --session-id <session_id> --worker worker-1
```

## Recommended Setup for llama.cpp
- Preferred: `celery + crewai` workers (`MODE=celery`) for orchestration and resilience.
- Fallback: `MODE=direct` only for debugging specific endpoint behavior.

MCP base URL resolution:
- `DENIS_SPRINT_MCP_BASE_URL` if defined.
- else first `DENIS_BASELINE_ENDPOINTS` endpoint on `:8084`.
- else `DENIS_MASTER_URL`.
- else default `http://127.0.0.1:8084`.

## Rollback
```bash
git restore --worktree sprint_orchestrator scripts/sprintctl.py .env.phase0.example SPRINT_PROVIDER_LOAD.md
```
