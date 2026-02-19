# Rollback: async_min + Control Room Runner

This rollback is safe: `async_min` is non-critical by design.

## Remove Files (added)
- `denis_unified_v1/async_min/`
- `control_room/`
- `scripts/async_snapshot_hass_demo.py`
- `docs/ASYNC_OPERATIONS.md`
- `docs/ROLLBACK_ASYNC_MIN.md`
- `docs/schema/telemetry_v1_1.json`
- `tests/schema/test_telemetry_v1_1.py`
- `tests/test_async_snapshot_hass.py` (revert to previous)
- `tests/test_control_room_runner.py` (revert to previous)

## Revert Modified Files
- `api/telemetry_store.py`
- `api/routes/telemetry_ops.py`
- `api/routes/health_ops.py`
- `denis_unified_v1/async_min/artifacts.py`
- `denis_unified_v1/async_min/tasks.py`
- `control_room/runner.py`

## Commands (git)
```bash
git checkout -- api/telemetry_store.py api/routes/telemetry_ops.py api/routes/health_ops.py
git checkout -- denis_unified_v1/async_min/artifacts.py denis_unified_v1/async_min/tasks.py
git checkout -- control_room/runner.py tests/test_async_snapshot_hass.py tests/test_control_room_runner.py
git clean -fd -- denis_unified_v1/async_min control_room docs/schema/telemetry_v1_1.json tests/schema/test_telemetry_v1_1.py docs/ASYNC_OPERATIONS.md docs/ROLLBACK_ASYNC_MIN.md scripts/async_snapshot_hass_demo.py
```

## Runtime Rollback (no code change)
- Set `ASYNC_ENABLED=0` and restart the service. This disables Celery dispatch; jobs will run sync fallback only when called explicitly by runner/demo.

