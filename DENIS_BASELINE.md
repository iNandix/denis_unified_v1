# DENIS Baseline (Phase 0)

- Timestamp (UTC): `2026-02-11T21:09:09.899750+00:00`
- Host: `Nodo1`

## Ports
- Command: `ss -tlnp`
- Requested: `[8084, 9999, 8086, 9100, 8000]`
- Open: `[8084, 8086, 9999]`

## Health Endpoints
- `http://127.0.0.1:8084/health` -> `ok` (status=200, latency_ms=25)
- `http://127.0.0.1:9999/health` -> `ok` (status=200, latency_ms=6)
- `http://127.0.0.1:8086/health` -> `ok` (status=200, latency_ms=4)
- `http://127.0.0.1:8000/health` -> `error` (status=None, latency_ms=3)
  error: `curl: (7) Failed to connect to 127.0.0.1 port 8000 after 0 ms: Couldn't connect to server`

## Feature Flags Default
- `denis_use_quantum_substrate=False`
- `denis_use_quantum_search=False`
- `denis_use_cortex=False`
- `denis_enable_metagraph=True`
- `denis_autopoiesis_mode=supervised`
