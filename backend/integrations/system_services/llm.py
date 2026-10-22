# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Typed LLM facade retained on top of the generic system-service registry."""

from pathlib import Path
from typing import Any, Protocol

from .registry import SystemServiceRegistry


class LLMProvider(Protocol):
    def build_chat_request(self, settings: dict[str, Any], messages: list[dict[str, Any]],
                           max_tokens: int, tools: list[dict[str, Any]] | None,
                           tool_choice: str | dict[str, Any] | None, *,
                           plain_request: bool = False, disable_thinking: bool = False
                           ) -> tuple[str, dict[str, Any], dict[str, str], bool]: ...

    def parse_chat_response(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_models(self, base_url: str, api_key: str = "") -> list[str]: ...


class LLMProviderCatalog(SystemServiceRegistry):
    """Compatibility facade for callers that only need the LLM service."""

    def __init__(self, directory: Path):
        super().__init__(directory)
