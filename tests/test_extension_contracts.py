import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from backend.modules.generation.plugins import plugin_manifest_schema, validate_plugin_manifest
from backend.modules.shared.plugin_runtime import PLUGIN_RUNTIME_API_VERSION, PluginRuntime


ROOT = Path(__file__).resolve().parents[1]


class ExtensionContractTests(unittest.TestCase):
    def test_official_plugins_conform_to_the_published_manifest_schema(self):
        self.assertEqual(plugin_manifest_schema()["$schema"], "https://json-schema.org/draft/2020-12/schema")
        for path in ROOT.glob("plugins/*/plugin.json"):
            with self.subTest(plugin=path.parent.name):
                validate_plugin_manifest(json.loads(path.read_text(encoding="utf-8")))

    def test_capability_unknown_fields_are_rejected_by_the_manifest_schema(self):
        manifest = {
            "schema_version": 1, "id": "example", "version": "1.0.0", "name": "Example",
            "categories": [{"id": "image", "name": "Image"}],
            "modes": [{"id": "direct", "name": "Direct"}],
            "capabilities": {
                "example.create": {"kind": "image", "mode": "create", "category": "image", "typo": True}
            },
        }
        with self.assertRaisesRegex(ValueError, "typo"):
            validate_plugin_manifest(manifest)

    def test_plugin_runtime_v1_exposes_declared_cross_extension_calls(self):
        registry = Mock()
        registry.invoke.return_value = {"ok": True}
        context = SimpleNamespace(system_services=registry)
        runtime = PluginRuntime("example", {}, context, project_id="project-1")
        self.assertEqual(runtime.api_version, PLUGIN_RUNTIME_API_VERSION)
        self.assertEqual(runtime.call_system_service("example", "ping", {"value": 1}), {"ok": True})
        registry.invoke.assert_called_once_with(
            "example", "ping", {"value": 1}, provider_id=None, context=context,
        )
        for method in (
            "execute_action", "invoke_capability", "call_model", "call_system_service",
            "comfyui_request", "save_job_file", "job_file", "materialize_job_file",
            "link_job_file", "restore_job_file", "job_request", "jobs", "reference",
        ):
            self.assertTrue(callable(getattr(runtime, method)))


if __name__ == "__main__":
    unittest.main()
