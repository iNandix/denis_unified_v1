"""Minimal async plane (Celery + Redis) for non-critical jobs.

Design:
- Controlled by ASYNC_ENABLED=1.
- Always fail-open: if Redis/Celery is unavailable, jobs run sync or are marked stale.
"""

