# DENIS Workflow Contract

## Output Contract
Every response must follow this structure:
- Plan: Brief plan (max 7 bullets).
- Changes: Exact changes (files/settings/memories/ignore).
- Commands: Commands to execute (in order).
- Verification: Smokes/artifacts checks.
- Rollback: Risks + rollback steps.

## Definition of Done
- Run tests/smokes where applicable.
- Generate artifacts/*.json if relevant.
- Ensure no stubs/TODOs; all runnable.
- Confirm deterministic behavior.
