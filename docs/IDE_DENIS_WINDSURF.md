# IDE DENIS WINDSURF

## Rules Files

- **00-denis-premium-agent.md**: Defines identity as premium agentic AI, output contract (terse, direct, fact-based), no-stubs, determinism, premium behaviors (speculative validation + practical ToM).

- **10-denis-execution-policy.md**: Classifies commands:
  - SAFE: read-only ops, build/test.
  - CAUTION: warn before executing.
  - DESTRUCTIVE: require explicit "yes/no" confirmation.

- **20-denis-quality-gates.md**: Use ruff for lint, pytest for tests, mypy for types, smoke tests; set timeouts, avoid infinite loops.

- **30-denis-contracts-approvals.md**: Changes to contracts/* require approval; explain impact + rollback; locate consumers before modifying.

- **40-denis-sprint-orchestrator-smokes.md**: Smoke tests must timeout, generate artifacts/*.json.

## Hooks

Hooks execute scripts pre/post actions, block with exit code 2.

- **pre_run_command**: block_dangerous.py - parses stdin JSON for command_line, blocks DESTRUCTIVE patterns (rm -rf, git reset --hard, etc.), logs to blocked_commands.log.

- **pre_read_code**: block_secrets_read.py - blocks reading .env, keys, tokens, etc., logs to blocked_reads.log.

- **pre_mcp_tool_use**: mcp_allowlist.py - allows only denis-files, denis-git, web-fetch, agent-memory, time, denis-control-plane, seq-thinking; blocks others, logs to blocked_mcps.log.

- **post_run_command**: post_run_log.py - logs command + exit_status to commands.log.

- **post_write_code**: post_gates.py - compile check, suggests commands based on path (smoke for sprintorchestrator/scripts/phase, preflight+smoke for contracts).

## CoT adaptativa con IDE Graph
Si el grafo devuelve poca info, el agente hace más análisis local (buscar GH/HF).
Si el grafo muestra patrón claro (componentes, tests, proposals), el agente va directo a acciones.

- **post_cascade_response**: post_log.py - logs response summary + files_touched to cascade_responses.log.

## MCPs

Activate in ~/.codeium/windsurf/mcp_config.json.

- denis-control-plane: tools for health_check, run_smoke, list_artifacts, read_artifact, kill_port (DESTRUCTIVE requires confirmation).

Deactivate unwanted in Windsurf MCP panel (~100 limit).

## Policy Examples

- SAFE: `ls`, `git status`.
- CAUTION: `git pull` (warn).
- DESTRUCTIVE: `rm -rf contracts/` (confirm yes/no).
