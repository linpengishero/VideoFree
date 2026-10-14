import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
from typing import Any
import uuid


class TaskStore:
    def __init__(self, tasks_path: Path, uploads_path: Path) -> None:
        self.tasks_path = tasks_path
        self.uploads_path = uploads_path

    def upload_path(self, value: str) -> Path | None:
        if not isinstance(value, str) or not value.startswith("upload:"):
            return None
        upload_id = value.removeprefix("upload:")
        if not upload_id or any(char not in "0123456789abcdef" for char in upload_id):
            return None
        matches = list(self.uploads_path.glob(f"{upload_id}.*"))
        return matches[0] if len(matches) == 1 and matches[0].is_file() else None

    def media_value(self, value: str, job_id: str) -> tuple[bytes, str]:
        if value.startswith("data:"):
            return self.data_url_bytes(value)
        if value.startswith("task:"):
            root = self.directory(job_id).resolve()
            path = (root / value.removeprefix("task:")).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError("任务素材不存在或路径无效")
            return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        path = self.upload_path(value)
        if path:
            return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        raise ValueError("上传素材引用无效或已过期")

    @staticmethod
    def data_url_bytes(value: str) -> tuple[bytes, str]:
        header, encoded = value.split(",", 1)
        media_type = header[5:].split(";", 1)[0] if header.startswith("data:") else "application/octet-stream"
        try:
            return base64.b64decode(encoded, validate=True), media_type
        except ValueError as exc:
            raise ValueError("Base64 素材格式无效") from exc

    @staticmethod
    def extension(media_type: str) -> str:
        known = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm", "audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/flac": ".flac", "audio/ogg": ".ogg"}
        return known.get(media_type, mimetypes.guess_extension(media_type) or ".bin")

    def directory(self, job_id: str) -> Path:
        kind = str(job_id).split("-", 1)[0]
        if kind not in {"image", "video", "tts", "music"}:
            kind = "other"
        return self.tasks_path / kind / str(job_id)

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def create(self, job: dict[str, Any], parent_job_id: str | None = None) -> Path:
        task_dir = self.directory(job["id"])
        for folder in (task_dir / "input" / "images", task_dir / "input" / "videos", task_dir / "input" / "audio", task_dir / "prompts", task_dir / "config", task_dir / "output"):
            folder.mkdir(parents=True, exist_ok=True)
        request, inputs = job["request"], []
        counters = {"image": 0, "video": 0, "audio": 0}

        def store(value: str, media_type: str, kind: str, original_name: str, role: str = "") -> None:
            if not isinstance(value, str):
                return
            source = self.upload_path(value)
            if not source and value.startswith("task:") and parent_job_id:
                parent_root = self.directory(parent_job_id).resolve()
                candidate = (parent_root / value.removeprefix("task:")).resolve()
                if parent_root not in candidate.parents or not candidate.is_file():
                    raise ValueError("父任务素材不存在或路径无效")
                source = candidate
            if source:
                detected_type, body = mimetypes.guess_type(source.name)[0] or media_type, None
            elif value.startswith("data:"):
                body, detected_type = self.data_url_bytes(value)
            else:
                raise ValueError("上传素材引用无效或已过期")
            media_type = detected_type or media_type
            counters[kind] += 1
            folder = {"image": "images", "video": "videos", "audio": "audio"}[kind]
            filename = f"{counters[kind]:03d}{self.extension(media_type)}"
            path = task_dir / "input" / folder / filename
            shutil.copy2(source, path) if source else path.write_bytes(body)
            inputs.append({"type": kind, "index": counters[kind], "original_name": original_name or filename, "path": path.relative_to(task_dir).as_posix(), "role": role, "media_type": media_type, "size": path.stat().st_size,
                           "upload_id": value.removeprefix("upload:") if value.startswith("upload:") else None,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

        params = request.get("params", {}) or {}
        for media, values, default_type, names, fallback_role in (
            ("image", request.get("references", []), "image/png", "Picture", "reference"),
            ("video", params.get("videos", []), "video/mp4", "Video", "reference"),
            ("audio", params.get("audios", []), "audio/wav", "Audio", "reference"),
        ):
            roles = params.get("input_roles", {}).get(media, [])
            for index, value in enumerate(values, 1):
                store(value, default_type, media, f"{names} {index}", roles[index - 1] if index <= len(roles) else fallback_role)
        if request.get("reference_audio"):
            store(request["reference_audio"], "audio/wav", "audio", "参考音频", "音色参考")

        prompt = request.get("prompt") or request.get("text") or ""
        (task_dir / "prompts" / "user.txt").write_text(str(prompt), encoding="utf-8")
        for key, filename in (("confirmed_prompt_zh", "confirmed_zh.txt"), ("execution_prompt_en", "execution_en.txt")):
            if params.get(key):
                (task_dir / "prompts" / filename).write_text(str(params[key]), encoding="utf-8")
        safe_request = dict(request)
        safe_request.pop("references", None)
        safe_request.pop("reference_audio", None)
        if isinstance(safe_request.get("params"), dict):
            safe_request["params"] = {key: value for key, value in safe_request["params"].items() if key not in {"videos", "audios"}}
        self.write_json(task_dir / "config" / "request.json", safe_request)
        self.write_json(task_dir / "manifest.json", {"task_id": job["id"], "kind": job["kind"], "project_id": job.get("project_id", "project-unassigned"), "parent_task_id": parent_job_id, "revision": job.get("revision", 1), "created_at": job["created_at"], "status": job["status"], "inputs": inputs, "outputs": [], "parameters": safe_request})
        return task_dir

    def hydrate(self, job: dict[str, Any]) -> dict[str, Any]:
        request = json.loads(json.dumps(job.get("request", {})))
        manifest_path = Path(job.get("manifest_path") or self.directory(job["id"]) / "manifest.json")
        if not manifest_path.is_file():
            return request
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        grouped: dict[str, list[str]] = {"image": [], "video": [], "audio": []}
        for item in sorted(manifest.get("inputs", []), key=lambda value: (value.get("type", ""), int(value.get("index", 0)))):
            media_type = item.get("type")
            if media_type in grouped and item.get("path"):
                grouped[media_type].append(f"task:{item['path']}")
        if grouped["image"]:
            request["references"] = grouped["image"]
        params = request.setdefault("params", {}) if job.get("kind") != "tts" else request.get("params", {})
        if grouped["video"]: params["videos"] = grouped["video"]
        if grouped["audio"]:
            if job.get("kind") == "tts": request["reference_audio"] = grouped["audio"][0]
            else: params["audios"] = grouped["audio"]
        return request

    def update_manifest(self, job_id: str, **values: Any) -> None:
        path = self.directory(job_id) / "manifest.json"
        if not path.is_file():
            return
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        manifest.update(values)
        self.write_json(path, manifest)
