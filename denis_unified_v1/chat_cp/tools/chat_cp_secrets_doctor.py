"""Package entrypoint wrapper for chat_cp secrets doctor CLI."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    root_dir = Path(__file__).resolve().parents[3]
    script = root_dir / "tools" / "chat_cp_secrets_doctor.py"
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
