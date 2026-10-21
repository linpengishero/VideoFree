# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Licensed under AGPL-3.0; see LICENSE, NOTICE and COMMERCIAL_LICENSE.md.
"""Import compatibility only; remove when existing adapter consumers migrate.

The sole implementation belongs to the ComfyUI system service.
"""
from ..system_services.comfyui.provider import Provider as ComfyUIClient

__all__ = ["ComfyUIClient"]
