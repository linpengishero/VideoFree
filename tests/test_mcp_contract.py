import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Request

from backend.interfaces.http.mcp import _tool_definitions, _tool_result


class MCPContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_wait_stays_below_client_request_timeout(self):
        tools = {tool['name']: tool for tool in _tool_definitions()}
        self.assertEqual(tools['wait_job']['inputSchema']['properties']['timeout']['maximum'], 30)
        with patch('backend.interfaces.http.mcp._local_api', new_callable=AsyncMock) as api:
            api.return_value = {'status': 'running'}
            await _tool_result('wait_job', {'job_id': 'long-job', 'timeout': 120})
            api.assert_awaited_once_with('GET', '/api/v2/jobs/long-job/wait?timeout=30')

    def test_all_tools_have_valid_schemas_without_workspace_parameters(self):
        from jsonschema import Draft202012Validator
        tools = _tool_definitions()
        self.assertEqual(len(tools), len({tool['name'] for tool in tools}))
        for tool in tools:
            Draft202012Validator.check_schema(tool['inputSchema'])
            self.assertNotIn('workspace_id', tool['inputSchema']['properties'], tool['name'])

    async def test_management_tools_forward_to_existing_http_services(self):
        cases = [
            ('list_jobs', {'project_id': 'p1', 'status': 'queued', 'limit': 10, 'offset': 20},
             'GET', '/api/v2/jobs?project_id=p1&status=queued&limit=10&offset=20', None),
            ('list_library', {'project_id': 'p1', 'category_id': '', 'kind': 'audio'},
             'GET', '/api/v2/library?project_id=p1&kind=audio&category_id=', None),
            ('list_collaborations', {'project_id': 'p1', 'active': False},
             'GET', '/api/v2/collaborations?project_id=p1&active=false', None),
            ('cancel_collaboration', {'collaboration_id': 'c1'}, 'POST', '/api/v2/collaborations/c1/cancel', None),
            ('list_plugins', {}, 'GET', '/api/v2/plugins', None),
            ('list_plugin_presets', {'plugin_id': 'cosyvoice3'}, 'GET', '/api/v2/plugins/cosyvoice3/presets', None),
            ('create_project_category', {'project_id': 'p1', 'name': 'Episode'}, 'POST', '/v1/projects/p1/categories', {'name': 'Episode'}),
            ('update_project_category', {'project_id': 'p1', 'category_id': 'c1', 'name': 'Episode 2'},
             'PUT', '/v1/projects/p1/categories/c1', {'name': 'Episode 2'}),
            ('create_public_asset', {'project_id': 'p1', 'name': 'Hero', 'kind': 'character'},
             'POST', '/v1/projects/p1/public-assets', {'name': 'Hero', 'kind': 'character'}),
            ('update_public_asset', {'project_id': 'p1', 'asset_id': 'a1', 'name': 'Hero', 'kind': 'character'},
             'PUT', '/v1/projects/p1/public-assets/a1', {'name': 'Hero', 'kind': 'character'}),
            ('attach_public_asset_media', {'project_id': 'p1', 'asset_id': 'a1', 'source': 'upload:' + 'a' * 32},
             'POST', '/v1/projects/p1/public-assets/a1/media', {'source': 'upload:' + 'a' * 32}),
            ('update_project', {'project_id': 'p1', 'name': 'New title', 'description': 'Description'},
             'PUT', '/v1/projects/p1', {'name': 'New title', 'description': 'Description'}),
        ]
        for name, arguments, method, path, payload in cases:
            with self.subTest(name=name), patch('backend.interfaces.http.mcp._local_api', new_callable=AsyncMock) as api:
                api.return_value = {'ok': True}
                await _tool_result(name, arguments)
                if payload is None:
                    api.assert_awaited_once_with(method, path)
                else:
                    api.assert_awaited_once_with(method, path, payload)

    async def test_plugin_action_forwards_options(self):
        options = {"width": 1312, "height": 736, "upscaler": "3d", "parameters": {"strength": 0.4}}
        with patch('backend.interfaces.http.mcp._local_api', new_callable=AsyncMock) as api:
            api.side_effect = [{"automation": True}, {"job_id": "processed"}]
            await _tool_result('run_plugin_action', {
                "source_job_id": "source", "action_id": "h3_refine", "inputs": options,
            })
            self.assertEqual(api.await_count, 2)
            api.assert_awaited_with('POST', '/api/v2/plugin-actions/h3_refine/execute',
                                   {'source_job_id':'source','project_id':None,'inputs':options})

    async def test_public_asset_read_delegates_with_explicit_project(self):
        with patch('backend.interfaces.http.mcp._local_api', new_callable=AsyncMock) as api:
            api.return_value = {'items': []}
            await _tool_result('list_public_assets', {'project_id': 'project-one'})
            api.assert_awaited_once_with('GET', '/v1/projects/project-one/public-assets')

    def test_schemas_and_permissions(self):
        tools = {tool["name"]: tool for tool in _tool_definitions()}
        self.assertIn("prompt_processing", tools["submit_generation"]["inputSchema"]["properties"])
        self.assertIn("session_id", tools["submit_generation"]["inputSchema"]["properties"])
        self.assertIn("inputs", tools["run_plugin_action"]["inputSchema"]["properties"])
        self.assertFalse({'speech_preset','speech_clone','speech_describe','run_job_action'} & tools.keys())
        self.assertIn("get_job_inputs", tools)
        self.assertFalse(any(name.startswith(("delete_", "update_voice")) for name in tools))

    async def test_speech_delegates_without_confirmation(self):
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            api.side_effect = [{"automation":True}, {"job_id": "job-test"}]
            result = await _tool_result("run_plugin_action", {"action_id":"speech_preset", "inputs":{"preset_id": "warm_male", "text": "测试", "speed": 1.2}})
            api.assert_awaited_with("POST", "/api/v2/plugin-actions/speech_preset/execute", {"source_job_id":None,"project_id":None,"inputs":{"preset_id": "warm_male", "text": "测试", "speed": 1.2}})
            self.assertEqual(json.loads(result["content"][0]["text"])["job_id"], "job-test")

    async def test_generation_continuation(self):
        with patch("backend.interfaces.http.mcp._local_api_request", return_value={"status": "needs_input"}) as api:
            await _tool_result("submit_generation", {"prompt_processing": "compile", "session_id": "session-test", "answer": "第一张是主角", "project_id": "project-test"})
            payload = json.loads(api.call_args.args[2])
            self.assertEqual(payload["session_id"], "session-test")
            self.assertEqual(payload["prompt_processing"], "compile")
            self.assertEqual(payload["project_id"], "project-test")

    async def test_generation_preserves_omitted_plugin_settings(self):
        with patch("backend.interfaces.http.mcp._local_api_request", return_value={"status": "queued"}) as api:
            await _tool_result("submit_generation", {
                "capability_id": "image.gpt_image.text_to_image", "prompt": "test",
            })
            payload = json.loads(api.call_args.args[2])
            self.assertNotIn("settings", payload)

            await _tool_result("submit_generation", {
                "capability_id": "image.gpt_image.text_to_image", "prompt": "test",
                "settings": {"ratio": "1:1"},
            })
            payload = json.loads(api.call_args.args[2])
            self.assertEqual(payload["settings"], {"ratio": "1:1"})

    async def test_action_without_automation_is_not_submitted(self):
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            api.return_value = {"automation":False}
            with self.assertRaises(ValueError):
                await _tool_result("run_plugin_action", {"action_id":"settings-change", "inputs":{}})
            self.assertEqual(api.await_count, 1)

    async def test_session_answer_uses_v2_messages(self):
        with patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            api.return_value = {"id": "c1", "status": "queued"}
            result = await _tool_result("send_collaboration_message", {
                "collaboration_id": "c1", "message": "Audio 1 belongs to the main character",
            })
            api.assert_awaited_once_with("POST", "/api/v2/collaborations/c1/messages",
                                        {"message": "Audio 1 belongs to the main character"})
            self.assertEqual(json.loads(result["content"][0]["text"])["status"], "queued")

    async def test_director_creation_uses_canonical_inputs(self):
        inputs = [{"type": "image", "upload_id": "a" * 32, "role": "reference"}]
        with patch("backend.interfaces.http.mcp._registry", return_value={"sample.video": {"kind": "video"}}), \
             patch("backend.interfaces.http.mcp.public_capability", return_value={
                 "collaboration_supported": True, "model": "sample", "mode": "reference"}), \
             patch("backend.interfaces.http.mcp._local_api", new_callable=AsyncMock) as api:
            api.return_value = {"id": "c1", "status": "queued"}
            await _tool_result("create_director_collaboration", {
                "capability_id": "sample.video", "message": "Make a scene",
                "inputs": inputs, "project_id": "p1",
            })
            api.assert_awaited_once_with("POST", "/api/v2/collaborations", {
                "capability_id": "sample.video", "model_id": "sample", "mode_id": "reference",
                "message": "Make a scene", "collaboration_mode": "director", "inputs": inputs,
                "settings": {}, "project_id": "p1", "category_id": None,
            })

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
