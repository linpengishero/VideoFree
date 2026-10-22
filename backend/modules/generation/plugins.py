# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Folder-based plugin discovery. Installed Python handlers are trusted local code."""

import hashlib
import importlib
import copy
from functools import lru_cache
import json
import logging
import math
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any
from jsonschema import Draft202012Validator, SchemaError
from referencing import Resource, Registry
from referencing.jsonschema import DRAFT202012
from referencing.exceptions import Unresolvable

from .plugin_ui import validate_form
from ...core.version import PLATFORM_VERSION

logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")
PLUGIN_MANIFEST_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "plugin-manifest-v1.schema.json"
APPLICATION_KEYS = {
    "name", "name_key", "entry", "ui", "resource_entry", "startup", "source_types",
    "selection_label", "selection_label_key", "scope", "order", "icon", "library_outputs",
    "requires_project_flags", "category_selector",
}
PROJECT_TOOL_KEYS = {
    "name", "name_key", "entry", "ui", "scope", "order", "icon", "dialog",
    "requires_project_flags",
}


def _version_tuple(value: str, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"{label} must use major.minor.patch")
    return tuple(int(part) for part in value.split("."))


def _validate_requires(value) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {"platform_min", "platform_max_exclusive"}:
        raise ValueError("Plugin requires only supports platform_min and platform_max_exclusive")
    minimum = _version_tuple(value.get("platform_min", "0.0.0"), "platform_min")
    maximum = _version_tuple(value.get("platform_max_exclusive", "999999.0.0"), "platform_max_exclusive")
    current = _version_tuple(PLATFORM_VERSION, "platform version")
    if minimum >= maximum:
        raise ValueError("Plugin platform compatibility range is empty")
    if current < minimum or current >= maximum:
        raise ValueError(
            f"Plugin requires VideoFree Studio >= {value.get('platform_min', '0.0.0')}"
            f" and < {value.get('platform_max_exclusive', 'unbounded')}; current is {PLATFORM_VERSION}"
        )


def _validate_bundle_ui(root: Path, value, label: str) -> str:
    if not isinstance(value, dict) or set(value) != {"entry"} or not isinstance(value.get("entry"), str):
        raise ValueError(f"{label} ui requires only an entry")
    entry = contained_file(root, value["entry"])
    if not entry.is_relative_to((root / "ui" / "dist").resolve()) or entry.suffix.lower() != ".js":
        raise ValueError(f"{label} ui entry must be a JavaScript module inside ui/dist")
    return value["entry"]


