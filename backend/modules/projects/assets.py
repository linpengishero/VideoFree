"""Project-wide reusable asset records and their independently owned media."""
from __future__ import annotations

import mimetypes
from pathlib import Path
import re
import shutil
import urllib.parse
import uuid

from .service import ProjectService, MEDIA_EXTENSIONS


# These are starter labels for the UI, not a schema constraint. Projects may
# define any non-empty asset kind and attach any supported media to it.
DEFAULT_ASSET_KINDS = ("character", "scene", "prop", "music", "sound", "other")


class PublicAssetService:
    def __init__(self, context):
        self.context = context
        self.projects = ProjectService(context)

    def list(self, project_id: str) -> list[dict]:
        self.projects.categories(project_id)  # Validate active project ownership.
        return self.context.db.project_assets(project_id)

    def list_types(self, project_id: str) -> list[dict]:
        self.projects.categories(project_id)
        return self.context.db.project_asset_types(project_id)

    def save_type(self, project_id: str, name: str, description: str = "", type_id: str | None = None) -> dict:
        self.projects.categories(project_id)
        name = name.strip()
        description = description.strip()
        if not name or len(name) > 40 or "\n" in name or "\r" in name or len(description) > 1000:
            raise ValueError("资产类别名称或描述长度无效")
        existing = next((item for item in self.list_types(project_id) if item["id"] == type_id), None) if type_id else None
        if type_id and not existing:
            raise ValueError("资产类别不存在")
        value = existing or {"id": f"asset-type-{uuid.uuid4().hex}", "project_id": project_id}
        value.update(name=name, description=description)
        try:
            self.context.db.save_project_asset_type(value, create=existing is None)
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("该资产类别已存在") from exc
            raise
        return value

    def get(self, project_id: str, asset_id: str) -> dict:
        asset = next((item for item in self.list(project_id) if item["id"] == asset_id), None)
        if not asset:
            raise ValueError("公共资产不存在或不属于当前项目")
        return asset

    def save(self, project_id: str, name: str, kind: str, description: str, asset_id: str | None = None, voice_text: str | None = None) -> dict:
        self.list(project_id)
        if not name.strip() or len(name.strip()) > 80:
            raise ValueError("资产名称须为1至80个字符")
        kind = kind.strip()
        if not kind or len(kind) > 40 or "\n" in kind or "\r" in kind or len(description) > 10000:
            raise ValueError("资产类型或描述长度无效")
        asset = self.get(project_id, asset_id) if asset_id else {
            "id": f"asset-{uuid.uuid4().hex}", "project_id": project_id, "kind": kind, "media": [],
        }
        if voice_text is not None:
            if len(voice_text) > 10000:
                raise ValueError("声音对应文字不能超过10000个字符")
            for media in asset["media"]:
                if media.get("role") == "character_voice":
                    media["transcript"] = voice_text.strip()
        asset.update(name=name.strip(), kind=kind, description=description.strip())
        asset.pop("media_json", None)
        self.context.db.save_project_asset(asset)
        return asset

    def _root(self, project_id: str, asset_id: str) -> Path:
        project = self.context.db.project(project_id)
        root = self.projects.ensure_directory(project)
        target = (root / "public-assets" / asset_id).resolve()
        if root not in target.parents:
            raise ValueError("公共资产目录无效")
        return target

    def attach(self, project_id: str, asset_id: str, source: str, role: str | None = None, transcript: str = "") -> dict:
        asset = self.get(project_id, asset_id)
        project_root = self.projects.ensure_directory(self.context.db.project(project_id))
        if source.startswith("upload:"):
            identifier = source.removeprefix("upload:")
            if not re.fullmatch(r"[a-f0-9]{32}", identifier):
                raise ValueError("上传标识无效")
            upload_root = self.context.paths.uploads.resolve()
            matches = [p for p in upload_root.glob(f"{identifier}.*") if p.is_file() and p.resolve().parent == upload_root]
            if len(matches) != 1:
                raise ValueError("上传文件不存在，请重新上传")
            original = matches[0]
        else:
            original = (self.projects.projects_root / source).resolve()
            if project_root not in original.parents or not original.is_file():
                raise ValueError("source 必须是当前项目素材库相对路径，或 upload:<upload_id>；不能直接传 job_id")
        suffix = original.suffix.lower()
        media_type = next((key for key, extensions in MEDIA_EXTENSIONS.items() if suffix in extensions), None)
        # Keep the historical default role for the starter character kind so
        # existing consumers can still identify a character board. Roles are
        # labels only; they do not impose media type or count limits.
        role = role or ("character_sheet" if asset["kind"] == "character" else "reference")
        if not media_type:
            raise ValueError("文件类型不受支持")
        if len(transcript) > 10000:
            raise ValueError("声音对应文字不能超过10000个字符")
        media_id = uuid.uuid4().hex
        root = self._root(project_id, asset_id)
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{media_id}{suffix}"
        # Copy rather than link: episode deletion and later edits cannot affect this archive.
        shutil.copy2(original, target)
        relative = target.relative_to(self.projects.projects_root).as_posix()
        media = {"id": media_id, "name": original.name, "path": relative,
                 "url": f"/v1/library/files/{urllib.parse.quote(relative)}",
                 "type": "image" if media_type == "images" else "video" if media_type == "videos" else "music" if asset["kind"] == "music" else "audio",
                 "media_type": mimetypes.guess_type(target.name)[0], "size": target.stat().st_size,
                 "role": role}
        if role == "character_voice":
            media["transcript"] = transcript.strip()
        asset["media"].append(media)
        try:
            self.context.db.save_project_asset(asset)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return asset

    def _check_usage(self, media: list[dict]) -> None:
        # Explicit URL references must be resolved before deleting; uploaded task snapshots are independent.
        needles = [value for item in media for value in (item["path"], item["url"])]
        import json
        for job in self.context.db.jobs(limit=None):
            request = json.dumps(job.get("request", {}), ensure_ascii=False)
            if any(value in request for value in needles):
                raise RuntimeError(f"资产仍被任务 {job['id']} 引用，请先处理该任务")
        for item in self.context.db.collaborations(limit=100000):
            request = json.dumps(item.get("request", {}), ensure_ascii=False)
            if any(value in request for value in needles):
                raise RuntimeError(f"资产仍被协作 {item['id']} 引用，请先处理该协作")

    def remove_media(self, project_id: str, asset_id: str, media_id: str) -> dict:
        asset = self.get(project_id, asset_id)
        media = next((item for item in asset["media"] if item["id"] == media_id), None)
        if not media:
            raise ValueError("资产文件不存在")
        self._check_usage([media])
        target = (self.projects.projects_root / media["path"]).resolve()
        if target.parent != self._root(project_id, asset_id):
            raise ValueError("资产文件目录无效")
        target.unlink(missing_ok=True)
        asset["media"] = [item for item in asset["media"] if item["id"] != media_id]
        self.context.db.save_project_asset(asset)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return asset

    def delete(self, project_id: str, asset_id: str) -> None:
        asset = self.get(project_id, asset_id)
        self._check_usage(asset["media"])
        root = self._root(project_id, asset_id)
        if root.is_dir():
            shutil.rmtree(root)
        self.context.db.delete_project_asset(project_id, asset_id)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])

    def delete_all(self, project_id: str) -> int:
        """Delete every public asset after validating all references first."""
        assets = self.list(project_id)
        media = [item for asset in assets for item in asset["media"]]
        self._check_usage(media)
        for asset in assets:
            root = self._root(project_id, asset["id"])
            if root.is_dir():
                shutil.rmtree(root)
            self.context.db.delete_project_asset(project_id, asset["id"])
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return len(assets)
