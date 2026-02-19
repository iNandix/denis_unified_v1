"""Environment bootstrap for chat_cp."""

from __future__ import annotations

import os
from pathlib import Path
import threading

_LOADED = False
_LOCK = threading.Lock()


def ensure_env_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        try:
            from dotenv import load_dotenv

            # repo_root/.env
            root = Path(__file__).resolve().parents[2]
            env_file = root / ".env"
            if env_file.exists():
                load_dotenv(dotenv_path=str(env_file), override=False)
        except Exception:
            pass
        _LOADED = True
