import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from backend.integrations.system_services import LLMProviderCatalog, SystemServiceRegistry
from backend.core.errors import SystemServiceError


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ROOT / "backend" / "integrations" / "system_services" / "llm_providers"


def manifest(provider_id, entry="provider.py:Provider", **extra):
    return {
        "schema_version": 1, "service_id": "test", "contract_version": 1,
        "provider_id": provider_id, "name": provider_id.title(), "entry": entry,
        "operations": {
            "echo": {
                "input_schema": {"type": "object", "required": ["value"],
                                 "properties": {"value": {"type": "string"}},
                                 "additionalProperties": False},
                "output_schema": {"type": "object", "required": ["value"],
                                  "properties": {"value": {"type": "string"}},
                                  "additionalProperties": False},
            }
        },
        **extra,
    }


class LLMProviderTests(unittest.TestCase):
    def setUp(self):
        self.catalog = LLMProviderCatalog(PROVIDERS)
        self.settings = {
            "ai_base_url": "https://llm.example/v1",
            "ai_api_key": "secret",
            "ai_model": "gpt-5-mini",
            "ai_thinking_mode": "high",
        }

    def test_built_in_providers_are_manifest_discovered(self):
        providers = {item["id"]: item for item in self.catalog.items()}
        self.assertEqual(set(providers), {"openai", "deepseek", "custom"})
        self.assertEqual(self.catalog.errors, [])
        self.assertEqual(providers["openai"]["defaults"]["ai_model"], "gpt-4.1-mini")
        self.assertEqual(providers["deepseek"]["defaults"]["ai_base_url"], "https://api.deepseek.com/v1")

    def test_openai_provider_builds_request_and_normalizes_response(self):
        endpoint, body, headers, optional = self.catalog.get("openai").build_chat_request(
            self.settings, [{"role": "user", "content": "hello"}], 100, None, None
        )
        self.assertEqual(endpoint, "https://llm.example/v1/chat/completions")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertTrue(optional)
        result = self.catalog.get("openai").parse_chat_response({"choices": [{
            "finish_reason": "stop",
            "message": {"content": [{"text": "answer"}], "tool_calls": [], "reasoning_content": ""},
        }]})
        self.assertEqual(result, {"content": "answer", "tool_calls": [], "reasoning": "", "finish_reason": "stop"})

    def test_deepseek_and_custom_thinking_options_are_provider_owned(self):
        deepseek = self.catalog.get("deepseek")
        _, body, _, optional = deepseek.build_chat_request(
            {**self.settings, "ai_model": "deepseek-chat"}, [], 20, None, None
        )
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertTrue(optional)
        custom = self.catalog.get("custom")
        _, body, _, optional = custom.build_chat_request(self.settings, [], 20, None, None, disable_thinking=True)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertTrue(optional)

    def test_manifest_entry_cannot_escape_provider_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extension = root / "unsafe"
            extension.mkdir()
            (extension / "provider.json").write_text(json.dumps(
                manifest("unsafe", "../../outside.py:Provider")
            ), encoding="utf-8")
            catalog = SystemServiceRegistry(root)
            self.assertEqual(catalog.items(), [])
            self.assertIn("inside its service catalog", catalog.errors[0]["error"])

    def test_manifest_defaults_reject_unapproved_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "unsafe"
            provider.mkdir()
            (provider / "provider.json").write_text(json.dumps(
                manifest("unsafe", unexpected=True)
            ), encoding="utf-8")
            catalog = SystemServiceRegistry(root)
            self.assertEqual(catalog.items(), [])
            self.assertIn("unexpected", catalog.errors[0]["error"])

    def test_manifest_rejects_invalid_or_remote_operation_schemas(self):
        for invalid_schema, expected in (
            ({"type": "object", "additionalProperties": "not-a-boolean"},
             "Invalid system service operation schema"),
            ({"type": "object", "properties": {"value": {"$ref": "https://example.com/schema"}},
             "additionalProperties": False}, "only support local references"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                provider = root / "provider"
                provider.mkdir()
                data = manifest("provider", "provider/provider.py:Provider")
                data["operations"]["echo"]["input_schema"] = invalid_schema
                (provider / "provider.json").write_text(json.dumps(data), encoding="utf-8")
                (provider / "provider.py").write_text(
                    "class Provider:\n"
                    "    def __init__(self, manifest): pass\n"
                    "    def invoke(self, operation, inputs, settings, *, context): return inputs\n",
                    encoding="utf-8",
                )

                catalog = SystemServiceRegistry(root)

                self.assertFalse(catalog.contains("provider", "test"))
                self.assertIn(expected, catalog.errors[0]["error"])

    def test_manifest_rejects_secret_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "provider"
            provider.mkdir()
            data = manifest("provider", "provider/provider.py:Provider", settings={"fields": [
                {"key": "api_key", "type": "string", "secret": True, "default": "credential"},
            ]})
            (provider / "provider.json").write_text(json.dumps(data), encoding="utf-8")
            (provider / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def invoke(self, operation, inputs, settings, *, context): return inputs\n",
                encoding="utf-8",
            )

            catalog = SystemServiceRegistry(root)

            self.assertFalse(catalog.contains("provider", "test"))
            self.assertIn("cannot declare manifest defaults", catalog.errors[0]["error"])

    def test_operation_names_accept_underscore_form(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "provider"
            provider.mkdir()
            data = manifest("provider", "provider/provider.py:Provider")
            data["operations"]["list_models"] = data["operations"].pop("echo")
            (provider / "provider.json").write_text(json.dumps(data), encoding="utf-8")
            (provider / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def invoke(self, operation, inputs, settings, *, context): return {'value': 'ok'}\n",
                encoding="utf-8",
            )

            catalog = SystemServiceRegistry(root)

            self.assertEqual(catalog.invoke("test", "list_models", {"value": "input"}), {"value": "ok"})

    def test_provider_initialization_failure_is_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken"
            broken.mkdir()
            (broken / "provider.json").write_text(json.dumps(
                manifest("broken", "broken/provider.py:Provider")
            ), encoding="utf-8")
            (broken / "provider.py").write_text(
                "class Provider:\n    def __init__(self, manifest):\n        raise RuntimeError('secret')\n",
                encoding="utf-8",
            )
            healthy = root / "healthy"
            healthy.mkdir()
            (healthy / "provider.json").write_text(json.dumps(
                manifest("healthy", "healthy/provider.py:Provider")
            ), encoding="utf-8")
            (healthy / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def invoke(self, operation, inputs, settings, context=None): return inputs\n",
                encoding="utf-8",
            )

            catalog = SystemServiceRegistry(root)

            self.assertTrue(catalog.contains("healthy", "test"))
            self.assertFalse(catalog.contains("broken", "test"))
            self.assertEqual(catalog.errors[0]["error"], "Provider initialization failed: RuntimeError")

    def test_providers_of_one_service_must_share_the_same_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for provider_id, schema in (("first", "string"), ("second", "integer")):
                provider = root / provider_id
                provider.mkdir()
                data = manifest(provider_id, f"{provider_id}/provider.py:Provider")
                data["operations"]["echo"]["input_schema"]["properties"]["value"]["type"] = schema
                (provider / "provider.json").write_text(json.dumps(data), encoding="utf-8")
                (provider / "provider.py").write_text(
                    "class Provider:\n"
                    "    def __init__(self, manifest): pass\n"
                    "    def invoke(self, operation, inputs, settings, *, context): return {'value': str(inputs)}\n",
                    encoding="utf-8",
                )

            catalog = SystemServiceRegistry(root)

            self.assertEqual(len(catalog.items("test")), 1)
            self.assertIn("disagree on operation contract", catalog.errors[0]["error"])

    def test_configure_does_not_persist_environment_secret_implicitly(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"TEST_SERVICE_KEY": "env-secret"}):
            root = Path(temporary)
            provider = root / "provider"
            provider.mkdir()
            data = manifest("provider", "provider/provider.py:Provider", default=True, settings={"fields": [
                {"key": "api_key", "source": "test.provider.api_key", "environment": "TEST_SERVICE_KEY",
                 "type": "string", "secret": True, "required": True},
                {"key": "label", "source": "test.provider.label", "type": "string", "default": "old"},
            ]})
            (provider / "provider.json").write_text(json.dumps(data), encoding="utf-8")
            (provider / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def invoke(self, operation, inputs, settings, *, context): return inputs\n",
                encoding="utf-8",
            )
            db = MagicMock()
            db.settings.return_value = {}
            context = MagicMock(db=db)
            registry = SystemServiceRegistry(root)

            self.assertEqual(registry.configure("test", "provider", {"label": "new"}, context)["api_key"], "********")
            saved = db.save_settings.call_args.args[0]

            self.assertEqual(saved, {"test.provider.label": "new", "system_service.test.provider": "provider"})
            self.assertNotIn("env-secret", json.dumps(saved))

    def test_generic_registry_validates_inputs_outputs_and_hides_provider_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "example"
            provider.mkdir()
            (provider / "provider.json").write_text(json.dumps(
                manifest("example", "example/provider.py:Provider", default=True)
            ), encoding="utf-8")
            (provider / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def invoke(self, operation, inputs, settings, context=None):\n"
                "        if inputs['value'] == 'fail': raise RuntimeError('secret-token')\n"
                "        return {'value': inputs['value']}\n",
                encoding="utf-8",
            )
            catalog = SystemServiceRegistry(root)
            self.assertEqual(catalog.invoke("test", "echo", {"value": "ok"}), {"value": "ok"})
            with self.assertRaisesRegex(SystemServiceError, "invalid_input"):
                catalog.invoke("test", "echo", {})
            with self.assertRaises(SystemServiceError) as invalid:
                catalog.invoke("test", "echo", {"value": {"credential": "secret-token"}})
            self.assertNotIn("secret-token", str(invalid.exception))
            with self.assertRaisesRegex(SystemServiceError, "provider_failed") as raised:
                catalog.invoke("test", "echo", {"value": "fail"})
            self.assertNotIn("secret-token", str(raised.exception))

    def test_model_listing_rejects_malformed_success_response(self):
        response = MagicMock()
        response.__enter__().read.return_value = b'{"data": null}'
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "数据格式无效"):
                self.catalog.get("openai").list_models("https://llm.example/v1")


if __name__ == "__main__":
    unittest.main()