def validate_plugin_json_schema(schema, label="Plugin"):
    if not isinstance(schema, dict):
        raise ValueError(f"{label} schema must be an object")
    resolver = Registry().with_resource("urn:videofree:schema", Resource.from_contents(schema, default_specification=DRAFT202012)).resolver("urn:videofree:schema")
    def check_refs(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef"} and (not isinstance(item, str) or not item.startswith("#")):
                    raise ValueError("Plugin action schemas only support local references")
                if key in {"$ref", "$dynamicRef"}:
                    try:
                        resolver.lookup(item)
                    except Unresolvable as exc:
                        raise ValueError(f"Unresolved plugin schema reference: {item}") from exc
                check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)
    check_refs(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid {label} schema: {exc.message}") from exc


def validate_action_schema(schema):
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("Plugin action input_schema must describe an object")
    validate_plugin_json_schema(schema, "plugin action")


@lru_cache(maxsize=1)
def plugin_manifest_schema() -> dict[str, Any]:
    schema = json.loads(PLUGIN_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    validate_plugin_json_schema(schema, "plugin manifest")
    return schema


@lru_cache(maxsize=1)
def _plugin_manifest_validator() -> Draft202012Validator:
    return Draft202012Validator(plugin_manifest_schema())


def validate_plugin_manifest(value: dict[str, Any]) -> None:
    errors = sorted(_plugin_manifest_validator().iter_errors(value),
                    key=lambda item: list(item.absolute_path))
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path)
    if error.validator == "additionalProperties" and not error.absolute_path:
        raise ValueError(f"Unknown plugin manifest fields: {error.message}")
    if error.validator == "additionalProperties" and location == "application":
        raise ValueError(f"Unknown application fields: {error.message}")
    if error.validator == "additionalProperties" and location == "project_tool":
        raise ValueError(f"Unknown project tool fields: {error.message}")
    if re.fullmatch(r"actions\.\d+\.description", location):
        raise ValueError("Plugin action description must be a string")
    if re.fullmatch(r"capabilities\.[^.]+(?:\.[^.]+)*\.ui_hidden", location):
        raise ValueError("ui_hidden must be a boolean")
    raise ValueError(f"Invalid plugin manifest{f' at {location}' if location else ''}: {error.message}")


def contained_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not name or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Plugin file is missing or outside its folder: {name}")
    return path


class PluginCatalog:
    def __init__(self, directory: Path, context=None):
        self.directory = directory.resolve()
        self.context = context

    def scan(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        if self.context is None or not hasattr(self.context, "plugin_catalogs"):
            return self._scan()
        key = str(self.directory)
        with self.context.plugin_catalog_lock:
            if key not in self.context.plugin_catalogs:
                self.context.plugin_catalogs[key] = self._scan()
            return copy.deepcopy(self.context.plugin_catalogs[key])

    def _scan(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        plugins, errors = [], []
        ids, capability_ids, categories = set(), set(), {}
        action_ids = set()
        for path in sorted(self.directory.glob("*/plugin.json")):
            try:
                plugin = self._read(path)
                if not plugin.get("enabled", True):
                    continue
                if plugin["id"] in ids:
                    raise ValueError(f"Duplicate plugin id: {plugin['id']}")
                duplicates = capability_ids.intersection(plugin["capabilities"])
                if duplicates:
                    raise ValueError(f"Duplicate capabilities: {sorted(duplicates)}")
                for category in plugin["categories"]:
                    old = categories.get(category["id"])
                    if old and old != category:
                        raise ValueError(f"Conflicting category: {category['id']}")
                plugin_actions = {action["id"] for action in plugin["actions"]}
                if action_ids.intersection(plugin_actions):
                    raise ValueError(f"Duplicate plugin actions: {sorted(action_ids.intersection(plugin_actions))}")
                ids.add(plugin["id"])
                capability_ids.update(plugin["capabilities"])
                action_ids.update(plugin_actions)
                categories.update({item["id"]: item for item in plugin["categories"]})
                plugins.append(plugin)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                errors.append({"plugin": path.parent.name, "error": str(exc)})
                logger.warning("Plugin %s disabled: %s", path.parent.name, exc)
        return plugins, errors

    def _read(self, path: Path) -> dict[str, Any]:
        root = path.parent.resolve()
        if not root.is_relative_to(self.directory.resolve()):
            raise ValueError("Plugin folder must stay inside plugins")
        value = json.loads(contained_file(root, "plugin.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Plugin manifest must be an object")
        validate_plugin_manifest(value)
        if value.get("enabled") is False:
            return {"enabled": False}
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported plugin schema_version")
        _validate_requires(value.get("requires"))
        contained_file(root, "INSTALL.md")
        for key in ("id", "version"):
            if not isinstance(value.get(key), str) or not IDENTIFIER.fullmatch(value[key]):
                raise ValueError(f"Invalid plugin {key}")
        value["_plugin_folder"] = root.name
        localization = value.get("localization")
        if localization is not None:
            if (not isinstance(localization, dict)
                    or set(localization) - {"default_locale", "messages"}
                    or localization.get("default_locale") not in {"zh-CN", "en-US"}
                    or not isinstance(localization.get("messages"), dict)
                    or localization["default_locale"] not in localization["messages"]):
                raise ValueError("Invalid plugin localization declaration")
            messages = {}
            for locale, filename in localization["messages"].items():
                if locale not in {"zh-CN", "en-US"} or filename != f"locales/{locale}.json":
                    raise ValueError("Plugin locales must use locales/<locale>.json")
                pack = json.loads(contained_file(root, filename).read_text(encoding="utf-8"))
                if not isinstance(pack, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in pack.items()):
                    raise ValueError("Plugin locale messages must be a flat string dictionary")
                messages[locale] = pack
            value["ui_messages"] = messages
        style_library = value.get("style_library")
        if style_library is not None:
            if not isinstance(style_library, dict):
                raise ValueError("style_library must be an object")
            if set(style_library) - {"directory", "default_id"}:
                raise ValueError("style_library only supports plugin-local directory and default_id")
            if "directory" in style_library:
                directory = style_library.get("directory")
                relative = Path(directory) if isinstance(directory, str) else Path()
                resolved = (root / relative).resolve()
                if (not isinstance(directory, str) or not directory or relative.is_absolute()
                        or relative.drive or ".." in relative.parts or not resolved.is_relative_to(root)
                        or not resolved.is_dir()):
                    raise ValueError("style_library directory must be a local plugin directory")
                default_id = style_library.get("default_id", "")
                if not isinstance(default_id, str) or (default_id and not IDENTIFIER.fullmatch(default_id)):
                    raise ValueError("style_library default_id must be a stable identifier")
            else:
                raise ValueError("style_library requires a plugin-local directory")
        assets = value.get('assets', [])
        if not isinstance(assets, list) or any(not isinstance(name, str) for name in assets):
            raise ValueError('Plugin assets must be a list of local file paths')
        for name in assets:
            contained_file(root, name)
        if not isinstance(value.get("categories"), list) or not isinstance(value.get("capabilities"), dict):
            raise ValueError("categories must be a list and capabilities an object")
        if "settings" in value:
            from ..settings.plugins import validate_settings_schema
            validate_settings_schema(value["settings"])
        application = value.get('application')
        if application is not None:
            if not isinstance(application, dict) or not isinstance(application.get('name'), str) or not application['name'].strip():
                raise ValueError('Application requires a name')
            if set(application) - APPLICATION_KEYS:
                raise ValueError(f"Unknown application fields: {sorted(set(application) - APPLICATION_KEYS)}")
            ui = application.get('ui')
            if bool(application.get('entry')) == bool(ui):
                raise ValueError('Application requires exactly one of entry or ui')
            if application.get('entry'):
                entry_path = application['entry']
                if (contained_file(root, entry_path).suffix != '.vue'
                        or Path(entry_path).parent.as_posix() != 'ui'):
                    raise ValueError('Application entry must be a local Vue component')
            if 'resource_entry' in application:
                entry_path = application.get('resource_entry', '')
                if (contained_file(root, entry_path).suffix != '.vue'
                        or Path(entry_path).parent.as_posix() != 'ui'):
                    raise ValueError('Application resource_entry must be a local Vue component')
            if application.get('startup'):
                filename, separator, symbol = application['startup'].partition(':')
                if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != '.py':
                    raise ValueError('Application startup must be a local Python file:function')
            if not isinstance(application.get('source_types', []), list) or any(kind not in {'image', 'video', 'tts', 'music', 'audio'} for kind in application.get('source_types', [])):
                raise ValueError('Invalid application source_types')
            if not isinstance(application.get('selection_label', ''), str):
                raise ValueError('Invalid application selection_label')
            if application.get('scope', 'project') not in {'workspace', 'project', 'category', 'resource'}:
                raise ValueError('Invalid application scope')
            if ui is not None:
                _validate_bundle_ui(root, ui, 'Application')
            if 'order' in application and (type(application['order']) is not int or application['order'] < 0):
                raise ValueError('Application order must be a non-negative integer')
            icon = application.get('icon')
            if icon and isinstance(icon, str) and not icon.startswith(('solar:', 'mdi:', 'lucide:')):
                icon_path = contained_file(root, icon)
                if icon_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                    raise ValueError('Application icon must be a local image')
            outputs = application.get('library_outputs')
            if outputs is not None:
                if not isinstance(outputs, dict) or not isinstance(outputs.get('directory'), str) or not IDENTIFIER.fullmatch(outputs['directory']) or outputs['directory'] in {'.', '..'}:
                    raise ValueError('Invalid application output directory')
                if not isinstance(outputs.get('filenames'), list) or not outputs['filenames'] or any(not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or name in {'.', '..'} for name in outputs['filenames']):
                    raise ValueError('Invalid application output filenames')
        project_tool = value.get('project_tool')
        if project_tool is not None:
            if not isinstance(project_tool, dict) or not isinstance(project_tool.get('name'), str) or not project_tool['name'].strip():
                raise ValueError('Project tool requires a name')
            if set(project_tool) - PROJECT_TOOL_KEYS:
                raise ValueError(f"Unknown project tool fields: {sorted(set(project_tool) - PROJECT_TOOL_KEYS)}")
            ui = project_tool.get('ui')
            if bool(project_tool.get('entry')) == bool(ui):
                raise ValueError('Project tool requires exactly one of entry or ui')
            if project_tool.get('entry'):
                entry = project_tool['entry']
                entry_path = contained_file(root, entry)
                if entry_path.suffix != '.vue' or Path(entry).parent.as_posix() != 'ui':
                    raise ValueError('Project tool entry must be a local Vue component')
            else:
                _validate_bundle_ui(root, ui, 'Project tool')
            if project_tool.get('scope', 'category') not in {'project', 'category'}:
                raise ValueError('Invalid project tool scope')
            required_flags = project_tool.get('requires_project_flags', [])
            if not isinstance(required_flags, list) or any(not isinstance(flag, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', flag) for flag in required_flags):
                raise ValueError('Invalid project tool project flags')
            if 'order' in project_tool and (type(project_tool['order']) is not int or project_tool['order'] < 0):
                raise ValueError('Project tool order must be a non-negative integer')
            dialog = project_tool.get('dialog', {})
            if not isinstance(dialog, dict) or set(dialog) - {'width', 'height'}:
                raise ValueError('Project tool dialog supports width and height only')
            for dimension in dialog.values():
                if dimension != 'auto' and (type(dimension) is not int or not 1 <= dimension <= 4096):
                    raise ValueError('Project tool dialog dimensions must be auto or pixels (1-4096)')
            icon = project_tool.get('icon')
            if icon and isinstance(icon, str) and not icon.startswith(('solar:', 'mdi:', 'lucide:')):
                icon_path = contained_file(root, icon)
                if icon_path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                    raise ValueError('Project tool icon must be a local image')
        collaboration_ui = value.get('collaboration_ui')
        if collaboration_ui is not None:
            if isinstance(collaboration_ui, str):
                entry_path = contained_file(root, collaboration_ui)
                if entry_path.suffix != '.vue' or Path(collaboration_ui).parent.as_posix() != 'ui':
                    raise ValueError('Collaboration UI entry must be a local Vue component')
            else:
                _validate_bundle_ui(root, collaboration_ui, 'Collaboration')
        actions = value.get("actions", [])
        lifecycle = value.get("resource_lifecycle", {})
        if not isinstance(lifecycle, dict) or set(lifecycle) - {"completed", "recover", "delete"}:
            raise ValueError("Invalid resource_lifecycle hooks")
        for target in lifecycle.values():
            filename, separator, symbol = str(target).partition(":")
            if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                raise ValueError("Resource lifecycle hook must be a local Python file:function")
        application_lifecycle = value.get("application_lifecycle", {})
        if not isinstance(application_lifecycle, dict) or set(application_lifecycle) - {"project_delete", "category_delete"}:
            raise ValueError("Invalid application_lifecycle hooks")
        for target in application_lifecycle.values():
            filename, separator, symbol = str(target).partition(":")
            if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                raise ValueError("Application lifecycle hook must be a local Python file:function")
        if not isinstance(actions, list):
            raise ValueError("actions must be a list")
        local_action_ids: set[str] = set()
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get("id"), str) or not IDENTIFIER.fullmatch(action["id"]) or action["id"] in local_action_ids:
                raise ValueError("Invalid or duplicate plugin action")
            if action.get("scope") not in {"resource", "workspace", "automation"}:
                raise ValueError(f"Invalid plugin action scope: {action['id']}")
            if not isinstance(action.get("name"), str) or not action["name"].strip():
                raise ValueError(f"Plugin action requires a name: {action['id']}")
            if "description" in action and not isinstance(action["description"], str):
                raise ValueError("Plugin action description must be a string")
            if "model_name" in action and (not isinstance(action["model_name"], str) or not action["model_name"].strip()):
                raise ValueError("Plugin action model_name must be a non-empty string")
            if "automation" in action and type(action["automation"]) is not bool:
                raise ValueError("Plugin action automation must be boolean")
            source_types = action.get("source_types", [])
            if not isinstance(source_types, list) or set(source_types) - {"image", "video", "tts", "music", "audio"}:
                raise ValueError(f"Invalid plugin action source_types: {action['id']}")
            if action["scope"] == "resource" and not source_types:
                raise ValueError(f"Resource action requires source_types: {action['id']}")
            capability_id = action.get("capability_id")
            if capability_id is not None and capability_id not in value["capabilities"]:
                raise ValueError(f"Plugin action capability does not exist: {action['id']}")
            if capability_id is None and not action.get("handler"):
                raise ValueError("Plugin action requires capability_id or handler")
            if "requires_latent" in action or "preview_only" in action:
                raise ValueError("Use source_schema and availability_handler for resource conditions")
            if "source_schema" in action:
                validate_action_schema(action["source_schema"])
            for field in ("handler", "availability_handler"):
                if action.get(field):
                    filename, separator, symbol = action[field].partition(":")
                    if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                        raise ValueError(f"Plugin action {field} must be a local Python file:function")
            input_schema = action.get("input_schema", {"type": "object", "properties": {}})
            validate_action_schema(input_schema)
            action["input_schema"] = input_schema
            if "ui" in action:
                capability_config = value["capabilities"].get(capability_id, {})
                validate_form(action["ui"], capability_config,
                              postprocess=capability_config.get("operation") == "postprocess",
                              action_schema=input_schema)
            local_action_ids.add(action["id"])
        if value.get("voice_presets"):
            filename, separator, symbol = str(value["voice_presets"]).partition(":")
            if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                raise ValueError("voice_presets must be a local Python file:function")
        category_ids = set()
        for item in value["categories"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not IDENTIFIER.fullmatch(item["id"]) or not isinstance(item.get("name"), str) or item["id"] in category_ids:
                raise ValueError("Invalid category")
            category_ids.add(item["id"])
        modes = value.get("modes", [])
        if not isinstance(modes, list):
            raise ValueError("modes must be a list")
        mode_ids = set()
        for mode in modes:
            if not isinstance(mode, dict) or not isinstance(mode.get("id"), str) or not IDENTIFIER.fullmatch(mode["id"]) or mode["id"] in mode_ids or not isinstance(mode.get("name"), str):
                raise ValueError("Invalid or duplicate processing mode")
            if mode.get("handler"):
                filename, separator, symbol = mode["handler"].partition(":")
                if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                    raise ValueError("Mode handler must be a local Python file:function")
            elif mode["id"] != "direct":
                raise ValueError("Non-direct modes require a handler")
            mode_ids.add(mode["id"])
        value["modes"] = modes
        if value["capabilities"] and "direct" not in mode_ids:
            raise ValueError("A direct processing mode is required")
        ui_models = value.get("ui_models", [])
        if not isinstance(ui_models, list):
            raise ValueError("ui_models must be a list")
        model_ids, registered = set(), set()
        model_orders: set[int] = set()
        default_models: dict[str, str] = {}
        for model in ui_models:
            if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not IDENTIFIER.fullmatch(model["id"]) or model["id"] in model_ids or not isinstance(model.get("name"), str) or not model["name"].strip() or model.get("category") not in category_ids:
                raise ValueError("Invalid or duplicate UI model")
            order = model.get("selector_order", 0)
            if type(order) is not int or order < 0 or order in model_orders:
                raise ValueError("Invalid or duplicate UI model selector_order")
            if "default" in model and type(model["default"]) is not bool:
                raise ValueError("UI model default must be boolean")
            if model.get("default"):
                if model["category"] in default_models:
                    raise ValueError(f"Duplicate default UI model: {model['category']}")
                default_models[model["category"]] = model["id"]
            model_ids.add(model["id"])
            model_orders.add(order)
            functions = model.get("functions")
            if not isinstance(functions, list) or not functions:
                raise ValueError("UI model requires functions")
            function_orders: set[int] = set()
            for index, function in enumerate(functions):
                if not isinstance(function, dict) or not isinstance(function.get("capability_id"), str) or not isinstance(function.get("name"), str) or not function["name"].strip():
                    raise ValueError("Invalid UI model function")
                key = function["capability_id"]
                config = value["capabilities"].get(key)
                if key in registered or not isinstance(config, dict) or config.get("operation", "generate") != "generate" or config.get("category") != model["category"]:
                    raise ValueError(f"Invalid UI function capability: {key}")
                function_order = function.get("selector_order", index)
                if type(function_order) is not int or function_order < 0 or function_order in function_orders:
                    raise ValueError("Invalid UI model function selector_order")
                config["selector_order"] = order * 1000 + function_order
                function_orders.add(function_order)
                registered.add(key)
                config["selector_model"] = {
                    "id": model["id"], "name": model["name"], "plugin_id": value["id"],
                    **({"name_key": model["name_key"]} if "name_key" in model else {}),
                    "selector_order": order, "default": bool(model.get("default")),
                }
                config["mode_name"] = function["name"]
                if "name_key" in function:
                    config["mode_name_key"] = function["name_key"]
        if any(config.get("operation", "generate") == "generate" and not config.get("ui_hidden", False)
               for config in value["capabilities"].values()) and not ui_models:
            raise ValueError("Generation plugins must declare ui_models")
        missing = {key for key, config in value["capabilities"].items()
                   if config.get("operation", "generate") == "generate" and not config.get("ui_hidden", False)} - registered
        if missing:
            raise ValueError(f"Generation capabilities missing from ui_models: {', '.join(sorted(missing))}")
        revision = hashlib.sha256(path.read_bytes())
        for file in sorted(root.rglob("*")):
            if file.is_file() and (file.suffix in {".py", ".json", ".md", ".txt", ".png"}
                                   or file.relative_to(root).as_posix() in assets):
                revision.update(file.relative_to(root).as_posix().encode() + b"\0")
                revision.update(hashlib.sha256(file.read_bytes()).digest())
        for key, config in value["capabilities"].items():
            translation_action = config.get("prompt_translation_action", value.get("prompt_translation_action"))
            if translation_action is not None:
                action = next((item for item in actions if item['id'] == translation_action), None)
                if action is None or action['scope'] == 'resource':
                    raise ValueError("prompt_translation_action must reference a non-resource plugin action")
                config['prompt_translation_action'] = translation_action
            if "ui_hidden" in config and type(config["ui_hidden"]) is not bool:
                raise ValueError(f"ui_hidden must be a boolean: {key}")
            if config.get("ui_hidden") and key in registered:
                raise ValueError(f"Hidden capability cannot appear in ui_models: {key}")
            if not IDENTIFIER.fullmatch(key) or not isinstance(config, dict) or config.get("kind") not in {"image", "video", "tts", "music", "audio"}:
                raise ValueError(f"Invalid capability: {key}")
            if config.get("category") not in category_ids or not isinstance(config.get("mode"), str):
                raise ValueError(f"Invalid category or generation mode: {key}")
            for aliases in ("model_aliases", "mode_aliases"):
                if aliases in config and (not isinstance(config[aliases], list)
                        or any(not isinstance(alias, str) or not IDENTIFIER.fullmatch(alias) for alias in config[aliases])):
                    raise ValueError(f"Invalid {aliases}: {key}")
            for label in ("name", "model_id", "model_name", "provider_name", "skill_model", "skill_mode"):
                if label in config and (not isinstance(config[label], str) or not config[label].strip()):
                    raise ValueError(f"Invalid {label}: {key}")
            if "duration" in config:
                duration = config["duration"]
                if (not isinstance(duration, dict) or any(type(duration.get(field)) not in {int, float}
                        or not math.isfinite(duration[field]) for field in ("min", "max", "default"))
                        or not 0 < duration["min"] <= duration["default"] <= duration["max"]):
                    raise ValueError(f"Invalid duration: {key}")
            if "dimension_alignment" in config and (type(config["dimension_alignment"]) is not int or config["dimension_alignment"] <= 0):
                raise ValueError(f"Invalid dimension_alignment: {key}")
            selected_modes = config.get("processing_modes", ["direct"])
            if not isinstance(selected_modes, list) or not selected_modes or any(not isinstance(item, str) for item in selected_modes) or set(selected_modes) - mode_ids:
                raise ValueError(f"Unregistered processing mode: {key}")
            config["processing_modes"] = [dict(item) for item in modes if item["id"] in selected_modes]
            self._files(root, config)
            config.update(plugin_id=value["id"], plugin_version=value["version"], plugin_revision=revision.hexdigest(), plugin_folder=root.name)
            if value.get('collaboration_ui'):
                collaboration_ui = value['collaboration_ui']
                if isinstance(collaboration_ui, str):
                    config['collaboration_ui'] = collaboration_ui
                else:
                    config['collaboration_ui_entry'] = (
                        f"/api/v2/plugins/{value['id']}/ui/"
                        f"{collaboration_ui['entry'].split('ui/dist/', 1)[-1]}"
                    )
            config.setdefault("compiler", "declarative")
            if config.get("operation", "generate") not in {"generate", "postprocess"}:
                raise ValueError("Invalid capability operation")
            if "postprocess" in config:
                raise ValueError("postprocess declarations moved to plugin-level actions")
            if config.get("compiler") not in {"builtin", "declarative"}:
                raise ValueError("Unsupported workflow compiler")
            definitions = config.get("parameters", {})
            bindings = config.get("parameter_bindings", {})
            if not isinstance(bindings, dict):
                raise ValueError("parameter_bindings must be an object")
            for source, targets in bindings.items():
                if not IDENTIFIER.fullmatch(source) or not isinstance(targets, list) or not targets:
                    raise ValueError("Invalid parameter binding source or targets")
                for target in targets:
                    if (not isinstance(target, dict) or not isinstance(target.get("node"), (str, int))
                            or not isinstance(target.get("input"), str) or not target["input"]):
                        raise ValueError("Parameter bindings require node and input")
                    if "default" in target and type(target["default"]) not in {str, int, float, bool}:
                        raise ValueError("Parameter binding defaults must be scalar values")
            if not isinstance(definitions, dict):
                raise ValueError("parameters must be an object")
            validate_form(config.get("ui"), config)
            for name, definition in definitions.items():
                if not IDENTIFIER.fullmatch(name) or not isinstance(definition, dict) or definition.get("type", "string") not in {"string", "boolean", "integer", "number"}:
                    raise ValueError(f"Invalid parameter definition: {name}")
                if "enum" in definition and (not isinstance(definition["enum"], list) or not definition["enum"]):
                    raise ValueError(f"Invalid parameter enum: {name}")
                if name in {"width", "height", "duration", "fps", "seed"}:
                    raise ValueError(f"Reserved platform parameter: {name}")
                for bound in ("minimum", "maximum"):
                    if bound in definition and (type(definition[bound]) not in {int, float} or not math.isfinite(definition[bound])):
                        raise ValueError(f"Invalid parameter bound: {name}.{bound}")
                if definition.get("minimum", float("-inf")) > definition.get("maximum", float("inf")):
                    raise ValueError(f"Reversed parameter bounds: {name}")
                if "maxLength" in definition and (type(definition["maxLength"]) is not int or definition["maxLength"] < 0):
                    raise ValueError(f"Invalid parameter maxLength: {name}")
            validate_parameters({**config, "parameters": {key: {**item, "required": False} for key, item in definitions.items()}}, {})
            for field in ("compiler_handler", "executor_handler", "confirmation_handler", "speech_handler"):
                if config.get(field):
                    filename, separator, symbol = config[field].partition(":")
                    if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                        raise ValueError(f"{field} must be a local Python file:function")
            if config.get("executor", "comfyui") != "comfyui" and not config.get("executor_handler"):
                raise ValueError("Native capabilities require executor_handler")
        for action in actions:
            action.update(
                plugin_id=value["id"], plugin_version=value["version"],
                plugin_revision=revision.hexdigest(), plugin_folder=root.name,
            )
        value["actions"] = actions
        value['_plugin_revision'] = revision.hexdigest()
        return value

    def _files(self, root: Path, config: dict[str, Any]) -> None:
        if not isinstance(config.get("variants", {}), dict):
            raise ValueError("variants must be an object")
        if config.get("file"):
            path = contained_file(root, config["file"])
            if path.suffix.lower() not in {".json", ".png"}:
                raise ValueError("Workflow must be JSON or PNG")
            config["file"] = path.relative_to(self.directory).as_posix()
        elif config.get("executor", "comfyui") == "comfyui":
            raise ValueError("ComfyUI capability requires a workflow file")
        for variant in config.get("variants", {}).values():
            if not isinstance(variant, dict):
                raise ValueError("variant must be an object")
            if "file" in variant:
                self._files(root, {**variant, "executor": "comfyui"})
                variant["file"] = contained_file(root, variant["file"]).relative_to(self.directory).as_posix()

    def capabilities(self) -> dict[str, dict[str, Any]]:
        plugins, _ = self.scan()
        return {key: config for plugin in plugins for key, config in plugin["capabilities"].items()}

    def actions(self) -> dict[str, dict[str, Any]]:
        plugins, _ = self.scan()
        return {action["id"]: action for plugin in plugins for action in plugin["actions"]}

    def public(self) -> dict[str, Any]:
        plugins, errors = self.scan()
        categories = {item["id"]: {**item, "plugin_id": plugin["id"]} for plugin in plugins for item in plugin["categories"]}
        return {"items": [{key: value for key, value in plugin.items() if key not in {"capabilities", "modes", "actions", "resource_lifecycle", "application_lifecycle", "_plugin_folder", "_plugin_revision", "application", "project_tool"}} | {"modes": [{key: val for key, val in mode.items() if key != "handler"} for mode in plugin["modes"]], "capability_ids": list(plugin["capabilities"]), "action_ids": [action["id"] for action in plugin["actions"]]} for plugin in plugins], "applications": self.applications(plugins), "project_tools": self.project_tools(plugins), "categories": list(categories.values()), "errors": errors}

    def applications(self, plugins=None):
        if plugins is None:
            plugins, _ = self.scan()
        result = [dict(id=plugin['id'], plugin_folder=plugin['_plugin_folder'],
                     **{key: value for key, value in plugin['application'].items() if key != 'startup'})
                for plugin in plugins if plugin.get('application')]
        for item in result:
            icon = item.get('icon')
            if isinstance(icon, str) and not icon.startswith(('solar:', 'mdi:', 'lucide:')):
                item['icon_asset'] = icon
                item['icon'] = None
            item.setdefault('scope', 'project')
            item.setdefault('order', 1000)
            item.setdefault('category_selector', False)
            required_flags = item.get('requires_project_flags', [])
            if not isinstance(required_flags, list) or any(not isinstance(flag, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', flag) for flag in required_flags):
                raise ValueError(f"Invalid application project flags: {item['id']}")
            item['icon_text'] = (item.get('name') or item['id'])[:1]
            ui = item.get('ui')
            if isinstance(ui, dict) and ui.get('entry'):
                item['ui_entry'] = f"/api/v2/plugins/{item['id']}/ui/{ui['entry'].split('ui/dist/', 1)[-1]}"
        return sorted(result, key=lambda item: (item.get('order', 1000), item['id']))

    def project_tools(self, plugins=None):
        if plugins is None:
            plugins, _ = self.scan()
        result = [dict(id=plugin['id'], plugin_folder=plugin['_plugin_folder'],
                       **plugin['project_tool']) for plugin in plugins if plugin.get('project_tool')]
        for item in result:
            icon = item.get('icon')
            if isinstance(icon, str) and not icon.startswith(('solar:', 'mdi:', 'lucide:')):
                item['icon_asset'] = icon
                item['icon'] = None
            item.setdefault('scope', 'category')
            item.setdefault('order', 1000)
            item['icon_text'] = (item.get('name') or item['id'])[:1]
            ui = item.get('ui')
            if isinstance(ui, dict) and ui.get('entry'):
                item['ui_entry'] = f"/api/v2/plugins/{item['id']}/ui/{ui['entry'].split('ui/dist/', 1)[-1]}"
        return sorted(result, key=lambda item: (item.get('order', 1000), item['id']))

    async def start_applications(self, context):
        from ..shared.plugin_runtime import PluginRuntime
        from ..settings.plugins import PluginSettings
        plugins, _ = self.scan()
        for plugin in plugins:
            target = plugin.get('application', {}).get('startup')
            if target:
                config = dict(plugin_folder=plugin['_plugin_folder'], plugin_revision=plugin['_plugin_revision'])
                try:
                    handler = self._load_handler(config, target)
                    await handler(PluginRuntime(plugin['id'], PluginSettings(context).runtime(plugin['id']), context))
                except Exception:
                    logger.exception('Application plugin startup failed: %s', plugin['id'])

    def handler(self, config: dict[str, Any], mode_id: str):
        mode = next((item for item in config.get("processing_modes", []) if item["id"] == mode_id), None)
        if mode is None:
            raise ValueError(f"Unsupported processing mode: {mode_id}")
        return self._load_handler(config, mode.get("handler", ""))

    def compiler(self, config: dict[str, Any]):
        return self._load_handler(config, config.get("compiler_handler", ""))

    def execution(self, config: dict[str, Any]):
        return self._load_handler(config, config.get("executor_handler", ""))

    def prepare(self, config, workflow, request, media, job_id, prompt, runtime):
        import inspect
        handler = self.compiler(config)
        if handler:
            # Existing six-argument compilers remain valid; system services are opt-in.
            kwargs = {"runtime": runtime} if "runtime" in inspect.signature(handler).parameters else {}
            handler(workflow, config, request, media, job_id, prompt, **kwargs)

    def confirmation(self, config: dict[str, Any]):
        return self._load_handler(config, config.get("confirmation_handler", ""))

    def speech(self, config: dict[str, Any]):
        return self._load_handler(config, config.get("speech_handler", ""))

    def action_handler(self, action: dict[str, Any]):
        return self._load_handler(action, action.get("handler", ""))

    def availability(self, action):
        return self._load_handler(action, action.get("availability_handler", ""), verify=False)

    def assert_current(self, config):
        if self.context is not None:
            root = self.directory / config["plugin_folder"]
            if self._read(root / "plugin.json")["_plugin_revision"] != config["plugin_revision"]:
                raise ValueError("插件文件已修改，请排空任务并重启网关后重新提交")

    def resource_event(self, event, context, *, job=None, request=None, config=None):
        """Dispatch lifecycle hooks; locked delete resources become warnings."""
        from ..shared.plugin_runtime import PluginRuntime
        from ..settings.plugins import PluginSettings
        plugins, _ = self.scan()
        warnings = []
        for plugin in plugins:
            target = plugin.get("resource_lifecycle", {}).get(event)
            if not target:
                continue
            generation = (job or {}).get("generation") or ((job or {}).get("request") or {}).get("generation") or {}
            if generation.get("plugin_id") not in {None, plugin["id"]}:
                continue
            if config and config.get("plugin_id") != plugin["id"]:
                continue
            identity = dict(plugin_folder=plugin["_plugin_folder"], plugin_revision=plugin["_plugin_revision"])
            try:
                self._load_handler(identity, target)(
                    {"job": job, "request": request, "config": config},
                    PluginRuntime(plugin["id"], PluginSettings(context).runtime(plugin["id"]), context, project_id=(job or {}).get("project_id"), category_id=(job or {}).get("category_id")),
                )
            except PermissionError as exc:
                if event != "delete":
                    raise
                warning = {
                    "code": "resource_cleanup_pending",
                    "plugin_id": plugin["id"],
                    "message": "插件外部资源暂时无法删除，主数据已完成删除，请检查文件权限后手动清理",
                }
                warnings.append(warning)
                logger.warning("Plugin resource cleanup deferred: %s (%s)", plugin["id"], exc)
            except Exception:
                if event == "delete":
                    raise
                logger.exception("Plugin resource %s failed: %s", event, plugin["id"])
        return warnings

    def application_event(self, event, context, *, project_id, category_id=None, reason="user_delete"):
        """Run application data lifecycle hooks; failures abort the destructive operation."""
        from ..shared.plugin_runtime import PluginRuntime
        from ..settings.plugins import PluginSettings
        plugins, _ = self.scan()
        if event not in {"project_delete", "category_delete"}:
            raise ValueError(f"Unsupported application lifecycle event: {event}")
        payload = {"project_id": project_id, "category_id": category_id, "reason": reason}
        for plugin in plugins:
            target = plugin.get("application_lifecycle", {}).get(event)
            if not target:
                continue
            identity = dict(plugin_folder=plugin["_plugin_folder"], plugin_revision=plugin["_plugin_revision"])
            self._load_handler(identity, target)(
                payload,
                PluginRuntime(plugin["id"], PluginSettings(context).runtime(plugin["id"]), context,
                              project_id=project_id, category_id=category_id),
            )

    def _load_handler(self, config: dict[str, Any], target: str, *, verify=True):
        filename, _, symbol = target.partition(":")
        if not filename:
            return None
        root = self.directory / config["plugin_folder"]
        if verify:
            self.assert_current(config)
        path = contained_file(root, filename)
        package_name = "videofree_plugin_" + hashlib.sha256((str(root.resolve()) + config["plugin_revision"]).encode()).hexdigest()
        # Each revision is a package so plugin-local relative imports share its version.
        parts = path.relative_to(root.resolve()).with_suffix("").parts
        for depth in range(len(parts)):
            name = ".".join((package_name, *parts[:depth]))
            if name not in sys.modules:
                package = ModuleType(name)
                package.__path__ = [str(root.joinpath(*parts[:depth]).resolve())]
                package.__package__ = name
                sys.modules[name] = package
        module_name = ".".join((package_name, *parts))
        # Standard import machinery waits for concurrent imports and removes failed modules.
        module = importlib.import_module(module_name)
        handler = getattr(module, symbol)
        if not callable(handler):
            raise ValueError(f"Mode handler is not callable: {symbol}")
        return handler


def validate_parameters(config: dict[str, Any], supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise ValueError("Plugin parameters must be an object")
    definitions = config.get("parameters", {})
    unknown = set(supplied) - set(definitions)
    if unknown:
        raise ValueError(f"Unknown plugin parameters: {sorted(unknown)}")
    result = {}
    for key, definition in definitions.items():
        value = supplied.get(key, definition.get("default"))
        if value is None:
            if definition.get("required"):
                raise ValueError(f"Required plugin parameter: {key}")
            continue
        expected = definition.get("type", "string")
        valid = {"string": isinstance(value, str), "boolean": isinstance(value, bool), "integer": type(value) is int, "number": type(value) in {int, float}}.get(expected, False)
        if not valid or ("enum" in definition and value not in definition["enum"]):
            raise ValueError(f"Invalid plugin parameter: {key}")
        if expected in {"integer", "number"} and (not math.isfinite(value) or not definition.get("minimum", float("-inf")) <= value <= definition.get("maximum", float("inf"))):
            raise ValueError(f"Plugin parameter out of range: {key}")
        if isinstance(value, str) and len(value) > definition.get("maxLength", 20000):
            raise ValueError(f"Plugin parameter too long: {key}")
        result[key] = value
    return result
