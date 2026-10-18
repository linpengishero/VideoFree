"""ComfyUI-Whisper adapter owned by the film-studio application plugin."""
from __future__ import annotations

import asyncio
import mimetypes
import time
import uuid
from pathlib import Path


SUPPORTED_MODELS = {"tiny", "base", "small", "medium", "large-v1", "large-v2",
                    "large-v3", "large-v3-turbo", "turbo"}


def _output_value(output, *names):
    if not isinstance(output, dict):
        return None
    for name in names:
        if name in output:
            value = output[name]
            if isinstance(value, list) and len(value) == 1:
                value = value[0]
            return value
    return None


def _segments(history: dict) -> list[dict]:
    """Extract segment alignment from the custom node's history output."""
    for node in history.values():
        output = node.get("outputs", {}) if isinstance(node, dict) and "outputs" in node else node
        raw = _output_value(output, "segments_alignment", "segments", "alignment", "text")
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = None
        if isinstance(raw, list):
            result = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("value", item.get("text", ""))).strip()
                try:
                    start, end = float(item["start"]), float(item["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if text and end > start:
                    result.append({"text": text, "start": start, "end": end})
            if result:
                return result
    return []


class ComfyWhisper:
    """Submit the installed ComfyUI-Whisper nodes through the public ComfyUI API."""

    def __init__(self, runtime):
        self.runtime = runtime

    def _request(self, path, method="GET", body=None):
        return self.runtime.comfyui_request(path, method, body)

    async def transcribe(self, source: Path, *, language="auto", model="large-v3-turbo",
                         prompt="", seek=0.0, duration=0.0, timeout=3600) -> list[dict]:
        if model not in SUPPORTED_MODELS:
            raise ValueError("Whisper 模型不受支持")
        if not source.is_file():
            raise ValueError("待识别的声音素材不存在")
        media_type = mimetypes.guess_type(source.name)[0] or "audio/wav"
        filename = f"film-studio-{uuid.uuid4().hex}{source.suffix.lower() or '.wav'}"
        uploaded = await asyncio.to_thread(self.runtime.comfyui_upload, source.read_bytes(), media_type, filename)
        if not uploaded:
            raise RuntimeError("ComfyUI 未返回上传文件名")
        node_language = "auto" if language in (None, "", "auto") else language
        workflow = {
            "1": {"class_type": "LoadAudio", "inputs": {
                "audio": uploaded,
            }},
            "2": {"class_type": "Apply Whisper", "inputs": {
                "audio": ["1", 0], "model": model, "language": node_language,
                "prompt": str(prompt or ""),
            }},
            # Apply Whisper is not an output node. Display Any keeps its alignment output
            # in ComfyUI history so the gateway can retrieve timestamps without a temp SRT.
            "3": {"class_type": "Display Any (rgthree)", "inputs": {
                "source": ["2", 1],
            }},
        }
        import json
        try:
            response = await asyncio.to_thread(self._request, "/prompt", "POST",
                                               json.dumps({"prompt": workflow, "client_id": "film-studio"}).encode())
        except RuntimeError as exc:
            detail = str(exc)
            if "prompt_no_outputs" in detail:
                raise RuntimeError("字幕识别工作流缺少可用输出节点；请确认 rgthree 的 Display Any 节点已安装并重启 ComfyUI") from exc
            if "does not exist" in detail or "class_type" in detail:
                raise RuntimeError("字幕识别所需的 ComfyUI-Whisper 或 rgthree 节点未正确加载") from exc
            raise RuntimeError("ComfyUI 拒绝字幕识别任务，请检查 Whisper 节点与模型配置") from exc
        prompt_id = response.get("prompt_id") if isinstance(response, dict) else None
        if not prompt_id:
            raise RuntimeError("ComfyUI 未接受字幕识别任务")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            try:
                history = await asyncio.to_thread(self._request, f"/history/{prompt_id}")
            except Exception:
                continue
            item = history.get(prompt_id) if isinstance(history, dict) else None
            if not item:
                continue
            if item.get("status", {}).get("status_str") == "error":
                raise RuntimeError("ComfyUI Whisper 识别失败，请查看 ComfyUI 日志")
            result = _segments(item.get("outputs", {}) if "outputs" in item else item)
            if result:
                return result
            if item.get("status", {}).get("completed"):
                return []
        raise RuntimeError("字幕识别超时，请检查 ComfyUI 和 Whisper 模型状态")
