# CONTEXTPACK: Chat Control Plane (Chat CP)

## Overview

Chat Control Plane is a multi-provider chat abstraction layer with:
- **OpenAI** provider
- **Anthropic** provider
- **Local fallback** provider (fail-open)

## Secrets Management

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Chat CP Providers                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │
│  │  OpenAI     │  │  Anthropic  │  │  Local Fallback │    │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘    │
│         │                │                    │             │
│         └────────────────┴────────────────────┘             │
│                          │                                  │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │   secrets.py         │                      │
│              │   (keyring backend)  │                      │
│              └───────────┬───────────┘                      │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         ▼                ▼                ▼                │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐       │
│  │ GNOME      │   │ macOS      │   │ Windows    │       │
│  │ Secret     │   │ Keychain   │   │ Credential │       │
│  │ Service    │   │            │   │ Manager    │       │
│  └────────────┘   └────────────┘   └────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Secrets Stored

| Secret Name | Provider | Required |
|-------------|----------|----------|
| `OPENAI_API_KEY` | OpenAI | No (fallback to local) |
| `ANTHROPIC_API_KEY` | Anthropic | No (fallback to local) |

### Environment Variables (Feature Flags Only)

These remain in `.env` - no secrets:

| Variable | Default | Description |
|----------|---------|-------------|
| `DENIS_ENABLE_CHAT_CP` | false | Enable Chat CP |
| `DENIS_CHAT_CP_SHADOW_MODE` | false | Log without executing |
| `DENIS_CHAT_CP_GRAPH_WRITE` | false | Write traces to Neo4j |

## Provisioning Secrets

### Prerequisites

```bash
# Install keyring package
pip install keyring

# For GNOME/Linux (usually pre-installed)
# For macOS: uses Keychain
# For Windows: uses Credential Manager
```

### Node: nodomac

```bash
# Interactive (will prompt for password securely)
python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY

# Or pipe from password manager
echo "sk-..." | python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY

# Verify
python -m denis_unified_v1.chat_cp.secrets get OPENAI_API_KEY

# Check keyring status
python -m denis_unified_v1.chat_cp.secrets check
```

### Node: nodo1 (denis_unified_v1)

Same commands - keyring is per-user, so secrets sync across nodes if same user.

### Node: nodo2

```bash
# Run via SSH
ssh nodo2 "python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY"
```

### First Access Behavior

1. **Keyring locked**: OS popup appears asking to unlock
2. **Secret missing**: Provider returns `missing_secret` error, fallback kicks in
3. **Secret present**: Provider works normally

## Migration from .env

### Before (NOT RECOMMENDED)

```bash
# DON'T do this - secrets in .env
echo "OPENAI_API_KEY=sk-..." >> .env
```

### After (RECOMMENDED)

```bash
# Store in keyring
python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY

# Verify it's not in .env
grep OPENAI_API_KEY .env  # Should return nothing
```

## CLI Commands

```bash
# Check keyring availability
python -m denis_unified_v1.chat_cp.secrets check

# List known secrets
python -m denis_unified_v1.chat_cp.secrets list

# Get a secret (masked)
python -m denis_unified_v1.chat_cp.secrets get OPENAI_API_KEY

# Set a secret (interactive prompt)
python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY

# Set a secret (from pipe)
echo "sk-..." | python -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY

# Delete a secret
python -m denis_unified_v1.chat_cp.secrets delete OPENAI_API_KEY
```

## Testing

### Smoke Test

```bash
# Test with local provider (no secrets required)
DENIS_ENABLE_CHAT_CP=1 python -c "
from denis_unified_v1.chat_cp.chat_router import ChatRouter
router = ChatRouter()
print('Providers:', list(router.providers.keys()))
print('OpenAI configured:', router.providers['openai'].is_configured())
print('Anthropic configured:', router.providers['anthropic'].is_configured())
print('Local configured:', router.providers['local'].is_configured())
"
```

### With Real Secrets

```bash
# After provisioning secrets
DENIS_ENABLE_CHAT_CP=1 python -c "
from denis_unified_v1.chat_cp.chat_router import ChatRouter
import asyncio

async def test():
    router = ChatRouter()
    result = await router.chat({'messages': [{'role': 'user', 'content': 'Hi'}]})
    print(result)

asyncio.run(test())
"
```

## Troubleshooting

### "Keyring not available"

```bash
# Install keyring with all backends
pip install keyring[all]

# Or install specific backend
# Linux: apt install libsecret-tools
# macOS: should work out of box
# Windows: should work out of box
```

### "Keyring is locked"

- Unlock via OS (e.g., `seahorse` on GNOME, or login)
- Or set secrets before first API call

### "Secret not found"

```bash
# Check what's in keyring
python -m denis_unified_v1.chat_cp.secrets list

# Verify the secret name
python -m denis_unified_v1.chat_cp.secrets get OPENAI_API_KEY
```

## Security Notes

- Secrets stored in OS keyring (encrypted at rest)
- No secrets in `.env` or committed to repo
- Keyring is per-user on each node
- First access may trigger OS unlock popup
