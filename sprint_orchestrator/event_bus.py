"""Native event bus for sprint orchestrator (store + optional Redis pubsub)."""

from __future__ import annotations

import json
import time
from typing import Any

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None

from .config import SprintOrchestratorConfig
from .models import SprintEvent
from .providers import merged_env
from .session_store import SessionStore


class EventBus:
    def __init__(self, store: SessionStore, config: SprintOrchestratorConfig) -> None:
        self.store = store
        self.config = config
        env = merged_env(config)
        self.channel = (env.get("DENIS_SPRINT_EVENT_BUS_CHANNEL") or "denis:sprint:events").strip()
        self.redis_url = (
            env.get("DENIS_SPRINT_EVENT_BUS_REDIS_URL")
            or env.get("REDIS_URL")
            or ""
        ).strip()
        self.redis_enabled = _env_bool(env.get("DENIS_SPRINT_EVENT_BUS_REDIS_ENABLED"), True)
        self.log_enabled = _env_bool(env.get("DENIS_SPRINT_EVENT_LOG_ENABLED"), True)
        configured_log = (env.get("DENIS_SPRINT_EVENT_LOG_PATH") or "").strip()
        if configured_log:
            self.log_path = configured_log
        else:
            logs_dir = self.config.state_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = str(logs_dir / "events.log.jsonl")
        self._client: Any = None

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "redis_enabled": self.redis_enabled,
            "redis_available": redis is not None,
            "redis_url_configured": bool(self.redis_url),
            "log_enabled": self.log_enabled,
            "log_path": self.log_path,
        }

    def publish(self, event: SprintEvent) -> None:
        self.store.append_event(event)
        self._write_log(event)
        if not self._use_redis():
            return
        payload = event.as_dict()
        payload["_bus_channel"] = self.channel
        try:
            self._get_client().publish(self.channel, json.dumps(payload, sort_keys=True))
        except Exception:
            # Event persistence already happened via store; fail-open on broadcast.
            return

    def iter_live(
        self,
        *,
        session_id: str,
        worker_filter: str | None = None,
        kind_filter: str | None = None,
        interval_sec: float = 1.0,
    ):
        if self._use_redis():
            yield from self._iter_live_redis(
                session_id=session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                interval_sec=interval_sec,
            )
            return
        yield from self._iter_live_store(
            session_id=session_id,
            worker_filter=worker_filter,
            kind_filter=kind_filter,
            interval_sec=interval_sec,
        )

    def _iter_live_store(
        self,
        *,
        session_id: str,
        worker_filter: str | None,
        kind_filter: str | None,
        interval_sec: float,
    ):
        cursor = len(self.store.read_events(session_id))
        while True:
            time.sleep(max(0.2, interval_sec))
            events = self.store.read_events(session_id)
            if len(events) <= cursor:
                continue
            batch = events[cursor:]
            cursor = len(events)
            for event in batch:
                if _event_matches(event, session_id, worker_filter, kind_filter):
                    yield event

    def _iter_live_redis(
        self,
        *,
        session_id: str,
        worker_filter: str | None,
        kind_filter: str | None,
        interval_sec: float,
    ):
        pubsub = self._get_client().pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(self.channel)
        try:
            while True:
                msg = pubsub.get_message(timeout=max(0.2, interval_sec))
                if not msg or msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    event = json.loads(data)
                except Exception:
                    continue
                if _event_matches(event, session_id, worker_filter, kind_filter):
                    yield event
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    def _use_redis(self) -> bool:
        return self.redis_enabled and bool(self.redis_url) and redis is not None

    def _get_client(self):
        if self._client is None:
            if not self._use_redis():
                raise RuntimeError("Redis event bus not available")
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _write_log(self, event: SprintEvent) -> None:
        if not self.log_enabled:
            return
        try:
            path_obj = self.config.state_dir / "logs"
            path_obj.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.as_dict(), sort_keys=True))
                fh.write("\n")
        except Exception:
            # Persistence already exists in SessionStore; logging must not block runtime.
            return


def _env_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _event_matches(
    event: dict[str, Any],
    session_id: str,
    worker_filter: str | None,
    kind_filter: str | None,
) -> bool:
    if str(event.get("session_id") or "") != session_id:
        return False
    if worker_filter not in (None, "", "all"):
        if str(event.get("worker_id") or "") != str(worker_filter):
            return False
    if kind_filter not in (None, "", "all"):
        if not str(event.get("kind") or "").startswith(str(kind_filter)):
            return False
    return True


def publish_event(store: SessionStore, event: SprintEvent, bus: EventBus | None = None) -> None:
    if bus is not None:
        bus.publish(event)
        return
    store.append_event(event)
