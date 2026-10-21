# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Discovery and execution contract for trusted infinite-canvas node packages."""

import asyncio
import copy
import hashlib
import importlib
import inspect
import json
import logging
from pathlib import Path
import re
import stat
import sys
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator
from referencing.exceptions import Unresolvable

from ...core.errors import GatewayError
from .plugins import contained_file, validate_plugin_json_schema

logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")
NODE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
PORT_TYPES = {"text", "number", "integer", "boolean", "json", "upload", "asset", "image", "video", "audio", "music", "media", "project", "category"}
MEDIA_SUFFIXES = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "video": {".mp4", ".mov", ".webm", ".mkv"},
    "audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a"},
}
MEDIA_SUFFIXES["music"] = MEDIA_SUFFIXES["audio"]


def _port_schema(port: dict[str, Any]) -> dict[str, Any]:
    kind = port["type"]
    if kind == "text":
        schema: dict[str, Any] = {"type": "string"}
    elif kind == "number":
        schema = {"type": "number"}
    elif kind == "integer":
        schema = {"type": "integer"}
    elif kind == "boolean":
        schema = {"type": "boolean"}
    elif kind == "json":
        schema = {}
    elif kind == "upload":
        schema = {
            "type": "object",
            "required": ["upload_id"],
            "properties": {
                "upload_id": {"type": "string", "pattern": "^[a-fA-F0-9]{32}$"},
                "name": {"type": "string", "maxLength": 255},
                "kind": {"type": "string", "enum": ["image", "video", "audio", "music"]},
            },
            "additionalProperties": False,
        }
    elif kind == "project":
        schema = {"type": "string", "minLength": 1}
    elif kind == "category":
        schema = {"type": "string"}
    else:
        media_types = ([kind] if kind in {"image", "video"} else ["audio", "music"] if kind == "audio"
                       else ["music"] if kind == "music" else list(MEDIA_SUFFIXES))
        schema = {
            "type": "object",
            "required": ["project_id", "path", "type"],
            "properties": {
                "project_id": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1},
                "type": {"type": "string", "enum": media_types},
                "name": {"type": "string"},
                "category_id": {"type": "string"},
                "media_type": {"type": "string"},
                "size": {"type": "integer", "minimum": 0},
                "modified": {"type": "number"},
                "url": {"type": "string"},
            },
            "additionalProperties": False,
        }
    return {"type": "array", "items": schema} if port.get("multiple") else schema


def _ports_schema(ports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {port["id"]: _port_schema(port) for port in ports},
        "required": [port["id"] for port in ports if port.get("required", False)],
        "additionalProperties": False,
    }


