"""ASGI application entry point."""

from .core.logging import configure_logging

configure_logging()

from .interfaces.http.api_v1 import app

__all__ = ["app"]
