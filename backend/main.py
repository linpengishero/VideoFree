# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""ASGI application entry point."""

from .core.logging import configure_logging

configure_logging()

from .interfaces.http.api_v1 import app

__all__ = ["app"]
