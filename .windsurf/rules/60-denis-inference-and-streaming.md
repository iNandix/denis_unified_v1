# DENIS Inference and Streaming
# Globs: **/inference/**, **/*stream*.py, **/worker_dispatch*.py

## Timeouts
- Mandatory connect/read timeouts (e.g., 30s).
- No infinite waits; use timeouts in all network ops.

## Streaming
- SSE streams: no infinite loops; watchdog + fallback required.
- Handle disconnections gracefully.

## Logging
- Log TTFT (time to first token) and latency metrics.
