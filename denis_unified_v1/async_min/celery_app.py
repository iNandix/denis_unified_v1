from __future__ import annotations

import logging
from typing import Any

from denis_unified_v1.async_min.config import get_async_config

logger = logging.getLogger(__name__)

_APP: Any = None


def get_celery_app():
    """Return a configured Celery app or None if async is disabled/unavailable."""
    global _APP
    if _APP is not None:
        return _APP

    cfg = get_async_config()
    if not cfg.enabled:
        _APP = None
        return None

    try:
        from celery import Celery  # type: ignore
    except Exception:
        _APP = None
        return None

    app = Celery(
        "denis_async_min",
        broker=cfg.broker_url,
        backend=cfg.result_backend,
        include=["denis_unified_v1.async_min.tasks"],
    )
    # Safe defaults; keep tasks lightweight and avoid long blocks.
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_acks_late=False,
        worker_prefetch_multiplier=1,
        task_default_queue="denis:async_min",
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_connection_timeout=1,
    )

    _APP = app
    return app