def _validate_value(schema: dict[str, Any], value: Any, label: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        error = next(Draft202012Validator(schema).iter_errors(value), None)
    except (TypeError, ValueError, Unresolvable) as exc:
        raise GatewayError(422, f"{label} 不是有效的 JSON 值") from exc
    if error:
        path = ".".join(str(part) for part in error.absolute_path) or label
        raise GatewayError(422, f"{path}: {error.message}")


def _is_link_or_reparse(path: Path) -> bool:
    """Detect links and Windows reparse points without following them."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _reject_package_links(root: Path) -> None:
    """Reject package links so handlers and revision hashing share one file tree."""
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            if _is_link_or_reparse(path):
                raise ValueError("Canvas node packages cannot contain symbolic links or reparse points")
            if path.is_dir():
                pending.append(path)


class CanvasNodeCatalog:
    """Loads nodes from plugins/canvas-nodes without exposing them as regular plugins."""

    def __init__(self, plugins_directory: Path, context=None):
        self.directory = (Path(plugins_directory).resolve() / "canvas-nodes")
        self.context = context

    def scan(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        if self.context is None or not hasattr(self.context, "plugin_catalogs"):
            return self._scan()
        key = f"canvas-nodes:{self.directory}"
        with self.context.plugin_catalog_lock:
            if key not in self.context.plugin_catalogs:
                self.context.plugin_catalogs[key] = self._scan()
            return copy.deepcopy(self.context.plugin_catalogs[key])

    def _scan(self) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        nodes: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        ids: set[str] = set()
        if not self.directory.is_dir():
            return nodes, errors
        if _is_link_or_reparse(self.directory):
            message = "Canvas node directory cannot be a symbolic link or reparse point"
            logger.warning("Canvas node directory disabled: %s", message)
            return nodes, [{"plugin": "canvas-nodes", "error": message}]
        package_ids: set[str] = set()
        for manifest in sorted(self.directory.glob("*/plugin.json")):
            try:
                package_nodes = self._read(manifest)
                package_id = package_nodes[0]["plugin_id"] if package_nodes else None
                if package_id and package_id in package_ids:
                    raise ValueError(f"Duplicate canvas node package id: {package_id}")
                duplicates = ids.intersection(item["type"] for item in package_nodes)
                if duplicates:
                    raise ValueError(f"Duplicate canvas node types: {sorted(duplicates)}")
                if package_id:
                    package_ids.add(package_id)
                ids.update(item["type"] for item in package_nodes)
                nodes.extend(package_nodes)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                errors.append({"plugin": manifest.parent.name, "error": str(exc)})
                logger.warning("Canvas node package %s disabled: %s", manifest.parent.name, exc)
        return nodes, errors

    def _read(self, manifest: Path) -> list[dict[str, Any]]:
        package_path = manifest.parent
        if _is_link_or_reparse(package_path):
            raise ValueError("Canvas node package directory cannot be a symbolic link or reparse point")
        base = self.directory.resolve()
        root = package_path.resolve()
        if root.parent != base:
            raise ValueError("Canvas node package must stay inside plugins/canvas-nodes")
        _reject_package_links(root)
        value = json.loads(contained_file(root, "plugin.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("Unsupported canvas node package schema_version")
        if value.get("plugin_type") != "canvas_node":
            raise ValueError("plugin_type must be canvas_node")
        if value.get("enabled", True) is not True:
            return []
        for field in ("id", "version"):
            if not isinstance(value.get(field), str) or not IDENTIFIER.fullmatch(value[field]):
                raise ValueError(f"Invalid canvas node package {field}")
        if value["id"] != root.name:
            raise ValueError("Canvas node package id must match its directory name")
        if not isinstance(value.get("name"), str) or not value["name"].strip():
            raise ValueError("Canvas node package requires a name")
        contained_file(root, "INSTALL.md")
        declared_assets = value.get("assets", [])
        if not isinstance(declared_assets, list) or any(not isinstance(item, str) for item in declared_assets):
            raise ValueError("Canvas node assets must be a list of local file paths")
        for filename in declared_assets:
            contained_file(root, filename)
        declared_nodes = value.get("nodes")
        if not isinstance(declared_nodes, list) or not declared_nodes:
            raise ValueError("Canvas node package requires a non-empty nodes list")

        revision = hashlib.sha256()
        for file in sorted(root.rglob("*")):
            if file.is_file() and not file.is_symlink() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                revision.update(file.relative_to(root).as_posix().encode() + b"\0")
                revision.update(hashlib.sha256(file.read_bytes()).digest())
        revision_hex = revision.hexdigest()

        result = []
        local_ids: set[str] = set()
        for node in declared_nodes:
            if not isinstance(node, dict):
                raise ValueError("Canvas node declaration must be an object")
            node_id = node.get("id")
            if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id) or node_id in local_ids:
                raise ValueError("Invalid or duplicate canvas node id")
            local_ids.add(node_id)
            for field in ("name", "category", "handler"):
                if not isinstance(node.get(field), str) or not node[field].strip():
                    raise ValueError(f"Canvas node {node_id} requires {field}")
            if not IDENTIFIER.fullmatch(node["category"]):
                raise ValueError(f"Invalid canvas node category: {node_id}")
            if "description" in node and not isinstance(node["description"], str):
                raise ValueError("Canvas node description must be a string")
            ports_by_direction = {}
            for direction in ("inputs", "outputs"):
                ports = node.get(direction, [])
                if not isinstance(ports, list):
                    raise ValueError(f"Canvas node {direction} must be a list")
                port_ids: set[str] = set()
                for port in ports:
                    if (not isinstance(port, dict) or set(port) - {"id", "name", "type", "description", "required", "multiple"}
                            or not isinstance(port.get("id"), str) or not NODE_ID.fullmatch(port["id"])
                            or port["id"] in port_ids or not isinstance(port.get("name"), str)
                            or not port["name"].strip() or port.get("type") not in PORT_TYPES):
                        raise ValueError(f"Invalid {direction} port in canvas node {node_id}")
                    for boolean_field in ("required", "multiple"):
                        if boolean_field in port and type(port[boolean_field]) is not bool:
                            raise ValueError(f"Canvas node port {boolean_field} must be boolean")
                    if "description" in port and not isinstance(port["description"], str):
                        raise ValueError("Canvas node port description must be a string")
                    if direction == "outputs" and port.get("multiple"):
                        raise ValueError("Canvas node outputs cannot declare multiple values")
                    if direction == "outputs" and port["type"] == "upload":
                        raise ValueError("Canvas node outputs cannot expose temporary uploads")
                    if port.get("multiple") and port["type"] in {"project", "category"}:
                        raise ValueError("Canvas node project/category ports cannot be multiple")
                    port_ids.add(port["id"])
                ports_by_direction[direction] = ports
            config_schema = node.get("config_schema", {"type": "object", "properties": {}, "additionalProperties": False})
            if not isinstance(config_schema, dict) or config_schema.get("type") != "object":
                raise ValueError(f"Canvas node {node_id} config_schema must describe an object")
            validate_plugin_json_schema(config_schema, "canvas node config")
            filename, separator, symbol = node["handler"].partition(":")
            if not separator or not symbol.isidentifier() or contained_file(root, filename).suffix != ".py":
                raise ValueError(f"Canvas node handler must be a local Python file:function: {node_id}")
            icon = node.get("icon")
            if icon is not None:
                if not isinstance(icon, str) or not icon.strip():
                    raise ValueError(f"Invalid canvas node icon: {node_id}")
                if not icon.startswith(("solar:", "mdi:", "lucide:")):
                    contained_file(root, icon)
            result.append({
                "type": f"{value['id']}.{node_id}", "id": node_id,
                "plugin_id": value["id"], "plugin_name": value["name"],
                "plugin_version": value["version"], "plugin_folder": root.name,
                "plugin_revision": revision_hex, "name": node["name"],
                "description": node.get("description", ""), "category": node["category"],
                "icon": icon, "inputs": copy.deepcopy(ports_by_direction["inputs"]),
                "outputs": copy.deepcopy(ports_by_direction["outputs"]),
                "config_schema": copy.deepcopy(config_schema), "handler": node["handler"],
            })
        return result

    def nodes(self) -> dict[str, dict[str, Any]]:
        nodes, _ = self.scan()
        return {node["type"]: node for node in nodes}

    def public(self) -> dict[str, Any]:
        nodes, errors = self.scan()
        private = {"handler", "plugin_folder", "plugin_revision", "config_schema"}
        return {"items": [{key: value for key, value in node.items() if key not in private}
                          | {"config_schema": node["config_schema"]} for node in nodes],
                "errors": [{"plugin": item["plugin"], "error": "节点包清单或声明无效，详情请检查网关日志"}
                           for item in errors]}

    def _load_handler(self, node: dict[str, Any]):
        try:
            current = self._read(self.directory / node["plugin_folder"] / "plugin.json")
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise GatewayError(409, "画布节点插件文件已修改，请排空画布任务并重启网关",
                               headers={"X-Plugin-Restart-Required": "true"}) from exc
        current_revision = next((item["plugin_revision"] for item in current if item["type"] == node["type"]), None)
        if current_revision != node["plugin_revision"]:
            raise GatewayError(409, "画布节点插件文件已修改，请排空画布任务并重启网关", headers={"X-Plugin-Restart-Required": "true"})
        root = self.directory / node["plugin_folder"]
        filename, _, symbol = node["handler"].partition(":")
        path = contained_file(root, filename)
        package_name = "videofree_canvas_node_" + hashlib.sha256(
            (str(root.resolve()) + node["plugin_revision"]).encode()
        ).hexdigest()
        parts = path.relative_to(root.resolve()).with_suffix("").parts
        for depth in range(len(parts)):
            name = ".".join((package_name, *parts[:depth]))
            if name not in sys.modules:
                package = ModuleType(name)
                package.__path__ = [str(root.joinpath(*parts[:depth]).resolve())]
                package.__package__ = name
                sys.modules[name] = package
        module = importlib.import_module(".".join((package_name, *parts)))
        handler = getattr(module, symbol, None)
        if not callable(handler):
            raise ValueError(f"Canvas node handler is not callable: {symbol}")
        return handler

    async def execute(self, node_type: str, inputs: dict[str, Any], config: dict[str, Any], runtime):
        node = self.nodes().get(node_type)
        if not node:
            raise GatewayError(404, f"画布节点不存在: {node_type}")
        input_schema = _ports_schema(node["inputs"])
        _validate_value(input_schema, inputs, "inputs")
        _validate_value(node["config_schema"], config, "config")
        for port in node["inputs"]:
            if port["type"] == "upload" and port["id"] in inputs:
                values = inputs[port["id"]] if port.get("multiple") else [inputs[port["id"]]]
                for upload in values:
                    if not runtime.application.upload_exists(upload["upload_id"]):
                        raise GatewayError(422, "画布上传素材不存在或已过期")
            elif port["type"] in {"project", "category"} and port["id"] in inputs:
                self._validate_context_reference(inputs[port["id"]], port["type"], runtime)
            elif port["type"] in {"asset", "image", "video", "audio", "music", "media"} and port["id"] in inputs:
                values = inputs[port["id"]] if port.get("multiple") else [inputs[port["id"]]]
                for asset in values:
                    self._validate_asset(asset, port["type"], runtime)
        try:
            handler = self._load_handler(node)
            if inspect.iscoroutinefunction(handler):
                result = await handler(inputs, config, runtime)
            else:
                result = await asyncio.to_thread(handler, inputs, config, runtime)
                if inspect.isawaitable(result):
                    result = await result
        except GatewayError:
            raise
        except ValueError as exc:
            raise GatewayError(422, str(exc)) from exc
        except RuntimeError as exc:
            raise GatewayError(409, str(exc)) from exc
        except Exception as exc:
            logger.exception("Canvas node %s failed", node_type)
            raise GatewayError(502, "画布节点执行失败，请检查网关日志") from exc
        if not isinstance(result, dict):
            raise GatewayError(502, "画布节点必须返回包含输出端口的 JSON 对象")
        _validate_value(_ports_schema(node["outputs"]), result, "outputs")
        for port in node["outputs"]:
            if port["type"] in {"project", "category"} and port["id"] in result:
                self._validate_context_reference(result[port["id"]], port["type"], runtime)
            elif port["type"] in {"asset", "image", "video", "audio", "music", "media"} and port["id"] in result:
                self._validate_asset(result[port["id"]], port["type"], runtime)
        return result

    @staticmethod
    def _validate_context_reference(value: str, port_type: str, runtime) -> None:
        project_id = getattr(runtime, "project_id", None)
        if not project_id:
            raise GatewayError(422, "画布节点需要项目上下文")
        if port_type == "project":
            if value != project_id:
                raise GatewayError(422, "画布节点不能引用其他项目")
            return
        try:
            categories = runtime.application.categories(project_id)
        except ValueError as exc:
            raise GatewayError(422, "画布分类不存在或不属于当前项目") from exc
        if not any(item.get("id") == value for item in categories):
            raise GatewayError(422, "画布分类不存在或不属于当前项目")

    @staticmethod
    def _validate_asset(value: dict[str, Any], port_type: str, runtime) -> None:
        project_id = getattr(runtime, "project_id", None)
        if not project_id or value.get("project_id") != project_id:
            raise GatewayError(422, "画布素材必须属于当前项目")
        media_type = value.get("type")
        if media_type not in MEDIA_SUFFIXES:
            raise GatewayError(422, "画布素材类型无效")
        if port_type in {"image", "video", "music"} and media_type != port_type:
            raise GatewayError(422, "画布素材类型与输入端口不匹配")
        if port_type == "audio" and media_type not in {"audio", "music"}:
            raise GatewayError(422, "画布素材类型与输入端口不匹配")
        relative_parts = Path(value["path"].replace("\\", "/")).parts
        if any(part.rstrip(" .").casefold() == ".internal" for part in relative_parts):
            raise GatewayError(422, "画布节点不能访问内部任务文件")
        suffixes = MEDIA_SUFFIXES[media_type]
        try:
            runtime.application.resolve_library_path(project_id, value["path"], allowed_suffixes=suffixes)
        except (ValueError, OSError) as exc:
            raise GatewayError(422, "画布素材不存在或不属于当前项目") from exc
