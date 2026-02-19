"""
sitecustomize.py
================

Python automatically imports `sitecustomize` on interpreter startup (if found
on `sys.path`).

We use it to make pytest runs deterministic and avoid known hangs when
observability exporters / global instrumentation are enabled during unit tests.
This is intentionally *conditional* and does not affect normal runtime.
"""

from __future__ import annotations

import os
import sys


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes"}


def _running_pytest() -> bool:
    return any("pytest" in (arg or "") for arg in sys.argv) or _truthy(
        os.getenv("PYTEST_CURRENT_TEST")
    )


if _running_pytest() and not _truthy(os.getenv("DENIS_TEST_ENABLE_OBSERVABILITY")):
    # Ensure this is set *before* pytest plugins and app modules import.
    os.environ.setdefault("DISABLE_OBSERVABILITY", "1")

