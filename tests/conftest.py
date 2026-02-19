"""Pytest configuration for DENIS tests."""

import os
import sys
from pathlib import Path
import importlib

project_root = Path(__file__).resolve().parent.parent
root_str = str(project_root)

# Keep unit/contract tests deterministic: do not start tracing exporters or
# global instrumentation unless explicitly requested.
if (os.getenv("DENIS_TEST_ENABLE_OBSERVABILITY") or "").strip().lower() not in {
    "1",
    "true",
    "yes",
}:
    os.environ.setdefault("DISABLE_OBSERVABILITY", "1")

# Keep repo root first to avoid shadowing by an installed package.
if not sys.path or sys.path[0] != root_str:
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
importlib.invalidate_caches()


def pytest_configure(config):  # type: ignore[no-untyped-def]
    # If an installed `denis_unified_v1` was imported by a plugin before tests start,
    # it can shadow the in-repo package (missing newer modules). Purge it once.
    mod = sys.modules.get("denis_unified_v1")
    if mod is not None:
        mod_file = getattr(mod, "__file__", "") or ""
        if root_str not in mod_file:
            for name in list(sys.modules.keys()):
                if name == "denis_unified_v1" or name.startswith("denis_unified_v1."):
                    del sys.modules[name]
            importlib.invalidate_caches()

    # Best-effort: pin the in-repo package in sys.modules early so later plugin imports
    # don't accidentally resolve an older installed distribution.
    try:
        import denis_unified_v1.async_min  # noqa: F401
    except Exception:
        # Fail-open: tests will surface a real import error if this matters.
        return
