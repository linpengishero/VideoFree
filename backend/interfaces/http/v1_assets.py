# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import asyncio
import mimetypes
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...bootstrap import context
from ...modules.projects import ProjectService
from .dependencies import auth


router = APIRouter()
UPLOAD_CACHE = context.paths.uploads
MAX_UPLOAD_BYTES = context.config.max_upload_bytes

UPLOAD_MEDIA_TYPES = {
    "image/png": ("image/png", ".png"),
    "image/jpeg": ("image/jpeg", ".jpg"),
    "image/jpg": ("image/jpeg", ".jpg"),
    "image/webp": ("image/webp", ".webp"),
    "video/mp4": ("video/mp4", ".mp4"),
    "video/webm": ("video/webm", ".webm"),
    "video/quicktime": ("video/quicktime", ".mov"),
    "audio/wav": ("audio/wav", ".wav"),
    "audio/x-wav": ("audio/wav", ".wav"),
    "audio/vnd.wave": ("audio/wav", ".wav"),
    "audio/mpeg": ("audio/mpeg", ".mp3"),
    "audio/flac": ("audio/flac", ".flac"),
    "audio/x-flac": ("audio/flac", ".flac"),
    "audio/ogg": ("audio/ogg", ".ogg"),
    "audio/mp4": ("audio/mp4", ".m4a"),
    "audio/x-m4a": ("audio/mp4", ".m4a"),
}


def resolve_upload_media(file: UploadFile) -> tuple[str, str] | None:
    declared = (file.content_type or "").split(";", 1)[0].strip().lower()
    resolved = UPLOAD_MEDIA_TYPES.get(declared)
    if resolved:
        return resolved
    guessed = (mimetypes.guess_type(file.filename or "")[0] or "").lower()
    return UPLOAD_MEDIA_TYPES.get(guessed)


def validate_upload_content(path, media_type: str) -> None:
    """Reject truncated or undecodable media before it reaches a worker."""
    if media_type.startswith("image/"):
        try:
            from PIL import Image
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            raise HTTPException(422, "文件内容损坏或格式与扩展名不匹配") from exc
    elif media_type.startswith(("video/", "audio/")):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return
        try:
            subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=format_name",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True, check=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(422, "文件内容损坏或格式与扩展名不匹配") from exc


@router.post("/v1/uploads", dependencies=[Depends(auth)])
async def upload_media(file: UploadFile = File(...)):
    resolved = resolve_upload_media(file)
    if resolved:
        media_type, extension = resolved
    else:
        media_type, extension = "", ""
    if not extension:
        raise HTTPException(415, "仅支持常用图片、视频和音频格式")
    upload_id = uuid.uuid4().hex
    target = UPLOAD_CACHE / f"{upload_id}{extension}"
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"单文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    try:
        validate_upload_content(target, media_type)
        context.db.register_upload(upload_id)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"upload_id": upload_id, "value": f"upload:{upload_id}", "size": size, "media_type": media_type}

@router.get("/v1/library")
async def library(kind: str = "all", offset: int = 0, limit: int | None = None, sort: str = "new", category_id: str | None = None, _: None = Depends(auth), project_id: str | None = None):
    types = {"image": {".png", ".jpg", ".jpeg", ".webp", ".gif"}, "video": {".mp4", ".webm", ".mov", ".mkv"}, "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"}, "music": {".mp3", ".wav", ".flac", ".ogg", ".m4a"}}
    if kind not in {"all", *types}: raise HTTPException(400, "invalid library type")
    if offset < 0 or (limit is not None and (limit < 1 or limit > 100)) or sort not in {"new", "old"}: raise HTTPException(400, "invalid pagination")
    service = ProjectService(context)
    try:
        project = (service.authorize(project_id) if project_id else service.current())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not project or project.get("status") != "active":
        raise HTTPException(422, "项目不存在或已归档")
    try:
        return await asyncio.to_thread(service.library, project["id"], kind=kind, offset=offset,
                                        limit=limit, sort=sort, category_id=category_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/v1/library/files/{path:path}")
async def library_file(path: str, _: None = Depends(auth)):
    service = ProjectService(context)
    try:
        target = service.storage.local_path(path)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "file not found")
    relative = Path(path.replace("\\", "/"))
    if not relative.parts: raise HTTPException(404, "file not found")
    try:
        service.authorize_library_path(relative)
    except ValueError as exc:
        raise HTTPException(404, "file not found") from exc
    return FileResponse(target)

