"""Small MCP-over-HTTP adapter for LAN AI clients.

The adapter exposes discovery, generation, speech and post-processing tools.
It delegates state and validation to the existing v2 API
services instead of reading workflows or calling ComfyUI directly.
"""

import json
import base64
import asyncio
import mimetypes
import urllib.error
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ...bootstrap import context
from ...modules.generation.service import workflow_registry
from ...modules.shared.schemas import AgentChatRequest
from .v1_collaboration import enqueue_agent_collaboration
from .v2_capabilities import capability as public_capability
from .dependencies import auth
from .v2_schemas import CreateRequest, PresetSpeechRequest, DescribedSpeechRequest, ClonedSpeechRequest, RegenerateRequest


MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_INFO = {"name": "zizai-media-gateway", "version": "1.1.0"}


def _jsonrpc(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response


def _text(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}]}


def _local_api_url(path: str) -> str:
    return f"http://127.0.0.1:{context.config.port}{path}"


def _local_api_request(method: str, path: str, body: bytes | None = None, content_type: str = "application/json", idempotency_key: str = "", workspace_id: str = "mcp-default") -> Any:
    headers = {"Accept": "application/json"}
    if context.config.api_token:
        headers["X-API-Token"] = context.config.api_token
    if body is not None:
        headers["Content-Type"] = content_type
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    headers["X-Workspace-Id"] = workspace_id or "mcp-default"
    request = urllib.request.Request(_local_api_url(path), data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=135 if "/wait?" in path else 30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"网关请求失败 ({exc.code}): {detail}") from exc


async def _local_api(method: str, path: str, value: Any = None, workspace_id: str = "mcp-default") -> Any:
    body = json.dumps(value, ensure_ascii=False).encode("utf-8") if value is not None else None
    return await asyncio.to_thread(_local_api_request, method, path, body, "application/json", "", workspace_id)


def _registry() -> dict[str, dict[str, Any]]:
    workflows_path = context.paths.workflows
    values = {}
    for key, value in workflow_registry().items():
        if value.get("executor", "comfyui") != "comfyui" or (workflows_path / value.get("file", "")).is_file():
            values[key] = value
    for hidden in ("image.text_to_image", "image.image_to_image", "image.character", "tts.clone"):
        values.pop(hidden, None)
    return values


def _capabilities(kind: str | None = None) -> list[dict[str, Any]]:
    result = []
    for key, config in _registry().items():
        if kind and config.get("kind") != kind:
            continue
        result.append(public_capability(key, config))
    return result


