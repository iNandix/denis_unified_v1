#!/usr/bin/env python3
"""Diagnostics for Chat CP keyring and required secrets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from denis_unified_v1.chat_cp.secrets import (
    preflight_keyring,
    required_secrets_for_provider,
    vault_file_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chat CP secrets doctor")
    parser.add_argument(
        "--provider",
        default="auto",
        choices=["auto", "openai", "anthropic", "local"],
    )
    parser.add_argument("--service", default="denis_chat_cp")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    required = required_secrets_for_provider(args.provider)
    diag = preflight_keyring(required_secrets=required, service=args.service)
    env_diag: dict[str, Any] = {
        "dbus_session_bus": bool(os.getenv("DBUS_SESSION_BUS_ADDRESS")),
        "xdg_runtime_dir": bool(os.getenv("XDG_RUNTIME_DIR")),
        "vault_file": vault_file_path(),
        "allow_env": os.getenv("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "0") == "1",
    }
    diag["env"] = env_diag

    if args.json:
        print(json.dumps(diag, ensure_ascii=True))
    else:
        print(
            f"keyring available={diag.get('keyring_available')} backend={diag.get('backend')}"
        )
        print(f"dbus_session_bus={env_diag.get('dbus_session_bus')} xdg_runtime_dir={env_diag.get('xdg_runtime_dir')}")
        print(f"vault_file={env_diag.get('vault_file')} allow_env={env_diag.get('allow_env')}")
        secrets = diag.get("secrets", {})
        if isinstance(secrets, dict):
            for name, row in secrets.items():
                status = row.get("status") if isinstance(row, dict) else "unknown"
                print(f"{name}: {status}")
        if not diag.get("ok", False):
            print("diagnostic: configure missing secrets using:")
            print("  python3 -m denis_unified_v1.chat_cp.secrets set OPENAI_API_KEY")
            print("  python3 -m denis_unified_v1.chat_cp.secrets set ANTHROPIC_API_KEY")
            print("diagnostic: if keyring fails under systemd/headless, consider vault-lite file:")
            print("  export DENIS_CHAT_CP_VAULT_FILE=~/.config/denis/chat_cp.vault")
            print("  chmod 600 ~/.config/denis/chat_cp.vault")
            print("  printf 'OPENAI_API_KEY=...\\nANTHROPIC_API_KEY=...\\n' > ~/.config/denis/chat_cp.vault")
            print("  (do not commit this file)")

    return 0 if bool(diag.get("ok", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
