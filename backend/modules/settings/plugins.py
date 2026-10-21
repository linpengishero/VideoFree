# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Declarative plugin settings stored as literal values in each plugin's .env."""
import json
import os
from pathlib import Path
import re
import tempfile

from ..generation.plugins import PluginCatalog


def validate_settings_schema(schema):
    if not isinstance(schema, dict) or not isinstance(schema.get("fields"), list):
        raise ValueError("Plugin settings requires fields")
    if not isinstance(schema.get("title", ""), str) or not isinstance(schema.get("description", ""), str):
        raise ValueError("Invalid plugin settings title or description")
    keys, bindings = set(), set()
    for field in schema["fields"]:
        key = field.get("key", "") if isinstance(field, dict) else ""
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in keys:
            raise ValueError("Invalid or duplicate plugin setting key")
        if field.get("type", "string") not in {"string", "secret", "url", "boolean", "number", "select"} or not isinstance(field.get("label"), str):
            raise ValueError("Invalid plugin setting field")
        binding = field.get("runtime_key")
        if binding and (not re.fullmatch(r"[a-z][a-z0-9_]*", binding) or binding in bindings):
            raise ValueError("Invalid or duplicate plugin runtime setting")
        if field.get("type") == "select" and not field.get("options"):
            raise ValueError("Plugin select setting requires options")
        if field.get("type") == "secret" and field.get("default"):
            raise ValueError("Plugin secrets cannot have manifest defaults")
        if field.get("type") == "select" and any(
            not isinstance(option, dict) or "value" not in option or not isinstance(option.get("label"), str)
            for option in field["options"]
        ):
            raise ValueError("Invalid plugin setting options")
        keys.add(key)
        if binding:
            bindings.add(binding)


class PluginSettings:
    def __init__(self, context):
        self.context = context

    def _plugins(self):
        return [p for p in PluginCatalog(self.context.paths.plugins, self.context).scan()[0] if p.get("settings", {}).get("fields")]

    def _plugin(self, plugin_id):
        plugin = next((p for p in self._plugins() if p["id"] == plugin_id), None)
        if not plugin:
            raise ValueError("插件不存在或未注册配置")
        return plugin

    def _path(self, plugin):
        root = self.context.paths.plugins.resolve()
        # Resolve by discovered folder, not by a client-supplied path.
        folder = root / plugin["_plugin_folder"]
        path = (folder / ".env").resolve()
        if path.parent != folder.resolve() or not path.is_relative_to(root):
            raise ValueError("插件配置路径无效")
        return path

    @staticmethod
    def _read(path):
        values = {}
        if not path.exists():
            return values
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.removeprefix("export ").partition("=")
            if not separator:
                continue
            value = value.strip()
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            values[key.strip()] = value
        return values

    def values(self, plugin_id):
        plugin = self._plugin(plugin_id)
        stored = self._read(self._path(plugin))
        return {field["key"]: stored.get(field["key"], field.get("default", ""))
                for field in plugin["settings"]["fields"]}

    def catalog(self):
        return [{"id": p["id"], "name": p["settings"].get("title", p.get("name", p["id"])),
                 "name_key": p["settings"].get("title_key", p.get("name_key", "")),
                 "schema": p["settings"]} for p in self._plugins()]

    def read(self, plugin_id):
        plugin = self._plugin(plugin_id)
        values = self.values(plugin_id)
        for field in plugin["settings"]["fields"]:
            if field.get("type") == "secret":
                values[field["key"]] = "********" if values[field["key"]] else ""
        return values

    def save(self, plugin_id, supplied):
        plugin = self._plugin(plugin_id)
        path = self._path(plugin)
        stored = self._read(path)
        fields = {f["key"]: f for f in plugin["settings"]["fields"]}
        if not isinstance(supplied, dict) or set(supplied) - fields.keys():
            raise ValueError("包含未注册的插件配置项")
        for key, value in supplied.items():
            field = fields[key]
            if field.get("type") == "secret" and value == "********":
                continue
            if not isinstance(value, (str, bool, int, float)):
                raise ValueError(f"配置值无效：{field['label']}")
            value = str(value).strip()
            if len(value) > 8192 or "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError(f"配置值无效：{field['label']}")
            if value and field.get("prefix") and not value.startswith(field["prefix"]):
                raise ValueError(f"{field['label']} 必须以 {field['prefix']} 开头")
            if value and field.get("type") == "url":
                from urllib.parse import urlparse
                if urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc:
                    raise ValueError(f"{field['label']} 必须是 HTTP(S) 地址")
            if field.get("type") == "boolean" and value.lower() not in {"true", "false"}:
                raise ValueError(f"{field['label']} 必须为布尔值")
            if field.get("type") == "number":
                import math
                try:
                    number = float(value)
                except ValueError:
                    raise ValueError(f"{field['label']} 必须为数字") from None
                if not math.isfinite(number) or not field.get("minimum", -math.inf) <= number <= field.get("maximum", math.inf):
                    raise ValueError(f"{field['label']} 超出范围")
            if field.get("type") == "select" and value not in {str(o["value"]) for o in field["options"]}:
                raise ValueError(f"{field['label']} 选项无效")
            stored[key] = value
        # Replace atomically; unrelated .env keys keep their values.
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=path.parent)
        except OSError as exc:
            raise ValueError("插件目录不可写，无法保存配置") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                for key, value in stored.items():
                    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                        raise ValueError(".env 中存在无效配置名")
                    output.write(f"{key}={json.dumps(value, ensure_ascii=False)}\n")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return self.read(plugin_id)

    def runtime(self, plugin_id):
        plugin = next((p for p in self._plugins() if p["id"] == plugin_id), None)
        if not plugin:
            return {}
        values = self.values(plugin_id)
        result = {}
        for field in plugin["settings"]["fields"]:
            if field.get("runtime_key"):
                value = values[field["key"]]
                if field.get("required") and not value:
                    raise ValueError(f"请在设置 → {plugin['settings'].get('title', plugin_id)} 配置 {field['label']}")
                if field.get("type") == "boolean":
                    value = str(value).lower() == "true"
                elif field.get("type") == "number":
                    value = float(value)
                result[field["runtime_key"]] = value
        return result

    def migrate_legacy(self):
        legacy = str(self.context.db.settings().get("grsai_api_key") or os.getenv("GRSAI_API_KEY", "")).strip()
        try:
            current = self.values("gpt-image")
        except ValueError:
            return
        if legacy and not current.get("GRSAI_API_KEY"):
            self.save("gpt-image", {"GRSAI_API_KEY": legacy})
        self.context.db.delete_settings(["grsai_api_key"])
