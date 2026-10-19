from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Protocol


PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class LLMProvider(Protocol):
    def build_chat_request(self, settings: dict[str, Any], messages: list[dict[str, Any]],
                           max_tokens: int, tools: list[dict[str, Any]] | None,
                           tool_choice: str | dict[str, Any] | None, *,
                           plain_request: bool = False, disable_thinking: bool = False
                           ) -> tuple[str, dict[str, Any], dict[str, str], bool]: ...

    def parse_chat_response(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_models(self, base_url: str, api_key: str = "") -> list[str]: ...


class LLMProviderCatalog:
    """Loads trusted provider packages declared under the system-services directory."""

    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self._providers: dict[str, tuple[dict[str, Any], LLMProvider]] = {}
        self.errors: list[dict[str, str]] = []
        self._load()

    def _load(self) -> None:
        if not self.directory.is_dir():
            return
        for manifest_path in sorted(self.directory.glob("*/provider.json")):
            try:
                root = self.directory
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                provider_id = manifest.get("id")
                if manifest.get("schema_version") != 1 or not isinstance(provider_id, str) or not PROVIDER_ID.fullmatch(provider_id):
                    raise ValueError("Invalid system service provider identity")
                if provider_id in self._providers:
                    raise ValueError(f"Duplicate system service provider: {provider_id}")
                if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
                    raise ValueError("Provider requires a display name")
                defaults = manifest.get("defaults", {})
                if (not isinstance(defaults, dict)
                        or set(defaults) - {"ai_base_url", "ai_model"}
                        or any(not isinstance(value, str) for value in defaults.values())):
                    raise ValueError("Provider defaults may only declare string ai_base_url and ai_model values")
                target = manifest.get("entry", "")
                filename, separator, symbol = target.partition(":")
                module_path = (self.directory / filename).resolve()
                if (not separator or not symbol.isidentifier() or not module_path.is_relative_to(root)
                        or not module_path.is_file() or module_path.suffix != ".py"):
                    raise ValueError("Provider entry must reference a local Python class")
                module_name = "videofree_system_service_" + hashlib.sha256(
                    f"{module_path}:{module_path.stat().st_mtime_ns}".encode()
                ).hexdigest()
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None or spec.loader is None:
                    raise ValueError("Cannot load provider entry")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                provider_type = getattr(module, symbol)
                provider = provider_type(manifest)
                if not all(callable(getattr(provider, method, None)) for method in (
                    "build_chat_request", "parse_chat_response", "list_models"
                )):
                    raise ValueError("LLM provider does not implement the provider protocol")
                self._providers[provider_id] = (manifest, provider)
            except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError) as exc:
                self.errors.append({"provider": manifest_path.parent.name, "error": str(exc)})

    def items(self) -> list[dict[str, Any]]:
        return [{"id": manifest["id"], "name": manifest["name"],
                 "defaults": dict(manifest.get("defaults", {}))}
                for manifest, _ in self._providers.values()]

    def get(self, provider_id: str) -> LLMProvider:
        provider = self._providers.get(str(provider_id))
        if not provider:
            raise ValueError(f"LLM Provider 未注册或不可用: {provider_id}")
        return provider[1]

    def contains(self, provider_id: str) -> bool:
        return str(provider_id) in self._providers
