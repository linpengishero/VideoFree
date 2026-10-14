import asyncio
import mimetypes
import time
import urllib.parse
import uuid
from typing import Any

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
    return {"upload_id": upload_id, "value": f"upload:{upload_id}", "size": size, "media_type": media_type}

@router.get("/v1/library")
async def library(kind: str = "all", offset: int = 0, limit: int | None = None, sort: str = "new", _: None = Depends(auth)):
    types = {"image": {".png", ".jpg", ".jpeg", ".webp", ".gif"}, "video": {".mp4", ".webm", ".mov", ".mkv"}, "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"}, "music": {".mp3", ".wav", ".flac", ".ogg", ".m4a"}}
    if kind not in {"all", *types}: raise HTTPException(400, "invalid library type")
    if offset < 0 or (limit is not None and (limit < 1 or limit > 100)) or sort not in {"new", "old"}: raise HTTPException(400, "invalid pagination")
    project = ProjectService(context).current(context.current_workspace_id.get())
    return await asyncio.to_thread(scan_library, kind, offset, limit, sort, types, project)


def scan_library(kind: str, offset: int, limit: int, sort: str, types: dict[str, set[str]], project: dict[str, Any]) -> dict[str, Any]:
    project_directory = ProjectService(context).ensure_directory(project)
    directory = str(project_directory)
    with context.library_lock:
        if context.library_cache["directory"] != directory or time.monotonic() - context.library_cache["created_at"] > 30:
            indexed = []
            for path in project_directory.rglob("*"):
                if not path.is_file(): continue
                ext = path.suffix.lower()
                relative_project = path.relative_to(project_directory)
                media_type = "music" if relative_project.parts and relative_project.parts[0] == "music" else next((name for name, extensions in types.items() if name != "music" and ext in extensions), None)
                if not media_type: continue
                stat = path.stat()
                relative = str(path.relative_to(context.paths.projects)).replace("\\", "/")
                indexed.append({"name": path.name, "path": relative, "type": media_type, "modified": stat.st_mtime, "size": stat.st_size, "url": f"/v1/library/files/{urllib.parse.quote(relative)}"})
            indexed.sort(key=lambda item: item["modified"], reverse=True)
            context.library_cache.update(directory=directory, created_at=time.monotonic(), items=indexed)
        items = [item for item in context.library_cache["items"] if kind == "all" or item["type"] == kind]
    if sort == "old":
        items = list(reversed(items))
    page = items[offset:] if limit is None else items[offset:offset + limit]
    next_offset = None if limit is None or offset + limit >= len(items) else offset + limit
    return {"items": page, "total": len(items), "next_offset": next_offset, "output_dir": directory, "project_id": project["id"]}

@router.get("/v1/library/files/{path:path}")
async def library_file(path: str, _: None = Depends(auth)):
    root = context.paths.projects.resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file(): raise HTTPException(404, "file not found")
    return FileResponse(target)

