from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import uuid
from typing import Any


UNASSIGNED_PROJECT_ID = "project-unassigned"
DEFAULT_WORKSPACE_ID = "studio-default"
MEDIA_DIRECTORIES = {
    "image": "images",
    "video": "videos",
    "audio": "audio",
    "tts": "audio",
    "music": "music",
}
MEDIA_EXTENSIONS = {
    "images": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "videos": {".mp4", ".webm", ".mov", ".mkv"},
    "audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a"},
}


class ProjectService:
    def __init__(self, context: Any):
        self.context = context

    @property
    def projects_root(self) -> Path:
        return self.context.paths.projects.resolve()

    @staticmethod
    def normalize_workspace_id(value: str | None) -> str:
        candidate = str(value or DEFAULT_WORKSPACE_ID).strip()
        return candidate if re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", candidate) else DEFAULT_WORKSPACE_ID

    @staticmethod
    def _directory_name(name: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(". ")
        value = re.sub(r"\s+", " ", value)
        if not value:
            raise ValueError("项目名称不能为空")
        return value[:80]

    def ensure_directory(self, project: dict[str, Any]) -> Path:
        root = self.projects_root
        directory = (root / str(project["output_subdir"])).resolve()
        if directory.parent != root:
            raise ValueError("项目输出目录无效")
        for child in set(MEDIA_DIRECTORIES.values()):
            (directory / child).mkdir(parents=True, exist_ok=True)
        return directory

    def create(self, name: str, description: str = "", content_summary: str = "") -> dict[str, Any]:
        display_name = name.strip()
        directory = self._directory_name(display_name)
        existing = {str(item["output_subdir"]).casefold() for item in self.context.db.projects(True)}
        base = directory
        suffix = 2
        while directory.casefold() in existing:
            directory = f"{base}-{suffix}"
            suffix += 1
        project = self.context.db.create_project({
            "id": f"project-{uuid.uuid4().hex[:12]}",
            "name": display_name,
            "output_subdir": directory,
            "description": description.strip(),
            "content_summary": content_summary.strip(),
        })
        self.ensure_directory(project)
        return project

    def list(self, include_archived: bool = False) -> list[dict[str, Any]]:
        projects = self.context.db.projects(include_archived)
        for project in projects:
            directory = self.ensure_directory(project)
            project["output_path"] = str(directory)
            project["asset_count"] = sum(1 for path in directory.rglob("*") if path.is_file())
        return projects

    def current(self, workspace_id: str | None) -> dict[str, Any]:
        workspace = self.normalize_workspace_id(workspace_id)
        project = self.context.db.current_project(workspace)
        if not project or project.get("status") != "active":
            project = self.context.db.project(UNASSIGNED_PROJECT_ID)
            if not project:
                raise RuntimeError("未归档项目尚未初始化")
            self.context.db.set_current_project(workspace, project["id"])
        project["output_path"] = str(self.ensure_directory(project))
        return project

    def select(self, workspace_id: str | None, project_id: str) -> dict[str, Any]:
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        selected = self.context.db.set_current_project(self.normalize_workspace_id(workspace_id), project_id)
        if not selected:
            raise RuntimeError("无法切换项目")
        selected["output_path"] = str(self.ensure_directory(selected))
        return selected

    def update(self, project_id: str, name: str, description: str = "", content_summary: str = "") -> dict[str, Any]:
        if project_id == UNASSIGNED_PROJECT_ID:
            raise ValueError("未归档项目不能修改")
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        display_name = name.strip()
        self._directory_name(display_name)
        result = self.context.db.update_project(project_id, {
            "name": display_name,
            "description": description.strip(),
            "content_summary": content_summary.strip(),
        })
        if not result:
            raise ValueError("项目不存在")
        result["output_path"] = str(self.ensure_directory(result))
        return result

    def delete(self, project_id: str) -> None:
        if project_id == UNASSIGNED_PROJECT_ID:
            raise ValueError("未归档项目不能删除")
        project = self.context.db.project(project_id)
        if not project:
            raise ValueError("项目不存在")
        jobs = self.context.db.jobs(limit=None, project_id=project_id)
        jobs_by_id = {str(job["id"]): job for job in jobs if job.get("id")}
        task_dirs: dict[str, Path] = {}
        self._collect_manifest_jobs(project_id, jobs_by_id, task_dirs)
        for job in getattr(self.context, "jobs", {}).values():
            if isinstance(job, dict) and str(job.get("project_id", "")) == project_id and job.get("id"):
                jobs_by_id.setdefault(str(job["id"]), job)
        jobs = list(jobs_by_id.values())
        if any(job.get("status") in {"queued", "running"} for job in jobs):
            raise RuntimeError("项目仍有任务正在生成，请先取消任务")

        collaborations = self._project_collaborations(project_id)
        # A project may be deleted together with stale conversations waiting
        # for user input/confirmation. Only work that can still execute in the
        # background must block deletion; the collaboration rows are removed
        # with the project below.
        active_collaborations = {"queued", "running"}
        if any(item.get("status") in active_collaborations for item in collaborations):
            raise RuntimeError("项目仍有智能协作任务，请先完成或取消任务")

        # Capture every file location before database rows are removed. Older
        # versions could delete rows while leaving their task packages behind.
        artifact_names = set()
        for job in jobs:
            artifact_names.update(
                str(item.get("name")) for item in job.get("artifacts", [])
                if isinstance(item, dict) and item.get("name")
            )
            if job.get("artifact_name"):
                artifact_names.add(str(job["artifact_name"]))
            artifact_names.update(self.context.db.artifact_names(str(job["id"])))
        artifact_paths = self._artifact_paths(artifact_names, jobs_by_id)
        collaboration_ids = [str(item["id"]) for item in collaborations if item.get("id")]
        for job in jobs:
            self.delete_job_published(job)
            self._delete_task_package(job, task_dirs.get(str(job.get("id", ""))))
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        for collaboration_id in collaboration_ids:
            self._delete_collaboration_directory(collaboration_id)
        project_dir = (self.projects_root / str(project["output_subdir"])).resolve()
        if self.projects_root in project_dir.parents and project_dir.is_dir():
            shutil.rmtree(project_dir)
        self.context.db.delete_project(project_id)
        for collaboration_id in collaboration_ids:
            self.context.db.delete_collaboration(collaboration_id)
        runtime_jobs = getattr(self.context, "jobs", None)
        if isinstance(runtime_jobs, dict):
            for job in jobs:
                runtime_jobs.pop(job["id"], None)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])

    def _collect_manifest_jobs(self, project_id: str, jobs: dict[str, dict[str, Any]], task_dirs: dict[str, Path]) -> None:
        tasks = getattr(self.context.paths, "tasks", None)
        if not tasks or not Path(tasks).is_dir():
            return
        for manifest_path in Path(tasks).rglob("manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(manifest.get("project_id", "")) != project_id:
                continue
            job_id = str(manifest.get("task_id", ""))
            if not job_id:
                continue
            task_dirs[job_id] = manifest_path.parent
            jobs.setdefault(job_id, {
                "id": job_id,
                "kind": manifest_path.parent.parent.name,
                "status": manifest.get("status", "completed"),
                "project_id": project_id,
                "artifacts": [],
            })

    def _project_collaborations(self, project_id: str) -> list[dict[str, Any]]:
        result = []
        for item in self.context.db.collaborations(limit=100000):
            if str(item.get("project_id", "")) == project_id:
                result.append(item)
                continue
            request = item.get("request") if isinstance(item.get("request"), dict) else {}
            if self._request_project_ids(request) & {project_id}:
                result.append(item)
        return result

    @classmethod
    def _request_project_ids(cls, value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key in ("project_id", "_project_id"):
                if value.get(key):
                    found.add(str(value[key]))
            for child in value.values():
                found.update(cls._request_project_ids(child))
        elif isinstance(value, list):
            for child in value:
                found.update(cls._request_project_ids(child))
        return found

    def _artifact_paths(self, names: set[str], jobs: dict[str, dict[str, Any]]) -> set[Path]:
        root = getattr(self.context.paths, "artifacts", None)
        if not root:
            return set()
        root = Path(root).resolve()
        paths: set[Path] = set()
        for name in names:
            target = (root / Path(name).name).resolve()
            if root in target.parents and target.is_file():
                paths.add(target)
        for job_id in jobs:
            for target in root.glob(f"{job_id}_*"):
                if target.is_file():
                    paths.add(target.resolve())
        return paths

    def _delete_collaboration_directory(self, collaboration_id: str) -> None:
        root = getattr(self.context.paths, "collaborations", None)
        if not root:
            return
        root = Path(root).resolve()
        target = (root / collaboration_id).resolve()
        if root in target.parents and target.is_dir():
            shutil.rmtree(target)

    def _delete_task_package(self, job: dict[str, Any], known_dir: Path | None = None) -> None:
        tasks = getattr(self.context.paths, "tasks", None)
        if not tasks:
            return
        task_dir = Path(known_dir or job.get("task_dir") or (Path(tasks) / job["kind"] / job["id"]))
        tasks_root = Path(tasks).resolve()
        target = task_dir.resolve()
        if tasks_root in target.parents and target.is_dir():
            shutil.rmtree(target)

    def delete_job_published(self, job: dict[str, Any]) -> None:
        artifacts = job.get("artifacts") or []
        self.delete_published(artifacts)
        project = self.context.db.project(job.get("project_id", UNASSIGNED_PROJECT_ID))
        if not project:
            return
        project_root = self.ensure_directory(project)
        job_id = str(job.get("id") or "")
        # Older records omitted project_path. The job prefix is deterministic and
        # limited to the project's own media directories.
        if job_id:
            for directory in set(MEDIA_DIRECTORIES.values()):
                media_dir = project_root / directory
                for target in media_dir.glob(f"{job_id}_*"):
                    if target.is_file():
                        target.unlink()
        self.context.library_cache.update(directory="", created_at=0.0, items=[])

    def resolve_job_project(self, workspace_id: str | None, parent_job_id: str | None = None) -> dict[str, Any]:
        if parent_job_id:
            parent = self.context.db.job(str(parent_job_id))
            if parent and parent.get("project_id"):
                project = self.context.db.project(parent["project_id"])
                if project:
                    return project
        return self.current(workspace_id)

    def output_prefix(self, job: dict[str, Any], media_kind: str) -> str:
        project = self.context.db.project(job.get("project_id", UNASSIGNED_PROJECT_ID))
        if not project:
            project = self.context.db.project(UNASSIGNED_PROJECT_ID)
        directory = MEDIA_DIRECTORIES.get(media_kind, "images")
        return f"projects/{project['output_subdir']}/{directory}/{job['id']}"

    def publish(self, job: dict[str, Any], paths: list[Path]) -> list[dict[str, str]]:
        project = self.context.db.project(job.get("project_id", UNASSIGNED_PROJECT_ID))
        if not project:
            project = self.context.db.project(UNASSIGNED_PROJECT_ID)
        project_root = self.ensure_directory(project)
        media_kind = job.get("kind", "image")
        output_dir = project_root / MEDIA_DIRECTORIES.get(media_kind, "images")
        published = []
        for index, source in enumerate(paths):
            filename = f"{job['id']}_{index}{source.suffix.lower()}"
            destination = output_dir / filename
            if source.resolve() != destination.resolve():
                temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
                try:
                    os.link(source, temporary)
                except OSError:
                    shutil.copy2(source, temporary)
                os.replace(temporary, destination)
            relative = destination.relative_to(self.projects_root).as_posix()
            published.append({"path": str(destination), "relative_path": relative})
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return published

    def delete_published(self, artifacts: list[dict[str, Any]]) -> None:
        root = self.projects_root
        for artifact in artifacts:
            relative = str(artifact.get("project_path") or "").strip()
            if not relative:
                continue
            target = (root / relative).resolve()
            if root in target.parents and target.is_file():
                target.unlink()
        self.context.library_cache.update(directory="", created_at=0.0, items=[])

    def import_legacy_assets(self) -> int:
        settings = self.context.db.settings()
        marker = "project_legacy_assets_imported_v1"
        if settings.get(marker) == "1":
            return 0
        project = self.context.db.project(UNASSIGNED_PROJECT_ID)
        if not project:
            return 0
        destination_root = self.ensure_directory(project)
        source_root = self.context.paths.artifacts.resolve()
        imported = 0
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            suffix = source.suffix.lower()
            category = next((name for name, extensions in MEDIA_EXTENSIONS.items() if suffix in extensions), None)
            if not category:
                continue
            relative = source.name
            target = destination_root / category / relative
            if target.exists():
                continue
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
            imported += 1
        self.context.db.save_settings({marker: "1"})
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return imported
