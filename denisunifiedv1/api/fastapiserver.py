"""
Legacy compatibility shim for denisunifiedv1.api.fastapiserver.
Re-exports create_app and app from the canonical api.fastapi_server module.
"""

from api.fastapi_server import create_app as createapp, app

__all__ = ["createapp", "app"]
