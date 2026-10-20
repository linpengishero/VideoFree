# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Read-only voice definitions owned by installed plugins."""

from pathlib import Path
import logging

from ..generation.plugins import IDENTIFIER, PluginCatalog, contained_file

logger = logging.getLogger(__name__)


def voice_presets(directory: Path, context=None) -> dict:
    catalog = PluginCatalog(directory, context)
    plugins, _ = catalog.scan()
    result = {}
    for plugin in plugins:
        target = plugin.get("voice_presets")
        if not target:
            continue
        config = next(iter(plugin["capabilities"].values()), None)
        if not config:
            continue
        try:
            definitions = catalog._load_handler(config, target)()
            if not isinstance(definitions, dict):
                raise ValueError("Voice presets must be a dictionary")
            pending = {}
            for key, definition in definitions.items():
                if not isinstance(key, str) or not IDENTIFIER.fullmatch(key):
                    raise ValueError(f"Invalid voice preset id: {key}")
                if key in result:
                    raise ValueError(f"Duplicate voice preset: {key}")
                if not isinstance(definition, dict) or not definition.get("display_name"):
                    raise ValueError(f"Invalid voice preset: {key}")
                if definition.get("sample_file"):
                    contained_file(directory / config["plugin_folder"], definition["sample_file"])
                pending[key] = {**definition, "plugin_id": plugin["id"], "plugin_folder": config["plugin_folder"]}
            result.update(pending)
        except Exception:
            logger.exception("Cannot load voice presets from plugin %s", plugin["id"])
    return result


class VoicePresets:
    def __init__(self, context):
        self.context = context

    def items(self):
        return [self._item(key, value) for key, value in voice_presets(self.context.paths.plugins, self.context).items()]

    def get(self, key):
        definition = voice_presets(self.context.paths.plugins, self.context).get(key)
        return self._item(key, definition) if definition else None

    def _item(self, key, definition):
        sample = Path(definition["sample_file"]).name if definition.get("sample_file") else None
        return {**definition, "preset_key": key, "model": definition.get("model", definition["plugin_id"]),
                "sample_audio_name": sample, "sample_audio_url": f"/v1/voices/{key}/sample" if sample else None}

    def sample_path(self, item):
        root = self.context.paths.plugins / item["plugin_folder"]
        if item.get("sample_file"):
            return contained_file(root, item["sample_file"])
        return None
