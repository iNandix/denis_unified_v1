from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from denis_unified_v1.chat_cp.secrets import get_secret
from denis_unified_v1.chat_cp.secrets import clear_secret_cache


def test_vault_file_fallback_reads_secret(tmp_path: Path, monkeypatch):
    clear_secret_cache()
    vault = tmp_path / "chat_cp.vault"
    vault.write_text("OPENAI_API_KEY=abc123\n", encoding="utf-8")
    os.chmod(vault, 0o600)
    monkeypatch.setenv("DENIS_CHAT_CP_VAULT_FILE", str(vault))
    monkeypatch.setenv("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "0")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_KEYRING", "1")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_SECRET_TOOL", "1")

    # Force keyring stage to be non-blocking by skipping it via env backend selection.
    # We can't control the system keyring, so rely on the policy continuing to file.
    value = get_secret("OPENAI_API_KEY", required=False)
    assert value == "abc123"


def test_vault_file_permissions_too_open(tmp_path: Path, monkeypatch):
    clear_secret_cache()
    vault = tmp_path / "chat_cp.vault"
    vault.write_text("OPENAI_API_KEY=abc123\n", encoding="utf-8")
    os.chmod(vault, 0o644)
    monkeypatch.setenv("DENIS_CHAT_CP_VAULT_FILE", str(vault))
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_KEYRING", "1")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_SECRET_TOOL", "1")

    with pytest.raises(Exception):
        _ = get_secret("OPENAI_API_KEY", required=False)


def test_env_fallback_opt_in(monkeypatch):
    clear_secret_cache()
    monkeypatch.setenv("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "1")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_KEYRING", "1")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_VAULT_FILE", "1")
    monkeypatch.setenv("DENIS_CHAT_CP_DISABLE_SECRET_TOOL", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    v = get_secret("OPENAI_API_KEY", required=False)
    assert v == "env-key"
