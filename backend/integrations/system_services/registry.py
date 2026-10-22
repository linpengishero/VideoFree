# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Manifest-discovered JSON operations for framework system services."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, SchemaError
from referencing import Resource, Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from ...core.errors import SystemServiceError


IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
OPERATION_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "system-service-provider-v1.schema.json"


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validation_message(error) -> str:
    location = ".".join(str(part) for part in error.absolute_path)
    return f"{location}: {error.message}" if location else error.message


def _validation_diagnostic(error) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "value"
    return f"{location}: {error.validator}"


def _validate_operation_schema(schema: dict[str, Any]) -> None:
    resolver = Registry().with_resource(
        "urn:videofree:system-service-schema",
        Resource.from_contents(schema, default_specification=DRAFT202012),
    ).resolver("urn:videofree:system-service-schema")

    def check_refs(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef"} and (
                    not isinstance(item, str) or not item.startswith("#")
                ):
                    raise ValueError("System service schemas only support local references")
                if key in {"$ref", "$dynamicRef"}:
                    try:
                        resolver.lookup(item)
                    except Unresolvable as exc:
                        raise ValueError(f"Unresolved system service schema reference: {item}") from exc
                check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)

    check_refs(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid system service operation schema: {exc.message}") from exc


class SystemServiceRegistry:
    """Load independent service providers and invoke their declared JSON operations."""

    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self._providers: dict[tuple[str, str], tuple[dict[str, Any], Any]] = {}
        self.errors: list[dict[str, str]] = []
        self._load()

    def _manifest_paths(self) -> list[Path]:
        if self.directory.name.endswith("_providers"):
            return sorted(self.directory.glob("*/provider.json"))
        paths = sorted(self.directory.glob("*_providers/*/provider.json"))
        return paths or sorted(self.directory.glob("*/provider.json"))

    def _load(self) -> None:
        if not self.directory.is_dir():
            return
        validator = Draft202012Validator(_schema())
        for manifest_path in self._manifest_paths():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.absolute_path))
                if errors:
                    raise ValueError(f"Invalid system service manifest: {_validation_message(errors[0])}")
                for operation in manifest["operations"].values():
                    _validate_operation_schema(operation["input_schema"])
                    _validate_operation_schema(operation["output_schema"])
                for field in manifest.get("settings", {}).get("fields", []):
                    if field.get("secret") and field.get("default") not in (None, ""):
                        raise ValueError("Secret system service settings cannot declare manifest defaults")
                service_id = manifest["service_id"]
                provider_id = manifest["provider_id"]
                key = (service_id, provider_id)
                if key in self._providers:
                    raise ValueError(f"Duplicate system service provider: {service_id}/{provider_id}")
                existing = next((item[0] for (service, _), item in self._providers.items()
                                 if service == service_id), None)
                if existing is not None:
                    for field in ("contract_version", "selection_key", "ui_hidden"):
                        if existing.get(field) != manifest.get(field):
                            raise ValueError(
                                f"System service providers disagree on {field}: {service_id}"
                            )
                    if existing["operations"] != manifest["operations"]:
                        raise ValueError(
                            f"System service providers disagree on operation contract: {service_id}"
                        )
                    if manifest.get("default") and any(
                        loaded.get("default") for (service, _), (loaded, _) in self._providers.items()
                        if service == service_id
                    ):
                        raise ValueError(f"System service has multiple default providers: {service_id}")
                catalog_root = manifest_path.parents[1].resolve()
                filename, _, symbol = manifest["entry"].partition(":")
                module_path = (catalog_root / filename).resolve()
                if (not symbol.isidentifier() or not module_path.is_relative_to(catalog_root)
                        or not module_path.is_file() or module_path.suffix != ".py"):
                    raise ValueError("Provider entry must reference a Python class inside its service catalog")
                module_name = "videofree_system_service_" + hashlib.sha256(
                    f"{module_path}:{module_path.stat().st_mtime_ns}".encode()
                ).hexdigest()
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec is None or spec.loader is None:
                    raise ValueError("Cannot load provider entry")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                provider = getattr(module, symbol)(manifest)
                if not callable(getattr(provider, "invoke", None)):
                    raise ValueError("System service provider must implement invoke(operation, inputs, settings, *, context)")
                self._providers[key] = (manifest, provider)
            except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError, json.JSONDecodeError) as exc:
                self.errors.append({"provider": manifest_path.parent.name, "error": str(exc)})
            except Exception as exc:
                self.errors.append({
                    "provider": manifest_path.parent.name,
                    "error": f"Provider initialization failed: {type(exc).__name__}",
                })

    def services(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for (service_id, _), (manifest, _) in self._providers.items():
            service = grouped.setdefault(service_id, {
                "id": service_id,
                "contract_version": manifest["contract_version"],
                "ui_hidden": bool(manifest.get("ui_hidden")),
                "providers": [],
            })
            service["providers"].append(self._public_provider(manifest))
        for service in grouped.values():
            service["providers"].sort(key=lambda item: item["id"])
        return [grouped[key] for key in sorted(grouped)]

    @staticmethod
    def _public_provider(manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": manifest["provider_id"],
            "name": manifest["name"],
            "defaults": dict(manifest.get("defaults", {})),
            "operations": sorted(manifest["operations"]),
            "settings": {"fields": [
                {key: value for key, value in field.items()
                 if key not in {"source", "environment"}}
                for field in manifest.get("settings", {}).get("fields", [])
            ]},
        }

    # Defaulting to llm preserves the typed LLM catalog surface used by settings.
    def items(self, service_id: str = "llm") -> list[dict[str, Any]]:
        return [self._public_provider(manifest) for (service, _), (manifest, _) in self._providers.items()
                if service == service_id]

    def get(self, provider_id: str, service_id: str = "llm"):
        record = self._providers.get((str(service_id), str(provider_id)))
        if not record:
            raise ValueError(f"System service provider is unavailable: {service_id}/{provider_id}")
        return record[1]

    def contains(self, provider_id: str, service_id: str = "llm") -> bool:
        return (str(service_id), str(provider_id)) in self._providers

    def _select(self, service_id: str, provider_id: str | None, context) -> tuple[dict[str, Any], Any]:
        candidates = [(manifest, provider) for (service, _), (manifest, provider) in self._providers.items()
                      if service == service_id]
        if provider_id:
            record = self._providers.get((service_id, provider_id))
            if record:
                return record
            raise SystemServiceError(404, service_id, provider_id, "", "provider_not_found")
        if not candidates:
            raise SystemServiceError(404, service_id, "", "", "service_not_found")
        selection_key = next((item[0].get("selection_key") for item in candidates
                              if item[0].get("selection_key")), None)
        selected = context.db.settings().get(selection_key, "") if context is not None and selection_key else ""
        if selected:
            record = self._providers.get((service_id, selected))
            if record:
                return record
        defaults = [item for item in candidates if item[0].get("default")]
        if len(defaults) == 1:
            return defaults[0]
        if len(candidates) == 1:
            return candidates[0]
        raise SystemServiceError(409, service_id, "", "", "provider_not_selected")

    @staticmethod
    def _setting_source(manifest: dict[str, Any], field: dict[str, Any]) -> str:
        return field.get("source") or (
            f"system_service.{manifest['service_id']}.{manifest['provider_id']}.{field['key']}"
        )

    @classmethod
    def _settings(cls, manifest: dict[str, Any], context) -> dict[str, Any]:
        stored = context.db.settings() if context is not None else {}
        values: dict[str, Any] = {}
        for field in manifest.get("settings", {}).get("fields", []):
            value = stored.get(cls._setting_source(manifest, field))
            if value is None and field.get("environment"):
                value = os.getenv(field["environment"])
            if value is None:
                value = field.get("default")
            if value is not None:
                if field.get("type") == "boolean" and not isinstance(value, bool):
                    value = str(value).lower() == "true"
                elif field.get("type") == "number" and not isinstance(value, (int, float)):
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                values[field["key"]] = value
        return values

    def selected_configuration(self, service_id: str, context, *, reveal_secrets: bool = False) -> dict[str, Any]:
        manifest, _ = self._select(service_id, None, context)
        provider_id = manifest["provider_id"]
        return {
            "provider_id": provider_id,
            "values": self.configuration(service_id, provider_id, context, reveal_secrets=reveal_secrets),
        }

    def configuration(self, service_id: str, provider_id: str, context, *, reveal_secrets: bool = False) -> dict[str, Any]:
        record = self._providers.get((service_id, provider_id))
        if not record:
            raise SystemServiceError(404, service_id, provider_id, "", "provider_not_found")
        manifest = record[0]
        values = self._settings(manifest, context)
        if not reveal_secrets:
            for field in manifest.get("settings", {}).get("fields", []):
                if field.get("secret") and values.get(field["key"]):
                    values[field["key"]] = "********"
        return values

    def configure(self, service_id: str, provider_id: str, supplied: dict[str, Any], context) -> dict[str, Any]:
        record = self._providers.get((service_id, provider_id))
        if not record:
            raise SystemServiceError(404, service_id, provider_id, "", "provider_not_found")
        manifest = record[0]
        fields = {field["key"]: field for field in manifest.get("settings", {}).get("fields", [])}
        if not isinstance(supplied, dict) or set(supplied) - fields.keys():
            raise SystemServiceError(422, service_id, provider_id, "", "invalid_settings")
        stored: dict[str, Any] = {}
        current = self.configuration(service_id, provider_id, context, reveal_secrets=True)
        effective = {**current, **supplied}
        for key, field in fields.items():
            value = effective.get(key, field.get("default"))
            if field.get("secret") and value == "********":
                effective[key] = current.get(key, "")
        for key, value in supplied.items():
            field = fields[key]
            if field.get("secret") and value == "********":
                continue
            if field.get("required") and (value is None or str(value).strip() == ""):
                raise SystemServiceError(422, service_id, provider_id, "", "required_setting_missing", diagnostic=key)
            kind = field.get("type", "string")
            if kind == "boolean" and not isinstance(value, bool):
                if str(value).lower() not in {"true", "false"}:
                    raise SystemServiceError(422, service_id, provider_id, "", "invalid_settings", diagnostic=key)
                value = str(value).lower() == "true"
            elif kind == "number" and not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    raise SystemServiceError(422, service_id, provider_id, "", "invalid_settings", diagnostic=key) from None
            elif value is not None:
                value = str(value).strip()
            if kind == "url" and value and (urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc):
                raise SystemServiceError(422, service_id, provider_id, "", "invalid_settings", diagnostic=key)
            if kind == "select" and value not in field.get("options", []):
                raise SystemServiceError(422, service_id, provider_id, "", "invalid_settings", diagnostic=key)
            if value is not None:
                stored[self._setting_source(manifest, field)] = value
                effective[key] = value
        for key, field in fields.items():
            value = effective.get(key, field.get("default"))
            if field.get("required") and (value is None or str(value).strip() == ""):
                raise SystemServiceError(422, service_id, provider_id, "", "required_setting_missing", diagnostic=key)
        selection_key = manifest.get("selection_key") or f"system_service.{service_id}.provider"
        stored[selection_key] = provider_id
        context.db.save_settings(stored)
        return self.configuration(service_id, provider_id, context)

    def invoke(self, service_id: str, operation: str, inputs: dict[str, Any], *,
               provider_id: str | None = None, context=None) -> dict[str, Any]:
        if not IDENTIFIER.fullmatch(str(service_id)) or not OPERATION_IDENTIFIER.fullmatch(str(operation)):
            raise SystemServiceError(422, str(service_id), str(provider_id or ""), str(operation), "invalid_request")
        manifest, provider = self._select(str(service_id), provider_id, context)
        provider_id = manifest["provider_id"]
        declaration = manifest["operations"].get(operation)
        if declaration is None:
            raise SystemServiceError(404, service_id, provider_id, operation, "operation_not_found")
        if not isinstance(inputs, dict):
            raise SystemServiceError(422, service_id, provider_id, operation, "invalid_input")
        try:
            json.dumps(inputs, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise SystemServiceError(422, service_id, provider_id, operation, "invalid_input") from None
        errors = sorted(Draft202012Validator(declaration["input_schema"]).iter_errors(inputs),
                        key=lambda item: list(item.absolute_path))
        if errors:
            raise SystemServiceError(422, service_id, provider_id, operation, "invalid_input",
                                     diagnostic=_validation_diagnostic(errors[0]))
        try:
            result = provider.invoke(operation, dict(inputs), self._settings(manifest, context), context=context)
        except SystemServiceError:
            raise
        except Exception as exc:
            raise SystemServiceError(502, service_id, provider_id, operation, "provider_failed") from exc
        if not isinstance(result, dict):
            raise SystemServiceError(502, service_id, provider_id, operation, "invalid_output")
        try:
            json.dumps(result, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise SystemServiceError(502, service_id, provider_id, operation, "invalid_output") from None
        errors = sorted(Draft202012Validator(declaration["output_schema"]).iter_errors(result),
                        key=lambda item: list(item.absolute_path))
        if errors:
            raise SystemServiceError(502, service_id, provider_id, operation, "invalid_output")
        return result
