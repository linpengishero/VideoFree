"""自由之手（Zizai）生成能力的**声明** —— 只服务于注册表 / preflight / 选择器。

为什么这里没有实现
------------------
生成能力的唯一实现在 MCP 服务：`/fast/tools/zizai-media-mcp`（端点 `127.0.0.1:8991/mcp`）。
它对本项目的 agent 暴露这些工具（同名，直接调）：

    zizai_image / zizai_video / zizai_video_post / zizai_tts / zizai_music
    zizai_job / zizai_status / zizai_capabilities / zizai_voices

参数校验与"黄金路径"固化在那边：视频默认 `reference`（多参考）且必须给参考图、
提示词自动编译、抽卡 480P/quick_preview、`h3_refine` 二采定稿、沙箱↔宿主路径映射、
长任务 submit→有界 wait→zizai_job 续等。

本文件只做两件事
----------------
1. 让 `registry.get_by_capability(...)` / `provider_menu_summary()` 知道这台机器有
   图 / 视频 / 配音 / 音乐 能力 —— 否则管线资产阶段会认为"没有生成 provider"而拒绝开工。
2. `execute()` 明确**拒绝执行**并指向 MCP 工具 —— 防止 agent 绕过 MCP 自己去拼 REST 调用。

历史与教训（2026-09-30 收口）
-----------------------------
这些工具原先各自带一份 HTTP 实现 + `tools/_zizai/client.py` 客户端。结果是：agent 直接
读客户端源码、绕开封装自己写脚本 —— 参数选错（整条片子走成纯文生视频、零参考图）、
每个任务重造一遍轮询脚本、checkpoint 逐字段死磕 1.5 小时。现在改为"仓库只留声明、
实现只有一份"，既让上游 `git pull` 干净，也让"绕过"在物理上失去说明书。
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability

# 网关地址的唯一来源：MCP 服务的 config.yaml（仓库 .env 里的 ZIZAI_* 已撤掉）
_MCP_CONFIG = Path("/fast/tools/zizai-media-mcp/config.yaml")


def _gateway_base() -> str:
    """网关基址。优先读 MCP 的 config.yaml，其次环境变量，最后默认值。"""
    try:
        import yaml  # 仓库里有 pyyaml

        data = yaml.safe_load(_MCP_CONFIG.read_text(encoding="utf-8")) or {}
        url = str((data.get("gateway") or {}).get("base_url") or "").strip()
        if url:
            return url.rstrip("/").removesuffix("/api/v2")
    except Exception:
        pass
    raw = (os.environ.get("ZIZAI_API_URL") or "http://192.168.50.8:8765").strip()
    return raw.rstrip("/").removesuffix("/api/v2")


def _gateway_online(timeout: float = 3.0) -> tuple[bool, str]:
    """探活：网关在线才算 AVAILABLE（preflight 要看到真实状态）。"""
    base = _gateway_base()
    try:
        with urllib.request.urlopen(base + "/api/v2/health", timeout=timeout) as resp:
            payload = json.loads(resp.read() or b"{}")
        ok = str(payload.get("status", "")).lower() in ("ok", "healthy", "up")
        return ok, f"在线（{payload.get('capabilities', '?')} 项能力）" if ok else f"状态异常：{payload}"
    except Exception as exc:
        return False, f"不可达（{base}）：{type(exc).__name__}"


class _ZizaiDeclareMixin:
    """共享元数据 + 探活 + 拒执行。

    注意：**故意不继承 BaseTool** —— 注册器会把本模块里所有非抽象的 BaseTool 子类都收走，
    一个同模块的中间基类会被当成无 name 的工具（实测报 "Tool must have a non-empty name"）。
    作为纯混入类，它被 `issubclass(cls, BaseTool)` 过滤掉，只有下面 5 个具体类会被注册。
    """

    provider = "zizai"
    version = "2.0.0"
    name: str = ""  # 由各具体子类覆盖（混入类自己不注册，仅为类型检查）
    runtime = ToolRuntime.LOCAL
    stability = ToolStability.PRODUCTION
    agent_skills = ["zizai-media-gateway"]
    dependencies: list[str] = []
    install_instructions = (
        "自托管局域网媒体网关（自由之手）。生成请走 MCP 工具；"
        "网关地址见 /fast/tools/zizai-media-mcp/config.yaml"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "描述文本。**请改用 MCP 工具，参数以它为准。**"},
        },
        "required": ["prompt"],
    }
    idempotency_key_fields = ["prompt"]

    def get_status(self):
        ok, detail = _gateway_online()
        self._status_detail = detail
        from tools.base_tool import ToolStatus

        return ToolStatus.AVAILABLE if ok else ToolStatus.UNAVAILABLE

    def execute(self, inputs: dict) -> ToolResult:
        return ToolResult(
            success=False,
            error=(
                f"{self.name} 只是能力声明，本环境不在这里生成。"
                f"请调用 MCP 工具 `mcp__zizai_media__{self.name}`（同名参数，参数校验/黄金路径都在那边）。"
            ),
        )


class ZizaiImage(_ZizaiDeclareMixin, BaseTool):
    name = "zizai_image"
    capability = "image_generation"
    capabilities = ["image_generation"]
    description = (
        "本地/局域网 GPT-Image 2.5 生图（自由之手网关）。取值：text_to_image / image_to_image / "
        "character（定妆图）/ scene / storyboard_4 / storyboard_6（宫格分镜，自动切单格）。"
        "实现与参数见 MCP 工具 mcp__zizai_media__zizai_image。"
    )
    supports = {
        "generate_image": True,
        "image_to_image": True,
        "character_consistency": True,
        "storyboard": True,
        "native_model_selection": True,
        "mcp_only": True,
    }
    best_for = ["character-consistent reference stills", "storyboard grids for scene planning"]
    not_good_for = ["text rendering in non-Latin scripts"]
    artifact_schema = {"type": "image", "extensions": [".png", ".jpg", ".webp"]}


class ZizaiVideo(_ZizaiDeclareMixin, BaseTool):
    name = "zizai_video"
    capability = "video_generation"
    capabilities = ["video_generation"]
    description = (
        "MiniMax H3 视频片段（自由之手网关）。**默认 video.reference（多参考），必须给参考图**；"
        "mode=text_to_video 需显式指定。480P+quick_preview 抽卡，满意后由 zizai_video_post 二采定稿。"
        "实现与参数见 MCP 工具 mcp__zizai_media__zizai_video。"
    )
    supports = {
        "generate_video": True,
        "reference_to_video": True,
        "multiple_references": True,
        "multi-reference shots: keep characters/props consistent from still images": True,
        "duration_control": True,
        "seed": True,
        "mcp_only": True,
    }
    best_for = ["character/scene-consistent generated shots", "documentary-style b-roll"]
    not_good_for = ["single clip longer than 15 seconds (split instead)"]
    artifact_schema = {"type": "video", "extensions": [".mp4"]}


class ZizaiVideoPost(_ZizaiDeclareMixin, BaseTool):
    name = "zizai_video_post"
    capability = "video_post"
    capabilities = ["video_post"]
    description = (
        "视频二采定稿（h3_refine，不重抽，内容不变）。抽卡满意后用它把 480P 预览升到 720p。"
        "实现与参数见 MCP 工具 mcp__zizai_media__zizai_video_post。"
    )
    supports = {"refine": True, "upscale": True, "mcp_only": True}
    best_for = ["finalising a picked preview without regenerating"]


class ZizaiTts(_ZizaiDeclareMixin, BaseTool):
    name = "zizai_tts"
    capability = "tts"
    capabilities = ["tts"]
    description = (
        "qwen3-tts 配音（自由之手网关，18 种预设音色，如 documentary_female / narrator_female / orion_7）。"
        "实现与参数见 MCP 工具 mcp__zizai_media__zizai_tts（先 zizai_voices 看音色，别猜）。"
    )
    supports = {"chinese_language": True, "voice_presets": True, "voice_design": True, "speed": True, "mcp_only": True}
    best_for = ["Chinese narration with preset voices"]
    artifact_schema = {"type": "audio", "extensions": [".flac", ".wav", ".mp3"]}


class ZizaiMusic(_ZizaiDeclareMixin, BaseTool):
    name = "zizai_music"
    capability = "music_generation"
    capabilities = ["music_generation"]
    description = (
        "MiniMax Music 3 生成音乐/歌曲（自由之手网关）。lyrics 必填；风格/歌手/音色纹理走 settings。"
        "实现与参数见 MCP 工具 mcp__zizai_media__zizai_music。"
    )
    supports = {"music_generation": True, "lyrics_control": True, "duration_control": True,
                "voice_texture": True, "mcp_only": True}
    best_for = ["short original beds and songs with Chinese lyrics"]
    artifact_schema = {"type": "audio", "extensions": [".flac", ".mp3"]}
