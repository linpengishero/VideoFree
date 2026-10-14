from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...bootstrap import context
from ...modules.projects import ProjectService, UNASSIGNED_PROJECT_ID
from .dependencies import auth


router = APIRouter()
service = ProjectService(context)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    content_summary: str = Field(default="", max_length=3000)


class ProjectSelect(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    content_summary: str = Field(default="", max_length=3000)


@router.get("/v1/projects", dependencies=[Depends(auth)])
async def projects(include_archived: bool = False):
    return {"items": service.list(include_archived)}


@router.post("/v1/projects", status_code=201, dependencies=[Depends(auth)])
async def create_project(request: ProjectCreate):
    try:
        project = service.create(request.name, request.description, request.content_summary)
        service.select(context.current_workspace_id.get(), project["id"])
        return project
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/v1/workspace/current-project", dependencies=[Depends(auth)])
async def current_project():
    return service.current(context.current_workspace_id.get())


@router.put("/v1/workspace/current-project", dependencies=[Depends(auth)])
async def select_project(request: ProjectSelect):
    try:
        return service.select(context.current_workspace_id.get(), request.project_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/v1/projects/{project_id}/archive", dependencies=[Depends(auth)])
async def archive_project(project_id: str):
    if project_id == UNASSIGNED_PROJECT_ID:
        raise HTTPException(409, "未归档项目不能归档")
    project = context.db.project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    result = context.db.archive_project(project_id)
    service.select(context.current_workspace_id.get(), UNASSIGNED_PROJECT_ID)
    return result


@router.put("/v1/projects/{project_id}", dependencies=[Depends(auth)])
async def update_project(project_id: str, request: ProjectUpdate):
    try:
        return service.update(project_id, request.name, request.description, request.content_summary)
    except ValueError as exc:
        message = str(exc)
        status = 409 if "不能" in message else 404 if "不存在" in message else 422
        raise HTTPException(status, message) from exc


@router.delete("/v1/projects/{project_id}", dependencies=[Depends(auth)])
async def delete_project(project_id: str):
    try:
        service.delete(project_id)
        return {"id": project_id, "deleted": True}
    except ValueError as exc:
        raise HTTPException(409 if "不能" in str(exc) else 404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