def _tool_definitions() -> list[dict[str, Any]]:
    tools = [
        {
            "name": "list_projects",
            "description": "列出 videofree 中的项目。生成前可先选择当前项目。",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "create_project",
            "description": "创建项目并返回 project_id。后续生成请显式携带该 project_id；不会改变工作台当前项目。",
            "inputSchema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "content_summary": {"type": "string"}, "workspace_id": {"type": "string"}}},
        },
        {
            "name": "get_current_project",
            "description": "读取当前 MCP 工作区选择的项目。",
            "inputSchema": {"type": "object", "properties": {"workspace_id": {"type": "string"}}},
        },
        {
            "name": "set_current_project",
            "description": "切换当前 MCP 工作区项目；后续导演协作与生成自动进入该项目。",
            "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "workspace_id": {"type": "string"}}},
        },
        {
            "name": "list_capabilities",
            "description": "发现网关当前支持的媒体生成和导演协作能力。",
            "inputSchema": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["image", "video", "audio", "tts", "music"]}}},
        },
        {
            "name": "get_capability",
            "description": "查询一个能力的完整输入限制、参考素材角色和协作模式。",
            "inputSchema": {"type": "object", "required": ["capability_id"], "properties": {"capability_id": {"type": "string"}}},
        },
        {
            "name": "create_director_collaboration",
            "description": "把普通创作需求交给导演协作管线，返回协作任务 ID；不会自动提交视频。",
            "inputSchema": {
                "type": "object", "required": ["capability_id", "model_id", "mode_id", "message"],
                "properties": {
                    "capability_id": {"type": "string"}, "model_id": {"type": "string"}, "mode_id": {"type": "string"},
                    "message": {"type": "string"}, "collaboration_mode": {"type": "string", "enum": ["quick", "director"]},
                    "references": {"type": "array", "items": {"type": "object"}}, "settings": {"type": "object"},
                    "project_id": {"type": "string", "description": "可选；省略时使用当前工作区激活项目"},
                },
            },
        },
        {
            "name": "get_collaboration",
            "description": "读取导演协作当前状态、问题、确认稿和进度。",
            "inputSchema": {"type": "object", "required": ["collaboration_id"], "properties": {"collaboration_id": {"type": "string"}}},
        },
        {
            "name": "send_collaboration_message",
            "description": "向现有导演协作任务补充信息或回答追问。",
            "inputSchema": {"type": "object", "required": ["collaboration_id", "message"], "properties": {"collaboration_id": {"type": "string"}, "message": {"type": "string"}}},
        },
        {
            "name": "get_final_prompt",
            "description": "取得导演协作生成的最终英文执行稿和中文确认稿，不提交生成。",
            "inputSchema": {"type": "object", "required": ["collaboration_id"], "properties": {"collaboration_id": {"type": "string"}}},
        },
        {
            "name": "confirm_collaboration",
            "description": "审核通过后确认当前版本并提交。默认必须取得用户明确确认；只有用户明确委托特定镜头的审核及确认时可按授权执行，禁止通用自动确认。",
            "inputSchema": {"type": "object", "required": ["collaboration_id", "revision"], "properties": {"collaboration_id": {"type": "string"}, "revision": {"type": "integer"}, "execution_prompt_en": {"type": "string"}, "confirmed_prompt_zh": {"type": "string"}, "idempotency_key": {"type": "string"}}},
        },
        {
            "name": "upload_reference",
            "description": "上传一个 Base64 素材并返回可复用的 upload_id。",
            "inputSchema": {"type": "object", "required": ["filename", "data_base64"], "properties": {"filename": {"type": "string"}, "data_base64": {"type": "string"}, "media_type": {"type": "string"}}},
        },
        {
            "name": "submit_generation",
            "description": "提交已确认的图片、视频、音频或语音生成任务，返回 job_id；会产生实际生成任务。",
            "inputSchema": {"type": "object", "required": ["capability_id", "prompt"], "properties": {"capability_id": {"type": "string"}, "prompt": {"type": "string"}, "lyrics": {"type": "string"}, "inputs": {"type": "array", "items": {"type": "object"}}, "settings": {"type": "object"}, "project_id": {"type": "string", "description": "可选；省略时使用当前工作区激活项目"}, "idempotency_key": {"type": "string"}}},
        },
        {
            "name": "get_job",
            "description": "查询任务状态以及已完成任务的产物 URL。",
            "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
        },
        {
            "name": "wait_job",
            "description": "等待任务一段时间并返回最新状态；超时只表示仍在运行，不会取消任务。",
            "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}, "timeout": {"type": "integer", "minimum": 1, "maximum": 120}}},
        },
        {
            "name": "get_job_artifacts",
            "description": "获取任务的全部媒体产物和下载 URL。",
            "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
        },
        {
            "name": "get_job_inputs",
            "description": "只读查询实际保存的任务参考素材、upload_id和SHA256，用于验证生成确实使用了参考。",
            "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
        },
        {
            "name": "cancel_job",
            "description": "取消仍在排队或运行中的任务。",
            "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
        },
    ]
    submission = next(tool for tool in tools if tool["name"] == "submit_generation")
    submission["description"] = "统一生成入口：direct 直接提交，compile 转换描述词，director 导演协作；追问用 session_id 和 answer 回答。不自动确认。"
    submission["inputSchema"] = CreateRequest.model_json_schema()
    submission["inputSchema"]["properties"].update({"workspace_id": {"type": "string"}, "idempotency_key": {"type": "string"}})
    for name, description, model in (
        ("speech_preset", "选择 ready=true 的预设音色生成语音，服务端使用 CosyVoice3；直接返回生成任务。", PresetSpeechRequest),
        ("speech_describe", "按声音描述生成语音，服务端使用 Qwen3-TTS；直接返回生成任务。", DescribedSpeechRequest),
        ("speech_clone", "用已上传的参考音频克隆音色，服务端使用 CosyVoice3；直接返回生成任务。", ClonedSpeechRequest),
        ("regenerate_job", "重新生成任务，保留原始任务；修改双语稿时必须同时传入中英文。", RegenerateRequest),
    ):
        schema = model.model_json_schema()
        schema["properties"]["workspace_id"] = {"type": "string"}
        if name == "regenerate_job":
            schema["properties"]["job_id"] = {"type": "string"}
            schema["required"] = ["job_id"]
        tools.append({"name": name, "description": description + " 语速 speed=0.5–2.0；普通中文约4–5字/秒。" if name.startswith("speech_") else description, "inputSchema": schema})
    for name, description in (
        ("get_health", "查询网关与生成服务状态。"),
        ("list_voices", "只读查询预设音色与 ready 状态，不允许修改预设。"),
        ("list_image_styles", "只读查询图片风格。"),
        ("list_music_styles", "只读查询音乐风格。"),
        ("list_music_singers", "只读查询歌手预设。"),
        ("list_music_voice_textures", "只读查询音乐音色。"),
    ):
        tools.append({"name": name, "description": description, "inputSchema": {"type": "object", "properties": {}}})
    tools.extend([
        {"name": "get_job_actions", "description": "查询任务支持的后处理操作。", "inputSchema": {"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}}},
        {"name": "run_job_action", "description": "执行任务已公布的后处理操作，返回新任务。", "inputSchema": {"type": "object", "required": ["job_id", "action_id"], "properties": {"job_id": {"type": "string"}, "action_id": {"type": "string"}}}},
    ])
    return tools


async def _tool_result(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace_id = str(arguments.get("workspace_id") or "mcp-default")
    read_paths = {"get_health": "/health", "list_voices": "/voices", "list_image_styles": "/image/styles", "list_music_styles": "/music/styles", "list_music_singers": "/music/singers", "list_music_voice_textures": "/music/voice-textures"}
    if name in read_paths:
        return _text(await _local_api("GET", "/api/v2" + read_paths[name], workspace_id=workspace_id))
    speech = {"speech_preset": ("preset", PresetSpeechRequest), "speech_describe": ("describe", DescribedSpeechRequest), "speech_clone": ("clone", ClonedSpeechRequest)}
    if name in speech:
        endpoint, model = speech[name]
        payload = model.model_validate(arguments).model_dump(mode="json")
        return _text(await _local_api("POST", f"/api/v2/tts/{endpoint}", payload, workspace_id))
    if name == "regenerate_job":
        payload = RegenerateRequest.model_validate(arguments).model_dump(mode="json", exclude_unset=True)
        return _text(await _local_api("POST", f"/api/v2/jobs/{arguments['job_id']}/regenerate", payload, workspace_id))
    if name in {"get_job_actions", "run_job_action"}:
        path = f"/api/v2/jobs/{arguments['job_id']}/actions"
        if name == "run_job_action":
            path += f"/{arguments['action_id']}"
        return _text(await _local_api("POST" if name == "run_job_action" else "GET", path, workspace_id=workspace_id))
    if name == "list_projects":
        return _text(await _local_api("GET", "/api/v2/projects", workspace_id=workspace_id))
    if name == "create_project":
        payload = {"name": str(arguments.get("name", "")), "description": str(arguments.get("description", "")), "content_summary": str(arguments.get("content_summary", ""))}
        return _text(await _local_api("POST", "/api/v2/projects", payload, workspace_id))
    if name == "get_current_project":
        return _text(await _local_api("GET", "/api/v2/projects/current", workspace_id=workspace_id))
    if name == "set_current_project":
        return _text(await _local_api("PUT", "/api/v2/projects/current", {"project_id": str(arguments.get("project_id", ""))}, workspace_id))
    if name == "list_capabilities":
        return _text(_capabilities(arguments.get("kind")))
    if name == "get_capability":
        capability_id = str(arguments.get("capability_id", ""))
        config = _registry().get(capability_id)
        if not config:
            raise ValueError(f"能力不存在: {capability_id}")
        return _text(public_capability(capability_id, config))
    if name == "get_collaboration" or name == "get_final_prompt":
        if name == "get_collaboration":
            value = await _local_api("GET", f"/api/v2/collaborations/{arguments.get('collaboration_id', '')}", workspace_id=workspace_id)
            # Retain result/progress for existing MCP consumers; canonical fields come from HTTP.
            item = context.db.collaboration(str(arguments.get("collaboration_id", "")))
            if item:
                value.update(result=item.get("result", {}), progress=item.get("progress", {}))
            return _text(value)
        item = context.db.collaboration(str(arguments.get("collaboration_id", "")))
        if not item:
            raise ValueError("协作任务不存在")
        result = item.get("result", {}) if isinstance(item.get("result"), dict) else {}
        if name == "get_final_prompt":
            return _text({"id": item["id"], "status": item["status"], "revision": item.get("revision", 0), "execution_prompt_en": result.get("optimized_prompt", ""), "confirmed_prompt_zh": result.get("optimized_prompt_zh", ""), "review": result.get("review", {})})
        return _text({"id": item["id"], "status": item["status"], "result": result, "progress": item.get("progress", {}), "revision": item.get("revision", 0)})
    if name == "create_director_collaboration":
        capability_id = str(arguments.get("capability_id", ""))
        capability_config = _registry().get(capability_id)
        if not capability_config:
            raise ValueError(f"能力不存在: {capability_id}")
        capability_view = public_capability(capability_id, capability_config)
        if not capability_view.get("collaboration_supported"):
            raise ValueError(f"能力不支持导演协作: {capability_id}")
        parts = capability_id.split(".")
        if len(parts) < 3:
            raise ValueError(f"无效的能力 ID: {capability_id}")
        model_id = str(arguments.get("model_id") or parts[1])
        mode_id = str(arguments.get("mode_id") or parts[2])
        request = AgentChatRequest(
            message=str(arguments.get("message", "")),
            kind=str(capability_config.get("kind", "video")),
            model=model_id,
            mode=mode_id,
            collaboration_mode=str(arguments.get("collaboration_mode", "director")),
            duration_seconds=float((arguments.get("settings") or {}).get("duration", 5)),
            ratio=str((arguments.get("settings") or {}).get("ratio", "16:9")),
            resolution=int(str((arguments.get("settings") or {}).get("resolution", "720P")).replace("P", "") or 720),
            references=arguments.get("references") or [],
            params=arguments.get("settings") or {},
            review_mode="external",
            client_request_id=f"mcp-{uuid.uuid4().hex}",
            project_id=str(arguments.get("project_id", "")) or None,
        )
        token = context.current_workspace_id.set(workspace_id)
        try:
            return _text(await enqueue_agent_collaboration(request))
        finally:
            context.current_workspace_id.reset(token)
    if name == "send_collaboration_message":
        request = AgentChatRequest(
            session_id=str(arguments.get("collaboration_id", "")),
            message=str(arguments.get("message", "")),
            model="minimax-h3", mode="reference", review_mode="external",
            client_request_id=f"mcp-{uuid.uuid4().hex}",
        )
        return _text(await enqueue_agent_collaboration(request))
    if name == "upload_reference":
        filename = str(arguments.get("filename", "reference.bin")).replace("\\", "/").rsplit("/", 1)[-1]
        media_type = str(arguments.get("media_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        raw = base64.b64decode(str(arguments.get("data_base64", "")), validate=True)
        boundary = f"----ZizaiMCP{uuid.uuid4().hex}"
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {media_type}\r\n\r\n").encode()
        body = head + raw + f"\r\n--{boundary}--\r\n".encode()
        return _text(await asyncio.to_thread(_local_api_request, "POST", "/v1/uploads", body, f"multipart/form-data; boundary={boundary}"))
    if name == "submit_generation":
        payload = CreateRequest.model_validate(arguments).model_dump(mode="json")
        result = await asyncio.to_thread(_local_api_request, "POST", "/api/v2/generations", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", str(arguments.get("idempotency_key", "")), workspace_id)
        return _text(result)
    if name == "confirm_collaboration":
        payload = {"revision": int(arguments.get("revision", 0))}
        if arguments.get("idempotency_key"):
            payload["idempotency_key"] = str(arguments["idempotency_key"])
        if arguments.get("execution_prompt_en") is not None:
            payload["execution_prompt_en"] = str(arguments["execution_prompt_en"])
        if arguments.get("confirmed_prompt_zh") is not None:
            payload["confirmed_prompt_zh"] = str(arguments["confirmed_prompt_zh"])
        result = await asyncio.to_thread(_local_api_request, "POST", f"/api/v2/collaborations/{arguments.get('collaboration_id', '')}/confirm", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", str(arguments.get("idempotency_key", "")), workspace_id)
        return _text(result)
    if name == "get_job":
        return _text(await _local_api("GET", f"/api/v2/jobs/{arguments.get('job_id', '')}"))
    if name == "wait_job":
        timeout = max(1, min(120, int(arguments.get("timeout", 30))))
        return _text(await _local_api("GET", f"/api/v2/jobs/{arguments.get('job_id', '')}/wait?timeout={timeout}"))
    if name == "get_job_artifacts":
        return _text(await _local_api("GET", f"/api/v2/jobs/{arguments.get('job_id', '')}/artifacts"))
    if name == "get_job_inputs":
        return _text(await _local_api("GET", f"/api/v2/jobs/{arguments.get('job_id', '')}/inputs", workspace_id=workspace_id))
    if name == "cancel_job":
        return _text(await _local_api("POST", f"/api/v2/jobs/{arguments.get('job_id', '')}/cancel"))
    raise ValueError(f"工具尚未实现: {name}")


def build_router() -> APIRouter:
    router = APIRouter(prefix="/mcp", tags=["MCP"], dependencies=[Depends(auth)])

    @router.post("")
    async def mcp_endpoint(request: Request):
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return JSONResponse(
                _jsonrpc(None, error={
                    "code": -32700,
                    "message": "Parse error: 请求体不是合法 JSON，请使用双引号和标准 JSON 格式",
                    "data": str(exc),
                }),
                status_code=400,
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                _jsonrpc(None, error={
                    "code": -32600,
                    "message": "Invalid Request: MCP 请求体必须是 JSON 对象",
                }),
                status_code=400,
            )
        request_id = payload.get("id")
        method = payload.get("method")
        if not isinstance(method, str) or not method.strip():
            return JSONResponse(
                _jsonrpc(request_id, error={
                    "code": -32600,
                    "message": "Invalid Request: 缺少有效的 method",
                }),
                status_code=400,
            )
        params = payload.get("params") or {}
        if method == "initialize":
            return JSONResponse(_jsonrpc(request_id, {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": MCP_SERVER_INFO}))
        if method == "notifications/initialized":
            return JSONResponse({}, status_code=202)
        if method == "tools/list":
            return JSONResponse(_jsonrpc(request_id, {"tools": _tool_definitions()}))
        if method == "tools/call":
            try:
                return JSONResponse(_jsonrpc(request_id, await _tool_result(str(params.get("name", "")), params.get("arguments") or {})))
            except Exception as exc:
                return JSONResponse(_jsonrpc(request_id, error={"code": -32000, "message": str(exc)}))
        return JSONResponse(_jsonrpc(request_id, error={"code": -32601, "message": f"Method not found: {method}"}))

    @router.get("")
    async def mcp_info():
        return {"name": MCP_SERVER_INFO["name"], "protocol": "MCP Streamable HTTP", "endpoint": "/mcp", "server_info": MCP_SERVER_INFO}

    return router
