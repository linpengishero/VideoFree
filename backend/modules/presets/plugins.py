# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Read-only preset discovery from installed plugin declarations."""

from ..generation.plugins import PluginCatalog
from .voices import VoicePresets


def plugin_presets(context, plugin_id):
    plugins, _ = PluginCatalog(context.paths.plugins, context).scan()
    plugin = next((item for item in plugins if item['id'] == plugin_id), None)
    if plugin is None:
        raise ValueError('Plugin is not installed or enabled')
    capabilities = plugin.get('capabilities', {})
    domains = {config.get('category') for config in capabilities.values()}
    return {
        'plugin_id': plugin_id,
        'fields': [
            {'capability_id': identifier, 'bind': field['bind'], 'options': field['options']}
            for identifier, config in capabilities.items()
            for field in config.get('ui', {}).get('fields', []) if field.get('options')
        ],
        'voices': [item for item in VoicePresets(context).items() if item['plugin_id'] == plugin_id],
        'creative_presets': [dict(item, domain=domain) for domain in sorted(domains - {None})
                             for item in context.db.creative_presets(domain)],
    }
