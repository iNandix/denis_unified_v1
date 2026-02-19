# Denis Integration - PearAI Premium Code Agent

## Overview

This document describes how to configure Denis as a premium code agent in PearAI with full Control Plane integration.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    PearAI       │────▶│  Denis API       │────▶│  Control Plane  │
│  ( IDE + Agent) │     │  (port 9100)     │     │  (port 8765)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │  Event Bus       │     │  Neo4j Graph    │
                        │  (WebSocket)     │     │  (State/History)│
                        └──────────────────┘     └─────────────────┘
```

## Prerequisites

1. **Denis Server Running**: API server on port 9100
2. **Intent Queue Running**: Control plane on port 8765
3. **Neo4j**: Graph database for state tracking
4. **PearAI Installed**: AI code editor

## Services Configuration

### 1. Start All Services

```bash
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
source .env

# Terminal 1: API Server (OpenAI compatible)
python3 -m uvicorn api.fastapi_server:create_app --factory --host 0.0.0.0 --port 9100

# Terminal 2: Intent Queue (Control Plane)
python3 -m uvicorn control_plane.intent_queue_app:app --host 0.0.0.0 --port 8765
```

### 2. Verify Services

```bash
# API Server
curl -s http://localhost:9100/health | jq

# Intent Queue
curl -s http://localhost:8765/health | jq

# Check pending intents
curl -s http://localhost:8765/intent/pending | jq
```

## PearAI Configuration

### config.json

Open PearAI command palette: `Cmd/Ctrl+Shift+P` > "Open config.json"

```json
{
  "models": [
    {
      "title": "Denis Premium Code Agent",
      "model": "denis-unified-v1",
      "provider": "openai",
      "apiBase": "http://localhost:9100/v1",
      "apiKey": "denis-local",
      "contextLength": 128000,
      "systemMessage": "You are Denis, an expert AI code agent with full control plane integration. When performing risky actions (file modifications, git operations, system commands), you MUST submit an intent to the control plane for human approval before executing. Use the Intent Queue API at http://localhost:8765 for this purpose."
    },
    {
      "title": "Denis Fast Mode",
      "model": "denis-unified-v1",
      "provider": "openai",
      "apiBase": "http://localhost:9100/v1",
      "apiKey": "denis-local",
      "contextLength": 64000,
      "systemMessage": "You are Denis in fast mode. For simple tasks, execute directly. Only submit intents for destructive operations."
    }
  ],
  "tabAutocompleteModel": {
    "title": "Denis Code Completion",
    "provider": "openai",
    "model": "denis-unified-v1",
    "apiBase": "http://localhost:9100/v1",
    "apiKey": "denis-local"
  }
}
```

## Control Plane Integration

### Intent Queue API

When Denis needs human approval, it sends intents to the Control Plane:

#### Create Intent
```bash
curl -X POST http://localhost:8765/intent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "pearai",
    "session_id": "session-123",
    "semantic_delta": {
      "action": "file_write",
      "path": "/project/src/main.py",
      "risk": "high"
    },
    "risk_score": 7,
    "source_node": "pearai"
  }'
```

#### Resolve Intent
```bash
curl -X POST "http://localhost:8765/intent/{intent_id}/resolve" \
  -H "Content-Type: application/json" \
  -d '{
    "human_id": "jotah",
    "decision": "approved",
    "notes": "Approved - needed for feature implementation"
  }'
```

#### List Pending
```bash
curl -s http://localhost:8765/intent/pending
```

#### List Decisions
```bash
curl -s http://localhost:8765/intent/decisions?n=20
```

## Event Bus Integration

### WebSocket Events

Connect to receive real-time events:

```javascript
const ws = new WebSocket('ws://localhost:9100/ws/events');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, data.payload);
};
```

### Event Types

| Channel | Events |
|---------|--------|
| `ops` | `run.step`, `error`, `graph.mutation` |
| `tool` | `tool.start`, `tool.complete`, `tool.error` |
| `neuro` | `neuro.layer`, `persona.state` |
| `control_room` | `approval.request`, `approval.resolved` |

## Agent Toolset

Denis provides these tools for code tasks:

1. **File Operations**: read, write, edit files
2. **Git Operations**: status, diff, commit, push
3. **Search**: grep, glob, find symbols
4. **Execution**: run commands, tests
5. **Context**: query knowledge graph, retrieve code context

## MCP Tools Configuration

Denis exposes all capabilities as MCP tools that PearAI can use natively.

### Start MCP Server

```bash
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
python3 tools/mcp_denis_server.py
```

The MCP server runs on port 9101 by default.

### Available Tools

| Tool | Category | Risk | Description |
|------|----------|------|-------------|
| `denis_read_file` | file | low | Read file contents |
| `denis_write_file` | file | high | Write to file |
| `denis_edit_file` | file | high | Edit file by replacing text |
| `denis_grep` | search | low | Search regex in files |
| `denis_glob` | search | low | Find files by glob pattern |
| `denis_list_dir` | file | low | List directory contents |
| `denis_execute` | execution | critical | Execute shell command |
| `denis_git_status` | git | low | Git status |
| `denis_git_diff` | git | low | Git diff |
| `denis_query_graph` | knowledge | low | Query Neo4j knowledge graph |
| `denis_search_symbol` | search | low | Search code symbols |
| `denis_submit_intent` | control_plane | medium | Submit intent for approval |
| `denis_check_pending_intents` | control_plane | low | Check pending intents |

### Using Tools

#### Direct HTTP API

```bash
# List available tools
curl -s http://localhost:9101/tools | jq

# Call a tool
curl -s -X POST http://localhost:9101/tools/denis_read_file/call \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"file_path": "README.md"}}'
```

#### MCP Protocol

```bash
# List tools (MCP protocol)
curl -s -X POST http://localhost:9101/mcp/tools/list

# Call tool (MCP protocol)
curl -s -X POST http://localhost:9101/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "denis_grep", "arguments": {"pattern": "def main", "include": "*.py"}}'
```

## Risk Levels

| Level | Actions | Control Plane |
|-------|---------|---------------|
| LOW | Read files, search, grep | Direct execution |
| MEDIUM | Create files, git operations | Notify only |
| HIGH | Modify files, shell commands | Requires approval |
| CRITICAL | System commands | Explicit approval + timeout |

## Example Workflow

1. **User asks**: "Refactor the authentication module"
2. **Denis analyzes**: Creates execution plan with risk assessment
3. **Intent submitted**: Sends to Control Plane with risk_score=8
4. **Human approves**: Via popup or Intent Queue API
5. **Execution**: Denis executes plan, streaming results
6. **Completion**: Event emitted to event bus

## Troubleshooting

### Services Not Running

```bash
# Check ports
ss -tlnp | grep -E ':(9100|8765)'

# Restart services
./scripts/start_all.sh
```

### Intent Not Appearing

```bash
# Check Neo4j
curl -s http://localhost:9100/health | jq '.components.neo4j'
```

### WebSocket Connection Failed

```bash
# Check WS endpoint
curl -s http://localhost:9100/ws/events
```

## Environment Variables

Key variables in `.env`:

```bash
DENIS_PERSONA_URL=http://localhost:8084
NEO4J_URI=bolt://localhost:7687
CONTROL_PLANE_MODE=dev
```
