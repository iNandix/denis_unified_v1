# Test Harness Notes

## Pytest Import Hygiene
Goal: tests must import the in-repo code, not an older installed wheel that might exist on the machine.

We standardize this via `pytest.ini`:
- `--import-mode=importlib` reduces `sys.path` side effects during collection/import.
- `pythonpath = .` keeps repo root first when the `pytest-pythonpath` plugin is present.

`tests/conftest.py` keeps a minimal guard:
- Ensure repo root is first in `sys.path`.
- If `denis_unified_v1` was already imported from outside the repo (by a plugin), purge it once at `pytest_configure`.

## Running
From repo root:
```bash
python -m pytest -q
```

