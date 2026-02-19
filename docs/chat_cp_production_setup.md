# Chat CP Production Setup

## Overview
Chat CP supports `openai`, `anthropic`, and `local` fallback providers.
Secrets are loaded from OS keyring only. Plaintext API keys in `.env` are not supported.

## 1) Store Secrets in Keyring
Set OpenAI:

```bash
python3 -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY
```

Set Anthropic:

```bash
python3 -m denis_unified_v1.chat_cp.secrets set ANTHROPIC_API_KEY
```

List status (masked, no values):

```bash
python3 -m denis_unified_v1.chat_cp.secrets list
```

## 2) Verify Keyring Health
Run secrets doctor:

```bash
python3 tools/chat_cp_secrets_doctor.py --provider auto
```

JSON output:

```bash
python3 tools/chat_cp_secrets_doctor.py --provider auto --json
```

## 3) Run Chat CP Preflight
Preflight checks keyring, secret presence, DNS, and TCP connectivity to provider endpoints.

OpenAI:

```bash
python3 tools/chat_cp_preflight.py --provider openai
```

Anthropic:

```bash
python3 tools/chat_cp_preflight.py --provider anthropic
```

Auto mode (degraded allowed):

```bash
python3 tools/chat_cp_preflight.py --provider auto
```

Strict mode (fail if not ready):

```bash
python3 tools/chat_cp_preflight.py --provider openai --strict
```

## 4) Run Smoke Tests
Direct provider smoke:

```bash
python3 tools/chat_cp_smoke.py --provider openai --message "ping"
python3 tools/chat_cp_smoke.py --provider anthropic --message "ping"
```

Router smoke with fallback:

```bash
python3 tools/chat_cp_smoke.py --provider auto --shadow-mode --message "ping"
```

Skip preflight:

```bash
python3 tools/chat_cp_smoke.py --provider openai --no-preflight
```

## 5) Common Failure Modes
- `missing_secret`: Key not found or keyring inaccessible.
  - Action: run secrets doctor, then set secret again.
- `auth_error`: API key invalid/revoked.
  - Action: rotate key and update keyring.
- `quota_exceeded`: account credits or quota exhausted.
  - Action: top up quota or rely on fallback provider.
- `network_error` / endpoint DNS/TCP failure:
  - Action: verify outbound network/firewall/DNS.
- Circuit breaker opens after repeated provider failures:
  - Action: provider is temporarily skipped until cooldown expires.

## Notes
- Chat CP never logs raw key values.
- Prompts are not persisted in cleartext; routing traces use hashes.
- Feature flag and endpoint wiring remain fail-soft: fallback to `local` when external providers fail.

## Vault-lite Fallback (Headless/Systemd)
If keyring/DBus is not available, you can use a vault-lite file (owner-only perms).
See: `docs/secrets_resolution_policy.md`.
