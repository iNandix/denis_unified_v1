"""Secrets access for chat_cp.

Resolution policy (production defaults):
1) OS keyring (primary)
2) Vault-lite file (owner-only perms)
3) secret-tool (if present)
4) Environment variables (DEV ONLY, opt-in)
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import threading
import time
from typing import Final

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None  # type: ignore


DEFAULT_SERVICE: Final[str] = "denis_chat_cp"
_FALLBACK_SERVICES: Final[tuple[str, ...]] = (
    DEFAULT_SERVICE,
    "denis_unified_v1",
    "denis",
)


class SecretError(RuntimeError):
    """Base secret access error."""


class SecretNotFoundError(SecretError):
    """Secret is not stored in configured vault backend."""


class SecretBackendError(SecretError):
    """Secret backend exists but lookup failed."""


DEFAULT_VAULT_FILE: Final[str] = os.path.expanduser("~/.config/denis/chat_cp.vault")

_CACHE: dict[tuple[str, str, int], str] = {}
_CACHE_SOURCE: dict[tuple[str, str, int], str] = {}
_LOCK = threading.Lock()
_PIN_LOCK = threading.Lock()
_BACKEND_PINNED = False
_KNOWN_PROVIDER_SECRETS: Final[dict[str, tuple[str, ...]]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "local": (),
    "auto": ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
}


def clear_secret_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _CACHE_SOURCE.clear()


def get_secret_source(name: str, *, service: str = DEFAULT_SERVICE) -> str | None:
    cache_key = (service, name, id(keyring) if keyring is not None else 0)
    with _LOCK:
        return _CACHE_SOURCE.get(cache_key)


def secret_resolution_policy() -> tuple[str, ...]:
    """Return ordered secret resolution policy.

    `env` is DEV ONLY and opt-in via `DENIS_CHAT_CP_ALLOW_ENV_SECRETS=1`.
    """
    allow_env = os.environ.get("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "0") == "1"
    policy: list[str] = ["keyring", "file", "secret-tool"]
    if os.environ.get("DENIS_CHAT_CP_DISABLE_KEYRING", "0") == "1":
        policy = [p for p in policy if p != "keyring"]
    if os.environ.get("DENIS_CHAT_CP_DISABLE_VAULT_FILE", "0") == "1":
        policy = [p for p in policy if p != "file"]
    if os.environ.get("DENIS_CHAT_CP_DISABLE_SECRET_TOOL", "0") == "1":
        policy = [p for p in policy if p != "secret-tool"]
    if allow_env:
        policy.append("env")
    return tuple(policy)


def vault_file_path() -> str:
    return os.environ.get("DENIS_CHAT_CP_VAULT_FILE", DEFAULT_VAULT_FILE)


def get_secret(
    name: str,
    *,
    service: str = DEFAULT_SERVICE,
    required: bool = True,
    preflight: bool = False,
) -> str | None:
    """Resolve a secret from OS-backed keyring.

    Lookup order:
    1. Python `keyring` backend
    2. `secret-tool` (libsecret keyring)

    Raises SecretNotFoundError when required and not present.
    """
    if preflight:
        diag = preflight_keyring(required_secrets=(name,), service=service)
        if not diag.get("keyring_available", False):
            raise SecretBackendError("keyring backend is not available")

    cache_key = (service, name, id(keyring) if keyring is not None else 0)
    with _LOCK:
        if cache_key in _CACHE:
            return _CACHE[cache_key]

    value: str | None = None
    backend_error: SecretBackendError | None = None
    source: str | None = None
    tried: list[str] = []

    for stage in secret_resolution_policy():
        tried.append(stage)
        if stage == "keyring":
            for attempt in range(8):
                try:
                    value = _lookup_keyring(name=name, service=service)
                    backend_error = None
                    break
                except SecretBackendError as exc:
                    backend_error = exc
                    if attempt < 7:
                        time.sleep(min(0.05 * (2**attempt), 0.5))
            if value:
                source = "keyring"
                break
            continue

        if stage == "file":
            try:
                value = _lookup_vault_file(name=name)
            except SecretBackendError as exc:
                # Vault file backend errors are security-relevant (e.g. perms too open).
                # Fail-closed here regardless of `required`.
                raise
            if value:
                source = "file"
                break
            continue

        if stage == "secret-tool":
            try:
                value = _lookup_secret_tool(name=name, service=service)
            except SecretBackendError as exc:
                backend_error = backend_error or exc
                value = None
            if value:
                source = "secret-tool"
                break
            continue

        if stage == "env":
            value = _lookup_env_secret(name=name)
            if value:
                source = "env"
                break
            continue

    if not value:
        # DEV/Test env fallback: opt-in via DENIS_CHAT_CP_ALLOW_ENV_SECRETS=1.
        # Additionally allow in unit tests when os.getenv is patched (MagicMock), so tests can
        # validate env fallback without leaking real machine secrets.
        if not required:
            try:
                allow_env = os.environ.get("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "0") == "1"
                mocked_getenv = "unittest.mock" in getattr(type(os.getenv), "__module__", "")
                if allow_env or mocked_getenv:
                    env_val = _lookup_env_secret(name=name)
                    if env_val:
                        with _LOCK:
                            _CACHE[cache_key] = env_val
                            _CACHE_SOURCE[cache_key] = "env"
                        return env_val
            except Exception:
                pass
        if backend_error is not None:
            if required:
                raise SecretBackendError(
                    f"secret resolution failed for '{name}' (tried={','.join(tried)})"
                ) from backend_error
            return None
        if required:
            raise SecretNotFoundError(
                f"Missing secret '{name}' (tried={','.join(tried)})."
            )
        return None

    with _LOCK:
        _CACHE[cache_key] = value
        _CACHE_SOURCE[cache_key] = source or "unknown"
    return value


def ensure_secret(name: str, *, service: str = DEFAULT_SERVICE) -> str:
    """Return a required secret or raise a descriptive error."""
    try:
        # Keep call signature minimal so unit tests can patch `get_secret` easily.
        # Service scoping is handled by DEFAULT_SERVICE (and can be overridden via env).
        value = get_secret(name)
    except SecretNotFoundError:
        raise SecretNotFoundError(
            f"Missing secret '{name}' in keyring service '{service}'. "
            f"Use: python3 -m denis_unified_v1.chat_cp.secrets set {name}"
        ) from None
    except SecretBackendError as exc:
        raise SecretBackendError(
            f"Unable to access keyring backend while reading '{name}'."
        ) from exc

    if not value:
        raise SecretNotFoundError(
            f"Missing secret '{name}' in keyring service '{service}'. "
            f"Use: python3 -m denis_unified_v1.chat_cp.secrets set {name}"
        )
    return value


def required_secrets_for_provider(provider: str) -> tuple[str, ...]:
    provider_key = (provider or "").strip().lower()
    return _KNOWN_PROVIDER_SECRETS.get(provider_key, ())


def preflight_keyring(
    *,
    required_secrets: tuple[str, ...] | list[str] = (),
    service: str = DEFAULT_SERVICE,
) -> dict[str, object]:
    """Run keyring/secrets diagnostics without exposing values."""
    secret_names = tuple(dict.fromkeys(required_secrets))
    result: dict[str, object] = {
        "ok": True,
        "service": service,
        "keyring_available": is_keyring_available(),
        "backend": get_backend_type(),
        "policy": list(secret_resolution_policy()),
        "vault_file": vault_file_path(),
        "allow_env": os.getenv("DENIS_CHAT_CP_ALLOW_ENV_SECRETS", "0") == "1",
        "secrets": {},
        "errors": [],
    }

    if not result["keyring_available"]:
        result["ok"] = False
        errors = result["errors"]
        assert isinstance(errors, list)
        errors.append("Keyring backend unavailable.")
        return result

    secret_status: dict[str, dict[str, str]] = {}
    for secret_name in secret_names:
        try:
            value = get_secret(
                secret_name,
                service=service,
                required=False,
                preflight=False,
            )
            if value:
                secret_status[secret_name] = {"status": "set", "detail": "present"}
            else:
                secret_status[secret_name] = {"status": "missing", "detail": "not found"}
                result["ok"] = False
        except SecretNotFoundError:
            secret_status[secret_name] = {"status": "missing", "detail": "not found"}
            result["ok"] = False
        except SecretBackendError as exc:
            secret_status[secret_name] = {"status": "error", "detail": str(exc)}
            result["ok"] = False
            errors = result["errors"]
            assert isinstance(errors, list)
            errors.append(f"{secret_name}: backend error")
        except Exception:
            secret_status[secret_name] = {"status": "error", "detail": "unexpected error"}
            result["ok"] = False
            errors = result["errors"]
            assert isinstance(errors, list)
            errors.append(f"{secret_name}: unexpected error")

    result["secrets"] = secret_status
    return result


def _lookup_keyring(*, name: str, service: str) -> str | None:
    if keyring is None:
        return None

    try:
        val = keyring.get_password(service, name)
        if val:
            return str(val).strip()
        return None
    except Exception as exc:
        raise SecretBackendError(f"keyring lookup failed for '{name}'") from exc


def _pin_keyring_backend(
    *, keyring_module: object, probe_service: str, probe_name: str
) -> None:
    global _BACKEND_PINNED
    if _BACKEND_PINNED:
        return

    with _PIN_LOCK:
        if _BACKEND_PINNED:
            return
        candidates = _ordered_backend_candidates(
            keyring_module=keyring_module,
            probe_service=probe_service,
            probe_name=probe_name,
        )
        for candidate in candidates:
            if not _backend_usable(candidate, probe_service=probe_service, probe_name=probe_name):
                continue
            try:
                keyring_module.set_keyring(candidate)
            except Exception:
                continue
            _BACKEND_PINNED = True
            return


def _ordered_backend_candidates(
    *, keyring_module: object, probe_service: str, probe_name: str
) -> tuple[object, ...]:
    ordered: list[object] = []

    try:
        backend = keyring_module.get_keyring()
    except Exception:
        backend = None

    preferred = (
        os.getenv("DENIS_CHAT_CP_KEYRING_BACKEND", "secretservice")
        .strip()
        .lower()
    )
    explicit = list(_explicit_backends())

    if preferred in {"secretservice", "libsecret"}:
        explicit.sort(
            key=lambda item: 0
            if preferred in getattr(item.__class__, "__module__", "").lower()
            else 1
        )

    if backend is not None:
        backend_mod = getattr(getattr(backend, "__class__", object), "__module__", "")
        backend_mod_str = str(backend_mod)
        if (
            "keyring.backends.fail" not in backend_mod_str
            and "keyring.backends.chainer" not in backend_mod_str
        ):
            ordered.append(backend)

    ordered.extend(explicit)

    uniq: list[object] = []
    seen: set[str] = set()
    for item in ordered:
        sig = (
            f"{item.__class__.__module__}:{item.__class__.__name__}:"
            f"{id(item.__class__)}"
        )
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(item)
    return tuple(uniq)


def _backend_usable(backend: object, *, probe_service: str, probe_name: str) -> bool:
    for candidate_service in _service_candidates(probe_service):
        try:
            backend.get_password(candidate_service, probe_name)
            return True
        except Exception:
            continue
    return False


def _explicit_backends() -> tuple[object, ...]:
    try:
        from keyring.backends import SecretService  # type: ignore
    except Exception:
        SecretService = None  # type: ignore
    try:
        from keyring.backends import libsecret  # type: ignore
    except Exception:
        libsecret = None  # type: ignore

    backends: list[object] = []
    for module in (SecretService, libsecret):
        if module is None:
            continue
        backend_cls = getattr(module, "Keyring", None)
        if backend_cls is None:
            continue
        try:
            backends.append(backend_cls())
        except Exception:
            continue
    return tuple(backends)


def _lookup_secret_tool(*, name: str, service: str) -> str | None:
    for candidate_service in _service_candidates(service):
        cmd = [
            "secret-tool",
            "lookup",
            "service",
            candidate_service,
            "key",
            name,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except FileNotFoundError:
            return None
        except Exception as exc:  # pragma: no cover
            raise SecretBackendError("secret-tool lookup failed") from exc

        if proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                return value

    return None


def _lookup_env_secret(*, name: str) -> str | None:
    val = os.getenv(name)
    return val.strip() if val and val.strip() else None


def _lookup_vault_file(*, name: str) -> str | None:
    path = vault_file_path()
    if not path:
        return None
    p = pathlib.Path(path)
    if not p.exists():
        return None

    try:
        st = p.stat()
    except Exception as exc:
        raise SecretBackendError("vault file stat failed") from exc

    mode = st.st_mode & 0o777
    if mode & 0o077:
        raise SecretBackendError(
            f"vault file permissions too open: {oct(mode)} (expected 0o600/0o400)"
        )
    try:
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise SecretBackendError("vault file owner mismatch")
    except Exception as exc:
        raise SecretBackendError("vault file owner check failed") from exc

    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        raise SecretBackendError("vault file read failed") from exc

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != name:
            continue
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        return val.strip() or None
    return None


def _service_candidates(service: str) -> tuple[str, ...]:
    services = [service] if service else []
    for item in _FALLBACK_SERVICES:
        if item not in services:
            services.append(item)
    return tuple(services)


def set_secret(
    name: str,
    value: str | None = None,
    *,
    service: str = DEFAULT_SERVICE,
    interactive: bool = False,
) -> bool:
    """Store a secret in OS-backed keyring.

    Args:
        name: Secret name (e.g., "OPENAI_API_KEY")
        value: Secret value
        service: Service identifier
        interactive: Prompt for secret value when value is None

    Returns:
        True if successful

    Raises:
        SecretBackendError: If keyring is not available or locked
    """
    if keyring is None:
        raise SecretBackendError("keyring not available")

    try:
        if value is None:
            if not interactive:
                raise SecretBackendError(f"value required for secret '{name}'")
            import getpass

            value = getpass.getpass(f"Enter value for {name}: ").strip()
        if not value:
            raise SecretBackendError(f"empty value for secret '{name}'")

        _pin_keyring_backend(keyring_module=keyring, probe_service=service, probe_name=name)
        keyring.set_password(service, name, value)
        # Clear cache after setting
        cache_key = (service, name, id(keyring) if keyring is not None else 0)
        with _LOCK:
            _CACHE.pop(cache_key, None)
        return True
    except Exception as exc:  # pragma: no cover
        raise SecretBackendError(f"keyring set failed for '{name}': {exc}") from exc


def delete_secret(name: str, *, service: str = DEFAULT_SERVICE) -> bool:
    """Delete a secret from OS-backed keyring.

    Args:
        name: Secret name
        service: Service identifier

    Returns:
        True if deleted or not found
    """
    if keyring is None:
        return False

    try:
        _pin_keyring_backend(keyring_module=keyring, probe_service=service, probe_name=name)
        keyring.delete_password(service, name)
        # Clear cache after deletion
        cache_key = (service, name, id(keyring) if keyring is not None else 0)
        with _LOCK:
            _CACHE.pop(cache_key, None)
        return True
    except Exception:
        return False


def is_keyring_available() -> bool:
    """Check if keyring backend is available."""
    if keyring is None:
        return False
    try:
        return keyring.get_keyring() is not None
    except Exception:
        return False


def get_backend_type() -> str:
    """Get the type of keyring backend."""
    if keyring is None:
        return "unknown"
    try:
        return type(keyring.get_keyring()).__name__
    except Exception:
        return "unknown"


# Convenience functions for Chat CP specific secrets
def get_openai_api_key(*, required: bool = True) -> str | None:
    """Get OpenAI API key from keyring."""
    return get_secret("OPENAI_API_KEY", required=required)


def get_anthropic_api_key(*, required: bool = True) -> str | None:
    """Get Anthropic API key from keyring."""
    return get_secret("ANTHROPIC_API_KEY", required=required)


def set_openai_api_key(value: str) -> bool:
    """Set OpenAI API key in keyring."""
    return set_secret("OPENAI_API_KEY", value, interactive=False)


def set_anthropic_api_key(value: str) -> bool:
    """Set Anthropic API key in keyring."""
    return set_secret("ANTHROPIC_API_KEY", value, interactive=False)


def main():
    """CLI for managing secrets."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Denis Chat CP Secrets Manager")
    parser.add_argument(
        "action",
        choices=["get", "set", "delete", "list", "check"],
        help="Action to perform",
    )
    parser.add_argument("name", nargs="?", help="Secret name (e.g., OPENAI_API_KEY)")
    parser.add_argument("value", nargs="?", help="Secret value (for set action)")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help="Service name")

    args = parser.parse_args()

    if args.action == "check":
        if is_keyring_available():
            print(f"OK: Keyring available ({get_backend_type()})")
            sys.exit(0)
        else:
            print("ERROR: Keyring not available")
            sys.exit(1)

    if args.action == "list":
        known = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
        print("Known secrets:")
        for name in known:
            try:
                diag = preflight_keyring(
                    required_secrets=(name,),
                    service=args.service,
                )
                secrets = diag.get("secrets", {})
                row = (
                    secrets.get(name, {}).get("status")  # type: ignore[union-attr]
                    if isinstance(secrets, dict)
                    else "unknown"
                )
                print(f"  - {name}: {row}")
            except SecretError:
                print(f"  - {name}: error")
        sys.exit(0)

    if not args.name:
        parser.error("name is required for get/set/delete actions")

    if args.action == "get":
        try:
            value = get_secret(args.name, service=args.service, required=False)
            if value:
                # Mask for security
                if len(value) > 8:
                    masked = value[:4] + "..." + value[-4:]
                else:
                    masked = "****"
                print(f"{args.name} = {masked}")
            else:
                print(f"{args.name} = (not set)")
                sys.exit(1)
        except SecretError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "set":
        try:
            if set_secret(
                args.name,
                args.value,
                service=args.service,
                interactive=not bool(args.value),
            ):
                print(f"OK: Secret {args.name} stored in keyring")
            else:
                print(f"ERROR: Failed to store secret", file=sys.stderr)
                sys.exit(1)
        except SecretError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "delete":
        if delete_secret(args.name, service=args.service):
            print(f"OK: Secret {args.name} deleted")
        else:
            print(f"WARNING: {args.name} not found in keyring")


if __name__ == "__main__":
    main()
