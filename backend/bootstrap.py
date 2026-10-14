from pathlib import Path

from .core.context import ApplicationContext
from .integrations.comfyui import ComfyUIClient


ROOT = Path(__file__).resolve().parents[1]
context = ApplicationContext.create(ROOT)
comfyui_client = ComfyUIClient(context.comfyui_url)

__all__ = ["ROOT", "context", "comfyui_client"]
