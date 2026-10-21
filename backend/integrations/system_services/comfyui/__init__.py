# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Licensed under AGPL-3.0; see LICENSE, NOTICE and COMMERCIAL_LICENSE.md.
"""Typed, single-node ComfyUI system extension (no node scheduler)."""
import importlib.util
import json
from pathlib import Path
from typing import Any, BinaryIO, ContextManager, Iterable, Protocol


class ComfyUIProvider(Protocol):
    base_url: str
    node_id: str

    def configure(self, base_url: str) -> None: ...
    def request(self, path: str, method: str = "GET", body: bytes | None = None) -> Any: ...
    def is_available(self) -> bool: ...
    def node_definitions(self, kinds: Iterable[str], aliases: dict[str, str]) -> dict: ...
    def upload_input(self, body: bytes, media_type: str, filename: str) -> str: ...
    def open_output(self, value: dict) -> ContextManager[BinaryIO]: ...
    def download_output(self, value: dict) -> bytes: ...
    def upload_file(self, source: Path, relative: str, destination: str = "output") -> dict: ...
    def free_memory(self) -> None: ...


def load_provider(base_url: str, directory: Path | None = None) -> ComfyUIProvider:
    root = (directory or Path(__file__).parent).resolve()
    manifest = json.loads((root / "provider.json").read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 1 or manifest.get("contract_version") != 1
            or manifest.get("service_id") != "comfyui" or manifest.get("provider_id") != "default"):
        raise ValueError("Unsupported ComfyUI service manifest")
    filename, symbol = manifest["entry"].split(":", 1)
    entry = (root / filename).resolve()
    if not entry.is_relative_to(root) or entry.suffix != ".py" or not entry.is_file():
        raise ValueError("ComfyUI provider entry must stay inside its directory")
    # Normal imports retain one class identity for existing adapter consumers.
    if root == Path(__file__).parent.resolve() and filename == "provider.py" and symbol == "Provider":
        from .provider import Provider
        provider = Provider(base_url)
    else:
        spec = importlib.util.spec_from_file_location("videofree_comfyui_provider", entry)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        provider = getattr(module, symbol)(base_url)
    for name in ("configure", "request", "is_available", "node_definitions", "upload_input",
                 "open_output", "download_output", "upload_file", "free_memory"):
        if not callable(getattr(provider, name, None)):
            raise ValueError(f"ComfyUI provider missing operation: {name}")
    if not getattr(provider, "node_id", ""):
        raise ValueError("ComfyUI provider requires node_id")
    return provider
