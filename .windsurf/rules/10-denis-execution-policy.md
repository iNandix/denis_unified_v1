# DENIS Execution Policy

## Command Classification
Classify each command into one of three classes and follow the policy strictly.

### A) SAFE (auto-executable without asking)
- Read-only: ls, cat, rg/grep, find, git status/diff/log, python -c "import ...", pytest -q, ruff, mypy, curl GET to /health, docker ps, systemctl status.
- Build/test: make preflight, scripts/smoke*.py, lint/typecheck.

### B) CAUTION (execute but warn in one line before)
- git checkout/switch, git pull/rebase (if no local changes), pip install (in venv), docker compose up (without --force-recreate), systemctl restart (only repo services, clearly identified).

### C) DESTRUCTIVE (requires explicit "yes/no" confirmation before executing)
- rm -rf, dd, mkfs, parted, wipefs, chmod/chown massive, kill -9 (except own processes with confirmed PID), git reset --hard, git clean -fdx, force push, truncate, overwrite sensitive config files, change contracts/* or critical gates without approval.
- Any command that could delete data, lose work, or affect system outside repo.

If in doubt, elevate to DESTRUCTIVE.
