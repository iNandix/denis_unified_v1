# Secrets Resolution Policy (Chat CP)

## Goals
- No secrets in code, logs, prompts, or repo.
- Production uses OS keyring by default.
- Provide a predictable escape hatch when DBus/keyring is unavailable (headless/systemd).

## Resolution Order
Chat CP resolves secrets in this order:
1. **OS keyring** (primary)
2. **Vault-lite file** (fallback A)
3. **`secret-tool`** (fallback B, if installed)
4. **Environment variables** (DEV ONLY, opt-in)

## Vault-lite File
Purpose: allow running without DBus/keyring in headless environments.

Default path:
- `~/.config/denis/chat_cp.vault`

Override:
- `DENIS_CHAT_CP_VAULT_FILE=/path/to/chat_cp.vault`

Format:
```text
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

Security requirements:
- Owner-only permissions: `chmod 600` (or `chmod 400`)
- Owned by the service user
- Never committed to git

## Environment Variable Fallback (DEV ONLY)
Disabled by default.

To enable:
- `DENIS_CHAT_CP_ALLOW_ENV_SECRETS=1`

Then Chat CP may read:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

This is intended for local development only.

## Diagnostics
Use:
```bash
python3 tools/chat_cp_secrets_doctor.py --provider auto
python3 tools/chat_cp_preflight.py --provider auto
```

These commands report presence/status only, never secret values.
