"""Resolve Neo4j config from existing Denis sources (no manual daily setup)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Any

from neo4j import GraphDatabase


ROOT = Path("/media/jotah/SSD_denis")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

_CANONICAL_ENV_FILE = PROJECT_ROOT / ".env"
_LOCAL_ENV_FILE = PROJECT_ROOT / ".env.local"
_ROOT_LOCAL_ENV_FILE = ROOT / ".env.local"
_LEGACY_ENV_FILES = [
    # Prefer local secrets first (project, then root).
    _LOCAL_ENV_FILE,
    _ROOT_LOCAL_ENV_FILE,
    ROOT / ".env.prod.local",
    ROOT / ".env.platform",
    ROOT / ".env.ultimate",
    ROOT / ".env.jordi",
    ROOT / ".env",
    ROOT / ".env.denis",
]
_ENV_FILES = [*_LEGACY_ENV_FILES, _CANONICAL_ENV_FILE]


@dataclass(frozen=True)
class Neo4jResolvedConfig:
    uri: str
    user: str
    password: str


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip("'").strip('"')
    return data


def _extract_neo4j(env: dict[str, str]) -> Neo4jResolvedConfig | None:
    uri = (
        env.get("NEO4J_URI")
        or env.get("NEO4J_URL")
        or env.get("DENIS_NEO4J_URI")
        or ""
    ).strip()
    user = (
        env.get("NEO4J_USER")
        or env.get("NEO4J_USERNAME")
        or env.get("DENIS_NEO4J_USER")
        or "neo4j"
    ).strip()
    password = (
        env.get("NEO4J_PASSWORD")
        or env.get("NEO4J_PASS")
        or env.get("DENIS_NEO4J_PASSWORD")
        or ""
    ).strip()
    if not uri or not password:
        return None
    return Neo4jResolvedConfig(uri=uri, user=user, password=password)


def _password_fp(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return digest[-8:]


def _expand_candidate_uris(cfg: Neo4jResolvedConfig) -> list[Neo4jResolvedConfig]:
    """Expand localhost URIs to configured remote candidate(s)."""
    out = [cfg]

    try:
        parsed = urlparse(cfg.uri)
        is_local = (parsed.hostname or "").strip() in {"localhost", "127.0.0.1"}
        if is_local:
            remote_uri = (
                os.getenv("DENIS_NEO4J_REMOTE_URI")
                or os.getenv("DENIS_NEO4J_URI")
                or "bolt://10.10.10.1:7687"
            ).strip()
            if remote_uri and remote_uri != cfg.uri:
                out.append(
                    Neo4jResolvedConfig(
                        uri=remote_uri,
                        user=cfg.user,
                        password=cfg.password,
                    )
                )

            remote_host = (os.getenv("DENIS_NEO4J_REMOTE_HOST") or "10.10.10.1").strip()
            if remote_host:
                # Keep original scheme/port and only replace host.
                rebuilt = parsed._replace(netloc=f"{remote_host}:{parsed.port or 7687}")
                rewritten_uri = urlunparse(rebuilt)
                if rewritten_uri and all(c.uri != rewritten_uri for c in out):
                    out.append(
                        Neo4jResolvedConfig(
                            uri=rewritten_uri,
                            user=cfg.user,
                            password=cfg.password,
                        )
                    )
    except Exception:
        pass

    return out


def _verify_connectivity(cfg: Neo4jResolvedConfig, timeout_sec: float = 4.0) -> tuple[bool, str | None]:
    driver = None
    try:
        driver = GraphDatabase.driver(
            cfg.uri,
            auth=(cfg.user, cfg.password),
            connection_timeout=timeout_sec,
        )
        driver.verify_connectivity()
        return True, None
    except Exception as exc:
        return False, str(exc)[:200]
    finally:
        try:
            if driver is not None:
                driver.close()
        except Exception:
            pass


def _is_auth_rate_limited(error: str | None) -> bool:
    if not error:
        return False
    return (
        "AuthenticationRateLimit" in error
        or "incorrect authentication details too many times" in error.lower()
    )


def _is_auth_unauthorized(error: str | None) -> bool:
    if not error:
        return False
    return "Unauthorized" in error or "authentication failure" in error.lower()


def ensure_neo4j_env_auto() -> dict[str, Any]:
    candidates: list[tuple[str, Neo4jResolvedConfig]] = []

    # Canonical project .env first, then legacy env files, then runtime fallback.
    for path in _ENV_FILES:
        env = _load_env_file(path)
        cfg = _extract_neo4j(env)
        if cfg:
            candidates.append((f"env_file:{path}", cfg))

    runtime_cfg = _extract_neo4j(dict(os.environ))
    if runtime_cfg:
        candidates.append(("runtime_env", runtime_cfg))

    dedup: list[tuple[str, Neo4jResolvedConfig]] = []
    seen: set[tuple[str, str, str]] = set()
    for source, cfg in candidates:
        for expanded_cfg in _expand_candidate_uris(cfg):
            key = (expanded_cfg.uri, expanded_cfg.user, _password_fp(expanded_cfg.password))
            if key in seen:
                continue
            seen.add(key)
            dedup.append((source, expanded_cfg))

    # Export canonical-first candidate so downstream code does not fail on empty password
    # even if connectivity validation fails.
    if dedup:
        _, first_cfg = dedup[0]
        os.environ["NEO4J_URI"] = first_cfg.uri
        os.environ["NEO4J_USER"] = first_cfg.user
        os.environ["NEO4J_USERNAME"] = first_cfg.user
        os.environ["NEO4J_PASSWORD"] = first_cfg.password
        os.environ["NEO4J_PASS"] = first_cfg.password

    attempts: list[dict[str, Any]] = []
    blocked_password_fps: set[str] = set()
    for source, cfg in dedup:
        pwd_fp = _password_fp(cfg.password)
        if pwd_fp in blocked_password_fps:
            attempts.append(
                {
                    "source": source,
                    "uri": cfg.uri,
                    "user": cfg.user,
                    "password_fp": pwd_fp,
                    "ok": False,
                    "error": "skipped_after_unauthorized_same_credential",
                }
            )
            continue

        ok, error = _verify_connectivity(cfg)
        attempts.append(
            {
                "source": source,
                "uri": cfg.uri,
                "user": cfg.user,
                "password_fp": pwd_fp,
                "ok": ok,
                "error": error,
            }
        )
        if ok:
            os.environ["NEO4J_URI"] = cfg.uri
            os.environ["NEO4J_USER"] = cfg.user
            os.environ["NEO4J_USERNAME"] = cfg.user
            os.environ["NEO4J_PASSWORD"] = cfg.password
            os.environ["NEO4J_PASS"] = cfg.password
            return {
                "status": "ok",
                "selected_source": source,
                "selected_uri": cfg.uri,
                "selected_user": cfg.user,
                "password_fp": _password_fp(cfg.password),
                "attempts": attempts,
            }

        if _is_auth_unauthorized(error):
            blocked_password_fps.add(pwd_fp)

        if _is_auth_rate_limited(error):
            return {
                "status": "error",
                "error": "neo4j_auth_rate_limited",
                "attempts": attempts,
            }

    return {
        "status": "error",
        "error": "no_valid_neo4j_config_found",
        "attempts": attempts,
    }
