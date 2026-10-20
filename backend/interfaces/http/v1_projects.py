# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...bootstrap import context
from ...modules.projects import ProjectService
from ...modules.projects.assets import PublicAssetService
from .dependencies import auth


router = APIRouter()
service = ProjectService(context)

def _authorized(project_id: str) -> dict:
    try:
        return service.authorize(project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
assets = PublicAssetService(context)


class PublicAssetWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=10000)
    voice_text: str | None = Field(default=None, max_length=10000)


class PublicAssetMedia(BaseModel):
    source: str = Field(min_length=1, max_length=2000)
    role: str | None = None
    transcript: str = Field(default="", max_length=10000)


class PublicAssetTypeWrite(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=1000)


@router.get("/v1/projects/{project_id}/public-assets", dependencies=[Depends(auth)])
async def public_assets(project_id: str):
    _authorized(project_id)
    try:
        return {"items": assets.list(project_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/v1/projects/{project_id}/public-asset-types", dependencies=[Depends(auth)])
async def public_asset_types(project_id: str):
    _authorized(project_id)
    try:
        return {"items": assets.list_types(project_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/projects/{project_id}/public-asset-types", status_code=201, dependencies=[Depends(auth)])
async def create_public_asset_type(project_id: str, request: PublicAssetTypeWrite):
    _authorized(project_id)
    try:
        return assets.save_type(project_id, request.name, request.description)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/projects/{project_id}/public-assets", status_code=201, dependencies=[Depends(auth)])
async def create_public_asset(project_id: str, request: PublicAssetWrite):
    _authorized(project_id)
    try:
        return assets.save(project_id, request.name, request.kind, request.description, voice_text=request.voice_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/v1/projects/{project_id}/public-assets/{asset_id}", dependencies=[Depends(auth)])
async def update_public_asset(project_id: str, asset_id: str, request: PublicAssetWrite):
    _authorized(project_id)
    try:
        return assets.save(project_id, request.name, request.kind, request.description, asset_id, request.voice_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/projects/{project_id}/public-assets/{asset_id}/media", dependencies=[Depends(auth)])
async def attach_public_asset_media(project_id: str, asset_id: str, request: PublicAssetMedia):
    _authorized(project_id)
    try:
        return assets.attach(project_id, asset_id, request.source, request.role, request.transcript)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/v1/projects/{project_id}/public-assets/{asset_id}/media/{media_id}", dependencies=[Depends(auth)])
async def remove_public_asset_media(project_id: str, asset_id: str, media_id: str):
    _authorized(project_id)
    try:
        return assets.remove_media(project_id, asset_id, media_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, "素材文件清理失败，请检查文件占用或目录权限后重试") from exc


@router.delete("/v1/projects/{project_id}/public-assets/{asset_id}", dependencies=[Depends(auth)])
async def delete_public_asset(project_id: str, asset_id: str):
    _authorized(project_id)
    try:
        assets.delete(project_id, asset_id)
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/v1/projects/{project_id}/public-assets", dependencies=[Depends(auth)])
async def delete_public_assets(project_id: str):
    _authorized(project_id)
    try:
        return {"deleted": assets.delete_all(project_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    content_summary: str = Field(default="", max_length=3000)
    ai_created: bool = False


class ProjectSelect(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500, description="Omit or pass null to preserve; an empty string clears the field.")
    content_summary: str | None = Field(default=None, max_length=3000, description="Omit or pass null to preserve; an empty string clears the field.")


class CategoryWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/v1/projects/{project_id}/categories", dependencies=[Depends(auth)])
async def categories(project_id: str):
    _authorized(project_id)
    try:
        return {"items": service.categories(project_id)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/projects/{project_id}/categories", status_code=201, dependencies=[Depends(auth)])
async def create_category(project_id: str, request: CategoryWrite):
    _authorized(project_id)
    try:
        return service.save_category(project_id, request.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/v1/projects/{project_id}/categories/{category_id}", dependencies=[Depends(auth)])
async def rename_category(project_id: str, category_id: str, request: CategoryWrite):
    _authorized(project_id)
    try:
        return service.save_category(project_id, request.name, category_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/v1/projects/{project_id}/categories/{category_id}", dependencies=[Depends(auth)])
async def delete_category(project_id: str, category_id: str):
    _authorized(project_id)
    try:
        service.delete_category(project_id, category_id)
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/v1/projects", dependencies=[Depends(auth)])
async def projects(include_archived: bool = False):
    return {"items": service.list(include_archived)}


@router.post("/v1/projects", status_code=201, dependencies=[Depends(auth)])
async def create_project(request: ProjectCreate):
    try:
        project = service.create(request.name, request.description, request.content_summary, ai_created=request.ai_created)
        service.select(project["id"])
        return project
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/v1/projects/current", dependencies=[Depends(auth)])
async def current_project():
    try:
        return service.current()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/v1/projects/current", dependencies=[Depends(auth)])
async def select_project(request: ProjectSelect):
    try:
        return service.select(request.project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/v1/projects/{project_id}", dependencies=[Depends(auth)])
async def update_project(project_id: str, request: ProjectUpdate):
    _authorized(project_id)
    try:
        return service.update(project_id, request.name, request.description, request.content_summary)
    except ValueError as exc:
        message = str(exc)
        status = 409 if "不能" in message else 404 if "不存在" in message else 422
        raise HTTPException(status, message) from exc


@router.delete("/v1/projects/{project_id}", dependencies=[Depends(auth)])
async def delete_project(project_id: str):
    _authorized(project_id)
    try:
        warnings = service.delete(project_id)
        return {"id": project_id, "deleted": True, "cleanup_warnings": warnings}
    except ValueError as exc:
        raise HTTPException(409 if "不能" in str(exc) else 404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(409, "项目文件清理失败，请检查文件占用或目录权限后重试") from exc
