# WORKFLOWS DENIS

To install dev tools: pip install -r requirements-dev.txt

## 1) Quick Change (One File)
- Edit file.
- Run ruff/pytest.
- Run smoke phase.
- Check artifact.

## 2) Contracts Change
- Get approval.
- Scan consumers.
- Make change.
- Run preflight.
- Run smoke.
- Check artifact.

## 3) Sprint Orchestrator Change
- Run phase11 smoke.
- Check manager view.
- Check approvals pending.

## 4) Inference/Stream
- Run streaming smoke.
- Check TTFT budget.
- Test fallback.

## 5) IDE Graph
- docker compose up -d
- Write sample node.
- Readback.
- docker compose down

## 6) MCP Troubleshooting
- Activate/deactivate servers.
- Check tool limit (~100).
- Restart Windsurf.
