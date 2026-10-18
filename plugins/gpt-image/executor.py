"""Plugin-owned cloud image executor."""
import base64
import json
import mimetypes
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from backend.integrations.native import NativeExecutionCancelled, NativeExecutionContext, NativeExecutionResult

GRSAI_SIZES = {
    "1:1": ("1024x1024", 1024, 1024),
    "16:9": ("1672x941", 1672, 941),
    "9:16": ("941x1672", 941, 1672),
    "4:3": ("1443x1090", 1443, 1090),
    "3:4": ("1090x1443", 1090, 1443),
    "3:2": ("1536x1024", 1536, 1024),
    "2:3": ("1024x1536", 1024, 1536),
    "21:9": ("1920x832", 1920, 832),
}


def _ratio(params: dict[str, Any]) -> str:
    width = max(1, int(params.get("width", 1024)))
    height = max(1, int(params.get("height", 576)))
    return min(GRSAI_SIZES, key=lambda value: abs(width / height - int(value.split(":")[0]) / int(value.split(":")[1])))


def _json_request(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "Zizai-Creation/1.0",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            if raw.startswith("data: "):
                raw = raw[6:]
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("GrisAI 返回了无法识别的数据")
            return value
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ValueError("GrisAI API Key 无效或已过期") from exc
            if exc.code == 429:
                raise ValueError("GrisAI 请求频率过高，请稍后重试") from exc
            if exc.code < 500 or attempt == 2:
                raise ValueError(f"GrisAI HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise ValueError(f"无法连接 GrisAI: {exc.reason if isinstance(exc, urllib.error.URLError) else exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("GrisAI 返回了无效 JSON") from exc
        time.sleep(2**attempt)
    raise ValueError("GrisAI 请求失败")


def _extension(url: str, media_type: str, body: bytes) -> str:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return ".webp"
    return mimetypes.guess_extension(media_type.split(";", 1)[0]) or Path(urllib.parse.urlparse(url).path).suffix or ".png"


def _image_dimensions(body: bytes) -> tuple[int, int] | None:
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 24:
        return struct.unpack(">II", body[16:24])
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP" and len(body) >= 30:
        kind = body[12:16]
        if kind == b"VP8X":
            return 1 + int.from_bytes(body[24:27], "little"), 1 + int.from_bytes(body[27:30], "little")
        if kind == b"VP8 " and body[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(body[26:28], "little") & 0x3FFF, int.from_bytes(body[28:30], "little") & 0x3FFF
    if body.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(body):
            if body[offset] != 0xFF:
                offset += 1
                continue
            marker = body[offset + 1]
            if marker in {0xD8, 0xD9}:
                offset += 2
                continue
            length = int.from_bytes(body[offset + 2:offset + 4], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                return int.from_bytes(body[offset + 7:offset + 9], "big"), int.from_bytes(body[offset + 5:offset + 7], "big")
            if length < 2:
                break
            offset += 2 + length
    return None


def execute_grsai(context: NativeExecutionContext) -> NativeExecutionResult:
    if not context.api_key.startswith("sk-"):
        raise ValueError("请先在设置中填写有效的 GrisAI API Key")
    if context.cancelled():
        raise NativeExecutionCancelled()
    ratio = _ratio(context.params)
    size, width, height = GRSAI_SIZES[ratio]
    requested_width = max(64, int(context.params.get("width", width)))
    requested_height = max(64, int(context.params.get("height", height)))
    references = []
    for value in context.references:
        body, _ = context.media_loader(value)
        references.append(base64.b64encode(body).decode("ascii"))
    payload = {
        "model": context.config.get("model", "gpt-image-2"),
        "prompt": context.prompt,
        "urls": references,
        "shutProgress": True,
        "aspectRatio": size,
        # Keep the provider's aspect-ratio contract while passing the user's
        # requested output size to providers that support native sizing.
        "imageSize": f"{requested_width}x{requested_height}",
    }
    base_url = str(context.config.get("base_url", "https://grsai.dakka.com.cn")).rstrip("/")
    result = _json_request(base_url + "/v1/draw/completions", payload, context.api_key, int(context.config.get("timeout", 600)))
    if result.get("status") != "succeeded":
        detail = result.get("error") or result.get("message") or result.get("id") or "未知错误"
        raise ValueError(f"GrisAI 生图失败: {detail}")
    urls = [item.get("url") for item in result.get("results", []) if isinstance(item, dict) and isinstance(item.get("url"), str)]
    if not urls and isinstance(result.get("url"), str):
        urls = [result["url"]]
    if not urls:
        raise ValueError("GrisAI 未返回图片地址")
    paths = []
    actual_dimensions = None
    for index, url in enumerate(urls):
        if context.cancelled():
            raise NativeExecutionCancelled()
        if urllib.parse.urlparse(url).scheme not in {"http", "https"}:
            raise ValueError("GrisAI 返回了无效图片地址")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Zizai-Creation/1.0"}), timeout=120) as response:
            body = response.read(100 * 1024 * 1024 + 1)
            media_type = response.headers.get_content_type()
        if not body or len(body) > 100 * 1024 * 1024:
            raise ValueError("GrisAI 返回图片为空或超过 100MB")
        path = context.output_dir / f"{context.job_id}_{index}{_extension(url, media_type, body)}"
        path.write_bytes(body)
        paths.append(path)
        actual_dimensions = actual_dimensions or _image_dimensions(body)
    actual_width, actual_height = actual_dimensions or (requested_width, requested_height)
    return NativeExecutionResult(paths, actual_width, actual_height)
