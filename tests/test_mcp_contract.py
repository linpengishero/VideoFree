import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Request

from backend.interfaces.http.mcp import _tool_definitions, _tool_result


class MCPContractTest(unittest.IsolatedAsyncioTestCase):
    def test_schemas_and_permissions(self):
        tools = {tool["name"]: tool for tool in _tool_definitions()}
        self.assertIn("prompt_processing", tools["submit_generation"]["inputSchema"]["properties"])
        self.assertIn("session_id", tools["submit_generation"]["inputSchema"]["properties"])
        self.assertIn("speed", tools["speech_clone"]["inputSchema"]["properties"])
        self.assertIn("get_job_inputs", tools)
        self.assertFalse(any(name.startswith(("delete_", "update_voice")) for name in tools))

    async def test_speech_delegates_without_confirmation(self):
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            api.return_value = {"job_id": "job-test"}
            result = await _tool_result("speech_preset", {"preset_id": "warm_male", "text": "测试", "speed": 1.2, "workspace_id": "agent-a"})
            api.assert_awaited_once_with("POST", "/api/v2/tts/preset", {"preset_id": "warm_male", "text": "测试", "speed": 1.2}, "agent-a")
            self.assertEqual(json.loads(result["content"][0]["text"])["job_id"], "job-test")

    async def test_generation_continuation(self):
        with patch("backend.interfaces.http.mcp._local_api_request", return_value={"status": "needs_input"}) as api:
            await _tool_result("submit_generation", {"prompt_processing": "compile", "session_id": "session-test", "answer": "第一张是主角", "project_id": "project-test"})
            payload = json.loads(api.call_args.args[2])
            self.assertEqual(payload["session_id"], "session-test")
            self.assertEqual(payload["prompt_processing"], "compile")
            self.assertEqual(payload["project_id"], "project-test")

    async def test_bad_speed_rejected_before_submission(self):
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            with self.assertRaises(ValueError):
                await _tool_result("speech_describe", {"voice_description": "男声", "text": "你好", "speed": 3})
            api.assert_not_awaited()

    async def test_canonical_collaboration_receipt(self):
        canonical = {"id": "c1", "model_id": "minimax-h3", "collaboration_mode": "quick",
                     "confirmation": {"execution_prompt_en": "English"}, "revision": 2}
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api, \
             patch("backend.interfaces.http.mcp.context.db.collaboration", return_value={"result": {"optimized_prompt": "English"}}):
            api.return_value = canonical
            result = await _tool_result("get_collaboration", {"collaboration_id": "c1"})
            receipt = json.loads(result["content"][0]["text"])
            self.assertEqual(receipt["confirmation"], canonical["confirmation"])
            self.assertEqual(receipt["result"]["optimized_prompt"], "English")

    async def test_confirmation_preserves_idempotency_body(self):
        with patch("backend.interfaces.http.mcp._local_api_request", return_value={"job_id": "j1"}) as api:
            await _tool_result("confirm_collaboration", {"collaboration_id": "c1", "revision": 2, "idempotency_key": "confirm-1"})
            self.assertEqual(json.loads(api.call_args.args[2])["idempotency_key"], "confirm-1")

    async def test_mcp_invalid_json_is_client_error(self):
        from backend.interfaces.http.mcp import build_router

        route = next(route for route in build_router().routes if route.path == "/mcp" and "POST" in route.methods)
        request = Request({
            "type": "http", "method": "POST", "path": "/mcp",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"", "scheme": "http", "server": ("test", 80),
            "client": ("test", 1), "root_path": "",
            "app": None, "router": None, "endpoint": None,
        }, receive=lambda: None)
        request._body = b"{'jsonrpc': '2.0'}"
        response = await route.endpoint(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"]["code"], -32700)
