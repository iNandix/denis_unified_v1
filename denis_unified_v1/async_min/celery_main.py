from __future__ import annotations

from denis_unified_v1.async_min.celery_app import get_celery_app

# Celery CLI entrypoint: `celery -A denis_unified_v1.async_min.celery_main:app worker ...`
app = get_celery_app()

