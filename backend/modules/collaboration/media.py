import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from ...bootstrap import context


def collaboration_directory(collaboration_id: str) -> Path:
    return context.paths.collaborations / collaboration_id


def materialize_reference(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("data:"):
        return value
    if not value.startswith("collaboration:"):
        return None
    collaboration_id = context.current_collaboration_id.get()
    if not collaboration_id:
        return None
    relative = value.split(":", 1)[1].lstrip("/")
    root = collaboration_directory(collaboration_id).resolve()
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        return None
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def materialize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded = json.loads(json.dumps(messages, ensure_ascii=False))
    for message in expanded:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        filtered = []
        for item in content:
            if not isinstance(item, dict):
                filtered.append(item)
                continue
            if item.get("type") in {"image_url", "video_url"}:
                key = item["type"]
                value = materialize_reference(item.get(key, {}).get("url"))
                if value:
                    item[key]["url"] = value
                    filtered.append(item)
            elif item.get("type") == "input_audio":
                value = materialize_reference(item.get("input_audio", {}).get("data"))
                if value and "," in value:
                    item["input_audio"]["data"] = value.split(",", 1)[1]
                    filtered.append(item)
            else:
                filtered.append(item)
        message["content"] = filtered
    return expanded


def strip_rich_media(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped = json.loads(json.dumps(messages, ensure_ascii=False))
    for message in stripped:
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"]
                if not isinstance(item, dict) or item.get("type") not in {"video_url", "input_audio"}
            ]
            message["content"].insert(0, {
                "type": "text",
                "text": "注意：当前 AI 服务不支持视频或音频多模态输入，以下参考视频/音频未被模型读取；请仅依据文字、文件名和已提供的素材说明继续。",
            })
    return stripped


def has_rich_media(messages: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(message.get("content"), list)
        and any(isinstance(item, dict) and item.get("type") in {"video_url", "input_audio"} for item in message["content"])
        for message in messages
    )


def is_compatibility_error(exc: ValueError) -> bool:
    if getattr(exc, "status", None) not in {400, 415, 422, 500, 501}:
        return False
    detail = str(exc).lower()
    media_markers = ("audio", "video", "input_audio", "video_url", "mmproj", "multimodal")
    rejection_markers = ("not supported", "unsupported", "invalid", "unknown", "mmproj")
    return any(marker in detail for marker in media_markers) and any(marker in detail for marker in rejection_markers)
