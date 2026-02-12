#!/usr/bin/env python3
"""Entry point for DENIS sprint orchestrator CLI."""
# ruff: noqa: E402

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from denis_unified_v1.sprint_orchestrator.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
