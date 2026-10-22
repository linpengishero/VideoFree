"""ComfyUI-Whisper adapter owned by the film-studio application plugin."""
from __future__ import annotations

import asyncio
import mimetypes
import time
import uuid
from pathlib import Path


SUPPORTED_MODELS = {"tiny", "base", "small", "medium", "large-v1", "large-v2",
                    "large-v3", "large-v3-turbo", "turbo"}
COMFYUI_LANGUAGES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "中文": "Chinese",
    "en": "English",
    "en-us": "English",
    "英文": "English",
}
TRANSCRIPTION_PROMPTS = {
    "Chinese": "这是一段普通话语音。请使用简体中文转写，保留完整词语、专有名词和数字，不要翻译或改写原意。",
    "English": "Transcribe the speech accurately in English. Preserve complete words, names, and numbers without translating or rewriting.",
    "auto": "Transcribe the speech accurately in its original language. Preserve complete words, names, and numbers without translating or rewriting.",
}


def _comfyui_language(language) -> str:
    value = str(language or "auto").strip()
    if value.lower() == "auto":
        return "auto"
    return COMFYUI_LANGUAGES.get(value.lower(), COMFYUI_LANGUAGES.get(value, value))


def transcription_prompt(language) -> str:
    return TRANSCRIPTION_PROMPTS.get(_comfyui_language(language), TRANSCRIPTION_PROMPTS['auto'])


def normalize_text(text: str, language: str) -> str:
    """Convert Chinese recognition output to simplified Chinese."""
    value = str(text or '').strip()
    if str(language or '').strip().lower() not in {'zh', 'zh-cn', 'chinese', '中文'}:
        return value
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError(
            '中文自动字幕需要 opencc-python-reimplemented，请按插件 INSTALL.md 安装依赖后重试'
        ) from exc
    return OpenCC('t2s').convert(value)


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
        node_language = _comfyui_language(language)
        prompt_text = str(prompt or '').strip() or TRANSCRIPTION_PROMPTS.get(node_language, '')
        workflow = {
            "1": {"class_type": "LoadAudio", "inputs": {
                "audio": uploaded,
            }},
            "2": {"class_type": "Apply Whisper", "inputs": {
                "audio": ["1", 0], "model": model, "language": node_language,
                "prompt": prompt_text,
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
            lowered = detail.lower()
            if "does not exist" in lowered or "node not found" in lowered:
                raise RuntimeError("字幕识别所需的 ComfyUI-Whisper 或 rgthree 节点未正确加载") from exc
            raise RuntimeError(f"ComfyUI 拒绝字幕识别任务：{detail}") from exc
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
