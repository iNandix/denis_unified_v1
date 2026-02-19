# How to Enable Denis Middleware in OpenCode

## Overview

This guide explains how to use Denis as a middleware proxy for OpenCode. Denis acts as a middleware layer that:
1. Prepares prompts/context before sending to cloud LLMs
2. Optionally postprocesses responses
3. Runs in low-impact mode to avoid starving Denis

## Architecture

```
User → OpenCode → [Denis Middleware] → Cloud LLM
                ↓
         /middleware/prepare
         /middleware/postprocess (optional)
```

## Prerequisites

1. **Denis API Server** must be running on port 19000 (default; configurable)
2. **FastAPI dependencies** installed: `pip install fastapi pydantic uvicorn`

## Quick Start

### 1. Start Denis API Server

```bash
cd denis_unified_v1
./scripts/run_denis_api.sh 19000
```

Or manually:
```bash
cd denis_unified_v1
export PYTHONPATH="$(pwd)"
python3 -m uvicorn api.fastapi_server:create_app --factory --host 127.0.0.1 --port 19000
```

### 2. Enable Middleware in OpenCode

Set environment variables:

```bash
export OPENCODE_DENIS_MIDDLEWARE=1
export OPENCODE_DENIS_URL="http://127.0.0.1:19000"
export OPENCODE_DENIS_TIMEOUT_MS=800
```

Or source the aliases:
```bash
source ~/.opencode/efficiency-aliases.sh
```

### 3. Verify Setup

```bash
# Check Denis is running
curl http://127.0.0.1:19000/middleware/status
# Should return: {"status":"healthy","mode":"low_impact","timeout_ms":800}

# Check OpenCode diagnostics
~/.opencode/bin/opencode-efficiency doctor
```

## Configuration Options

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OPENCODE_DENIS_MIDDLEWARE` | 0 | Enable/disable middleware (0 or 1) |
| `OPENCODE_DENIS_URL` | http://127.0.0.1:19000 | Denis server URL |
| `OPENCODE_DENIS_TIMEOUT_MS` | 800 | Max time for middleware calls |

## Middleware Endpoints

### POST /middleware/prepare

Prepares prompt/context for cloud LLM.

**Request:**
```json
{
  "session_id": "session-123",
  "user_text": "Write a function to sort an array in Python",
  "target_provider": "openrouter",
  "target_model": "qwen3-coder",
  "budget": {
    "max_prompt_tokens": 20000,
    "max_output_tokens": 1500
  },
  "artifacts": [],
  "mode": "low_impact"
}
```

**Response:**
```json
{
  "prepared_prompt": "You are a coding assistant.\n\nTask: ...",
  "contextpack": {
    "intent": "write_code",
    "constraints": ["python"],
    "output_format": "tagged_json_block"
  },
  "recommended": {
    "output_mode": "tagged_json_block",
    "stop": ["<end>", "Done."],
    "max_output_tokens": 1500
  },
  "trace_ref": {
    "session_id": "session-123",
    "turn_id": "uuid",
    "trace_ids": []
  }
}
```

### POST /middleware/postprocess

Validates/repairs cloud output (optional).

**Request:**
```json
{
  "session_id": "session-123",
  "target_model": "qwen3-coder",
  "raw_output": "{\"result\": \"success\"}",
  "output_mode": "json"
}
```

**Response:**
```json
{
  "final_output": "{\"result\": \"success\"}",
  "parse_ok": true,
  "repairs_applied": [],
  "trace_ref": {...}
}
```

## Low-Impact Mode

The middleware runs in low-impact mode by default:
- Max time: 800ms
- Max local tokens: 512
- Operations: classify, summarize, retrieve, prompt_pack, policy_check
- Never: run long research or generate code patches

## Fallback Behavior

If Denis middleware is unavailable or times out:
- OpenCode falls back to local pipeline (makina_filter, artifactizer, budgeter)
- No error is raised to user
- Cloud LLM remains default responder

## Rollback

To disable middleware and use original behavior:

```bash
export OPENCODE_DENIS_MIDDLEWARE=0
```

Or in opencode.json, remove the denis-middleware-client.js from plugins array.

## Testing

Run middleware tests:
```bash
cd denis_unified_v1
python3 -m pytest tests/test_denis_middleware_api.py -v
```

## Troubleshooting

### "Connection refused" errors
- Check Denis is running: `curl http://127.0.0.1:19999/middleware/status`
- Verify port matches `OPENCODE_DENIS_URL`

### Slow responses
- Reduce `OPENCODE_DENIS_TIMEOUT_MS` (default: 800)
- Check Denis server logs

### Middleware not called
- Ensure `OPENCODE_DENIS_MIDDLEWARE=1` is set
- Check OpenCode logs for "[denis-middleware]" warnings
