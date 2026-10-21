# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from array import array
from contextlib import contextmanager
import io
import json
from pathlib import Path
import time
import sys
import wave
import uuid
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request


class Provider:
    node_id = "default"
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._node_cache: dict[tuple[str, ...], tuple[float, dict[str, Any]]] = {}

    def configure(self, base_url: str) -> None:
        normalized = base_url.rstrip("/")
        if normalized != self.base_url:
            self.base_url = normalized
            self._node_cache.clear()

    def request(self, path: str, method: str = "GET", body: bytes | None = None) -> Any:
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ComfyUI HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 ComfyUI：{self.base_url}；{exc.reason}") from exc

    def is_available(self) -> bool:
        """Probe connectivity without depending on one optional diagnostics endpoint."""
        for path in ("/queue", "/system_stats"):
            try:
                self.request(path)
                return True
            except (OSError, RuntimeError, ValueError):
                continue
        return False

    def node_definitions(self, kinds: Iterable[str], aliases: dict[str, str]) -> dict[str, Any]:
        ignored = {
            "Note", "MarkdownNote", "Label (rgthree)", "AboutAuthorNode|Mie",
            "Fast Groups Bypasser (rgthree)", "Fast Groups Muter (rgthree)",
        }
        cache_key = tuple(sorted({aliases.get(kind, kind) for kind in kinds}))
        cached = self._node_cache.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < 60:
            return cached[1]
        definitions: dict[str, Any] = {}
        for kind in cache_key:
            canonical = aliases.get(kind, kind)
            if canonical not in ignored:
                definitions.update(self.request("/object_info/" + urllib.parse.quote(canonical, safe="")))
        self._node_cache[cache_key] = (now, definitions)
        return definitions

    def upload_input(self, body: bytes, media_type: str, filename: str) -> str:
        # ComfyUI's audio loader rejects uint8 WAV; preserve the original upload
        # and convert only the copy sent to ComfyUI into signed PCM16.
        if body[:4] == b"RIFF" and body[8:12] == b"WAVE":
            try:
                with wave.open(io.BytesIO(body), "rb") as source:
                    if source.getsampwidth() == 1:
                        samples = array("h", ((value - 128) << 8 for value in source.readframes(source.getnframes())))
                        if sys.byteorder != "little":
                            samples.byteswap()
                        output = io.BytesIO()
                        with wave.open(output, "wb") as target:
                            target.setnchannels(source.getnchannels())
                            target.setsampwidth(2)
                            target.setframerate(source.getframerate())
                            target.writeframes(samples.tobytes())
                        body = output.getvalue()
            except wave.Error:
                # Other WAV codecs may be supported by ComfyUI's loader.
                pass
        boundary = "----MediaGatewayBoundary"
        payload = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {media_type}\r\n\r\n"
        ).encode() + body + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            self.base_url + "/upload/image",
            data=payload,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read())
        return str(result.get("name") or result.get("filename") or "")

    def download_output(self, value: dict[str, Any]) -> bytes:
        with self.open_output(value) as response:
            return response.read()

    @contextmanager
    def open_output(self, value: dict[str, Any]):
        query = urllib.parse.urlencode({
            "filename": value.get("filename", ""),
            "subfolder": value.get("subfolder", ""),
            "type": value.get("type", "output"),
        })
        with urllib.request.urlopen(self.base_url + "/view?" + query, timeout=60) as response:
            yield response

    def upload_file(self, source: Path, relative: str, destination: str = "output") -> dict:
        """Stream an opaque dependency back to the single configured worker."""
        normalized = relative.replace("\\", "/")
        if (destination not in {"input", "output"} or any(c in normalized for c in '\r\n":')
                or any(p in {"", ".", ".."} for p in normalized.split("/"))):
            raise ValueError("Invalid ComfyUI file destination")
        folder, _, filename = normalized.rpartition("/")
        boundary = "VideoFree Studio" + uuid.uuid4().hex
        prefix = b""
        for name, value in (("type", destination), ("subfolder", folder), ("overwrite", "true")):
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode()
        prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                   'Content-Type: application/octet-stream\r\n\r\n').encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()
        with Path(source).open("rb") as handle:
            def chunks():
                yield prefix
                while chunk := handle.read(1024 * 1024):
                    yield chunk
                yield suffix
            request = urllib.request.Request(self.base_url + "/upload/image", data=chunks(), method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                         "Content-Length": str(len(prefix) + Path(source).stat().st_size + len(suffix))})
            try:
                with urllib.request.urlopen(request, timeout=600) as response:
                    result = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 413:
                    megabytes = Path(source).stat().st_size / (1024 * 1024)
                    raise RuntimeError(
                        f"ComfyUI 拒绝恢复依赖文件（{megabytes:.1f} MiB）：HTTP 413，上传大小超限。"
                        "请增大 ComfyUI 启动参数 --max-upload-size（单位 MB，须大于文件大小并预留表单开销），"
                        "重启 ComfyUI 后重试；若使用反向代理，也请检查其上传大小限制。"
                    ) from exc
                raise RuntimeError(f"ComfyUI 恢复依赖文件失败：HTTP {exc.code}") from exc
        if (result.get("name") != filename or result.get("subfolder", "").replace("\\", "/") != folder
                or result.get("type") != destination):
            raise RuntimeError("ComfyUI returned an unexpected file destination")
        return result

    def free_memory(self) -> None:
        try:
            self.request("/free", "POST", b'{"unload_models":true,"free_memory":true}')
        except (OSError, RuntimeError, ValueError):
            return
