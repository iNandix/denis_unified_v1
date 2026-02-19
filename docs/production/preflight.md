# Production Preflight

## Overview

The preflight script validates that critical and observability endpoints are accessible before deployment. It's designed to provide fast feedback about system health.

## Usage

```bash
# Basic check (chat is CRITICAL, health/telemetry are OBS)
./scripts/production_preflight.sh

# Strict mode (health and telemetry become CRITICAL)
./scripts/production_preflight.sh --strict

# JSON output for automation
./scripts/production_preflight.sh --json

# Custom base URL
./scripts/production_preflight.sh http://denis.internal:8084

# Combined options
./scripts/production_preflight.sh --strict --json http://denis.internal:8084
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Critical check failed |
| 2 | Internal error |

## Endpoint Classification

| Endpoint | Default | --strict |
|----------|---------|----------|
| `/chat` | **CRITICAL** | CRITICAL |
| `/health` | OBS | CRITICAL |
| `/telemetry` | OBS | CRITICAL |
| `/metrics` | OBS | OBS |

## Examples

### Success (server running)

```bash
$ ./scripts/production_preflight.sh
==============================================
  PRODUCTION PREFLIGHT CHECK
==============================================

Base URL: http://localhost:8084
Strict Mode: false

Checking endpoints...
Results:
  /chat                 ✓ PASS (45ms) [CRITICAL]
  /health               ✓ PASS (12ms)
  /telemetry            ✓ PASS (28ms)
  /metrics              ✓ PASS (15ms)

==============================================
  ✓ ALL CHECKS PASSED
==============================================
```

### Failure (server not running)

```bash
$ ./scripts/production_preflight.sh
==============================================
  PRODUCTION PREFLIGHT CHECK
==============================================

Base URL: http://localhost:8084
Strict Mode: false

Checking endpoints...
Results:
  /chat                 ✗ UNREACHABLE [CRITICAL]
  /health               ⚠ UNREACHABLE
  /telemetry            ⚠ UNREACHABLE
  /metrics              ⚠ UNREACHABLE

==============================================
  ✗ CRITICAL CHECKS FAILED
==============================================

System is NOT ready for production.

To debug:
  1. Check if server is running: ps aux | grep uvicorn
  2. Check logs: kubectl logs -l app=denis -n denis
  3. Try curl manually: curl -v http://localhost:8084/chat
```

### JSON Output

```bash
$ ./scripts/production_preflight.sh --json
{
  "timestamp": "2026-02-17T12:00:00+00:00",
  "base_url": "http://localhost:8084",
  "strict_mode": false,
  "results": {
    "chat": {"status": "PASS", "latency_ms": 45},
    "health": {"status": "PASS", "latency_ms": 12},
    "telemetry": {"status": "PASS", "latency_ms": 28},
    "metrics": {"status": "PASS", "latency_ms": 15}
  },
  "exit_code": 0
}
```

## Integration with CI/CD

```yaml
# .github/workflows/preflight.yaml
name: Preflight Check

jobs:
  preflight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Preflight
        run: |
          ./scripts/production_preflight.sh --strict --json > preflight.json
          
      - name: Check Result
        run: |
          exit_code=$(jq -r '.exit_code' preflight.json)
          if [ $exit_code -ne 0 ]; then
            echo "Preflight failed:"
            cat preflight.json
            exit 1
          fi
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DENIS_BASE_URL` | `http://localhost:8084` | Base URL for checks |
| `STRICT_MODE` | `false` | Enable strict mode |
| `JSON_OUTPUT` | `false` | Output JSON format |

## Troubleshooting

### Connection Refused

```bash
# Check if service is running
ps aux | grep -E "uvicorn|fastapi"

# Check port is listening
ss -tlnp | grep 8084

# Try manual curl
curl -v http://localhost:8084/health
```

### Timeout

```bash
# Increase timeout manually
curl --max-time 30 http://localhost:8084/chat
```
