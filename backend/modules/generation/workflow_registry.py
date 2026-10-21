# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from ...integrations.comfyui.workflow_loader import convert_workflow, workflow_from_png
from .plugins import PluginCatalog


class WorkflowRegistry:
    def __init__(
        self,
        workflows_path: Path,
        node_definitions: Callable[[Iterable[str]], dict[str, Any]],
        context=None,
    ) -> None:
        self.workflows_path = workflows_path
        self.node_definitions = node_definitions
        self.context = context

    def all(self) -> dict[str, dict[str, Any]]:
        return PluginCatalog(self.workflows_path, self.context).capabilities()

    def capability(self, capability_id: str, variant: str = "") -> dict[str, Any]:
        config = self.all().get(capability_id)
        if config is None:
            raise ValueError(f"Unsupported capability: {capability_id}")
        if config.get("operation") == "postprocess":
            variant = ""
        if variant and (variant != "normal" or variant in config.get("variants", {})):
            selected = config.get("variants", {}).get(variant)
            if selected is None:
                raise ValueError(f"Unsupported variant: {variant}")
            config = {**config, **selected, "variant": variant}
        if config.get("executor", "comfyui") == "comfyui":
            self._validated_path(config["kind"], config["mode"], str(config.get("file", "")))
        return config

    def load(self, kind: str, filename: str | None) -> dict[str, Any]:
        if not filename:
            raise ValueError(f"no workflow registered for {kind}")
        path = self._validated_path(kind, "", filename)
        source = workflow_from_png(path) if path.suffix.lower() == ".png" else json.loads(path.read_text(encoding="utf-8"))
        if "nodes" not in source or "links" not in source:
            return source
        definitions = self.node_definitions(
            node.get("type") for node in source["nodes"] if node.get("mode", 0) == 0
        )
        return convert_workflow(source, definitions)

    def _validated_path(self, kind: str, mode: str, filename: str) -> Path:
        path = (self.workflows_path / filename).resolve()
        if not path.is_relative_to(self.workflows_path.resolve()) or path.suffix.lower() not in {".json", ".png"}:
            message = f"invalid registered workflow file for {kind}.{mode}" if mode else "invalid workflow name"
            raise RuntimeError(message) if mode else ValueError(message)
        if not path.is_file():
            message = f"registered workflow is missing: {filename}" if mode else f"workflow not configured: {filename}"
            raise FileNotFoundError(message)
        return path
