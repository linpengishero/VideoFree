import json
from pathlib import Path
from typing import Any, Callable, Iterable

from ...integrations.comfyui.workflow_loader import convert_workflow, workflow_from_png


class WorkflowRegistry:
    def __init__(
        self,
        workflows_path: Path,
        registry_path: Path,
        node_definitions: Callable[[Iterable[str]], dict[str, Any]],
    ) -> None:
        self.workflows_path = workflows_path
        self.registry_path = registry_path
        self.node_definitions = node_definitions

    def all(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError("workflow registry is missing") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"workflow registry is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("workflow registry must be an object")
        return value

    def resolve(self, kind: str, mode: str, model: str = "", variant: str = "") -> dict[str, Any]:
        registry = self.all()
        config = registry.get(f"{kind}.{model}.{mode}") if model else None
        config = config or registry.get(f"{kind}.{mode}")
        if not isinstance(config, dict) or config.get("kind") != kind or config.get("mode") != mode:
            raise ValueError(f"unsupported {kind} mode: {mode}")
        # Post-processing has its own recipe; a parent's generation speed is irrelevant.
        if kind == "video" and mode in {"upscale", "interpolate", "lms_enhance"}:
            variant = ""
        if variant:
            selected = config.get("variants", {}).get(variant)
            if not isinstance(selected, dict):
                raise ValueError(f"unsupported {kind} variant: {variant}")
            config = {**config, **selected, "variant": variant}
        if config.get("executor", "comfyui") != "comfyui":
            return config
        self._validated_path(kind, mode, str(config.get("file", "")))
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
