# OpenCode Adapter - Reference for Denis Code CLI

## Overview
OpenCode (sst/opencode) is a TUI-based AI code assistant with tool execution and permissions.

## Relevant Architecture
- CLI with commands: run, serve, mcp, auth, models, session
- run --format json: emits raw JSON events for automation
- MCP support for external tools
- Permission system for tool approval

## Integration Notes
- Use OpenCode as UI reference, but build native Denis CLI
- MCP bridge: expose Denis tools via MCP server
- Tool schema: assistant_message + tool_calls array
- ReAct loop: query → validate → approve → execute → repeat

## Commands to inspect OpenCode
```bash
cd ~/ws/opencode
npm run build  # or equivalent
./bin/opencode run "list files" --format json
```

## Denis CLI Goals
- Native Python CLI
- Denis as conversational engine
- Tool approval via graph or interactive
- Workspace detection and context building
