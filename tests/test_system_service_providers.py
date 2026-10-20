import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from backend.integrations.system_services import LLMProviderCatalog


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ROOT / "backend" / "integrations" / "system_services" / "llm_providers"


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
            (extension / "provider.json").write_text(json.dumps({
                "schema_version": 1, "id": "unsafe", "name": "Unsafe",
                "entry": "../../outside.py:Provider",
            }), encoding="utf-8")
            catalog = LLMProviderCatalog(root)
            self.assertEqual(catalog.items(), [])
            self.assertIn("local Python class", catalog.errors[0]["error"])

    def test_manifest_defaults_reject_unapproved_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "unsafe"
            provider.mkdir()
            (provider / "provider.json").write_text(json.dumps({
                "schema_version": 1, "id": "unsafe", "name": "Unsafe",
                "entry": "provider.py:Provider", "defaults": {"ai_api_key": "secret"},
            }), encoding="utf-8")
            catalog = LLMProviderCatalog(root)
            self.assertEqual(catalog.items(), [])
            self.assertIn("defaults", catalog.errors[0]["error"])

    def test_provider_initialization_failure_is_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken"
            broken.mkdir()
            (broken / "provider.json").write_text(json.dumps({
                "schema_version": 1, "id": "broken", "name": "Broken",
                "entry": "broken/provider.py:Provider",
            }), encoding="utf-8")
            (broken / "provider.py").write_text(
                "class Provider:\n    def __init__(self, manifest):\n        raise RuntimeError('secret')\n",
                encoding="utf-8",
            )
            healthy = root / "healthy"
            healthy.mkdir()
            (healthy / "provider.json").write_text(json.dumps({
                "schema_version": 1, "id": "healthy", "name": "Healthy",
                "entry": "healthy/provider.py:Provider",
            }), encoding="utf-8")
            (healthy / "provider.py").write_text(
                "class Provider:\n"
                "    def __init__(self, manifest): pass\n"
                "    def build_chat_request(self, *args, **kwargs): pass\n"
                "    def parse_chat_response(self, payload): pass\n"
                "    def list_models(self, base_url, api_key=''): return []\n",
                encoding="utf-8",
            )

            catalog = LLMProviderCatalog(root)

            self.assertTrue(catalog.contains("healthy"))
            self.assertFalse(catalog.contains("broken"))
            self.assertEqual(catalog.errors[0]["error"], "Provider initialization failed: RuntimeError")

    def test_model_listing_rejects_malformed_success_response(self):
        response = MagicMock()
        response.__enter__().read.return_value = b'{"data": null}'
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "数据格式无效"):
                self.catalog.get("openai").list_models("https://llm.example/v1")


if __name__ == "__main__":
    unittest.main()
