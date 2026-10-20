# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from __future__ import annotations
import json
from pathlib import Path
import re
import shutil
import sqlite3
import uuid
from typing import Any


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
        from ...integrations.system_services import LocalStorageProvider
        self.storage = getattr(context, "storage_provider", None) or LocalStorageProvider(
            self._configured_projects_root
        )

    def _configured_projects_root(self) -> Path:
        configured = self.context.db.settings().get("resource_directory", "").strip()
        return Path(configured).expanduser().resolve() if configured else self.context.paths.projects.resolve()

    @property
    def projects_root(self) -> Path:
        return self.storage.root

    @staticmethod
    def _directory_name(name: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(". ")
        value = re.sub(r"\s+", " ", value)
        if not value:
            raise ValueError("项目名称不能为空")
        if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", value.split('.')[0].rstrip(), re.IGNORECASE):
            raise ValueError("项目名称不能使用 Windows 保留名称，如 CON、NUL、COM1")
        return value[:80]

    def ensure_directory(self, project: dict[str, Any]) -> Path:
        directory = self.storage.ensure_directory(str(project["output_subdir"]))
        for child in set(MEDIA_DIRECTORIES.values()):
            (directory / child).mkdir(parents=True, exist_ok=True)
        return directory

    def create(self, name: str, description: str = "", content_summary: str = "", *, ai_created: bool = False) -> dict[str, Any]:
        display_name = name.strip()
        directory = self._directory_name(display_name)
        existing = {str(item["output_subdir"]).casefold() for item in self.context.db.projects(True)}
        base = directory
        suffix = 2
        while directory.casefold() in existing:
            directory = f"{base}-{suffix}"
            suffix += 1
        values = {
            "id": f"project-{uuid.uuid4().hex[:12]}",
            "name": display_name,
            "output_subdir": directory,
            "description": description.strip(),
            "content_summary": content_summary.strip(),
            "ai_created": bool(ai_created),
        }
        output = self.ensure_directory(values)
        try:
            project = self.context.db.create_project(values)
            return project
        except Exception:
            # Remove only empty directories created before the failed insert.
            for child in set(MEDIA_DIRECTORIES.values()):
                try:
                    (output / child).rmdir()
                except OSError:
                    pass
            try:
                output.rmdir()
            except OSError:
                pass
            raise

    def list(self, include_archived: bool = False) -> list[dict[str, Any]]:
        projects = self.context.db.projects(include_archived)
        # The legacy unassigned bucket is an internal migration fallback, not a
        # user-facing project. Keep it available to existing jobs and the current project endpoint.
        # recovery, but never expose it as a selectable project.
        for project in projects:
            directory = self.ensure_directory(project)
            project["output_path"] = str(directory)
            project["asset_count"] = len(self.storage.list_files(str(project["output_subdir"])))
        return projects

    def categories(self, project_id: str) -> list[dict[str, Any]]:
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        return [{"id": "", "project_id": project_id, "name": "默认分类"}, *self.context.db.project_categories(project_id)]

    def validate_category(self, project_id: str, category_id: str | None) -> str:
        value = category_id or ""
        if not any(item["id"] == value for item in self.categories(project_id)):
            raise ValueError("分类不存在或不属于当前项目")
        return value

    def save_category(self, project_id: str, name: str, category_id: str | None = None) -> dict[str, str]:
        self.categories(project_id)
        name = name.strip()
        if not name or len(name) > 80 or name in {"默认分类", "公共资产", "全部素材"}:
            raise ValueError("分类名称须为1至80个字符，且不能使用系统入口名称")
        if category_id is not None:
            if not category_id:
                raise ValueError("默认分类不能修改")
            self.validate_category(project_id, category_id)
        identifier = category_id or f"category-{uuid.uuid4().hex[:12]}"
        try:
            self.context.db.save_category(project_id, identifier, name, create=category_id is None)
        except sqlite3.IntegrityError as exc:
            raise ValueError("分类名称已存在") from exc
        return {"id": identifier, "project_id": project_id, "name": name}

    def delete_category(self, project_id: str, category_id: str) -> None:
        if not category_id:
            raise ValueError("默认分类不能删除")
        self.validate_category(project_id, category_id)
        if any(job.get("project_id") == project_id and job.get("category_id") == category_id
               and (job.get("status") in {"queued", "running"}
                    or job['id'] in getattr(self.context, 'executing_jobs', set()))
               for job in getattr(self.context, "jobs", {}).values()):
            raise RuntimeError("分类仍有生成任务，请先完成或取消")
        # Keep pending collaborations bound to their original category until submission.
        if any(item.get("status") in {"queued", "running", "awaiting_confirmation", "needs_input"}
               and (item.get("request", {}).get("category_id") == category_id
                    or item.get("request", {}).get("params", {}).get("_category_id") == category_id)
               for item in self._project_collaborations(project_id)):
            raise RuntimeError("分类仍有智能协作任务，请先完成或取消")
        jobs = {job['id']: job for job in self.context.db.jobs(limit=None, project_id=project_id)
                if job.get('category_id') == category_id}
        jobs.update({job['id']: job for job in getattr(self.context, 'jobs', {}).values()
                     if job.get('project_id') == project_id and job.get('category_id') == category_id})
        if any(job.get('status') in {'queued', 'running'} or job['id'] in getattr(self.context, 'executing_jobs', set()) for job in jobs.values()):
            raise RuntimeError("分类仍有生成任务，请先完成或取消")
        if any(job.get('parent_job_id') in jobs and (job.get('status') in {'queued', 'running'}
               or job['id'] in getattr(self.context, 'executing_jobs', set()))
               for job in self.context.db.jobs(limit=None)):
            raise RuntimeError("分类素材仍有二采任务运行，请先完成或取消")
        self._check_application_tasks(project_id)
        self.check_application_references(project_id, set(jobs))
        plugins_path = getattr(self.context.paths, "plugins", None)
        if plugins_path:
            from ..generation.plugins import PluginCatalog
            catalog = PluginCatalog(plugins_path, self.context)
            catalog.application_event(
                "category_delete", self.context, project_id=project_id, category_id=category_id
            )
            self._delete_plugin_category_directories(project_id, category_id, catalog)
        names = {name for job_id in jobs for name in self.context.db.artifact_names(job_id)}
        for job in jobs.values():
            names.update(item['name'] for item in job.get('artifacts', []) if item.get('name'))
            if job.get('artifact_name'):
                names.add(job['artifact_name'])
        paths = self._artifact_paths(names, jobs)
        for job in jobs.values():
            self.delete_job_published(job)
            self._delete_task_package(job)
            self.context.db.delete_job(job['id'])
            getattr(self.context, 'jobs', {}).pop(job['id'], None)
        for path in paths:
            path.unlink(missing_ok=True)
        self.context.db.delete_category(project_id, category_id)

    def library_categories(self, project_id: str) -> dict[str, str]:
        result = {}
        project = self.context.db.project(project_id)
        for job in self.context.db.jobs(limit=None, project_id=project_id):
            for index, artifact in enumerate(job.get("artifacts") or []):
                path = artifact.get("project_path")
                if not path and project:
                    suffix = Path(str(artifact.get("name") or artifact.get("url") or "")).suffix
                    directory = MEDIA_DIRECTORIES.get(job.get("kind"), "images")
                    path = f"{project['output_subdir']}/{directory}/{job['id']}_{index}{suffix}"
                if path:
                    result[path] = job.get("category_id") or ""
        return result

    def current(self) -> dict[str, Any]:
        project = self.context.db.current_project()
        if not project or project.get("status") != "active":
            raise ValueError("当前尚未选择项目，请先创建或选择项目")
        project["output_path"] = str(self.ensure_directory(project))
        return project

    def select(self, project_id: str) -> dict[str, Any]:
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        selected = self.context.db.set_current_project(project_id)
        if not selected:
            raise RuntimeError("无法切换项目")
        selected["output_path"] = str(self.ensure_directory(selected))
        return selected

    def authorize(self, project_id: str) -> dict[str, Any]:
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        return project

    def authorize_library_path(self, path: Path) -> dict[str, Any]:
        project = next((item for item in self.context.db.projects(True)
                        if item.get("output_subdir") == path.parts[0]), None) if path.parts else None
        if not project:
            raise ValueError("素材文件不存在")
        return self.authorize(project["id"])

    def update(self, project_id: str, name: str, description: str | None = None, content_summary: str | None = None) -> dict[str, Any]:
        project = self.context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise ValueError("项目不存在或已归档")
        display_name = name.strip()
        self._directory_name(display_name)
        changes = {"name": display_name}
        if description is not None:
            changes["description"] = description.strip()
        if content_summary is not None:
            changes["content_summary"] = content_summary.strip()
        result = self.context.db.update_project(project_id, changes)
        if not result:
            raise ValueError("项目不存在")
        result["output_path"] = str(self.ensure_directory(result))
        return result

    def delete(self, project_id: str) -> list[dict[str, str]]:
        project = self.context.db.project(project_id)
        if not project:
            raise ValueError("项目不存在")
        jobs = self.context.db.jobs(limit=None, project_id=project_id)
        self.context.db.check_plugin_references(project_id)
        jobs_by_id = {str(job["id"]): job for job in jobs if job.get("id")}
        task_dirs: dict[str, Path] = {}
        self._collect_manifest_jobs(project_id, jobs_by_id, task_dirs)
        for job in getattr(self.context, "jobs", {}).values():
            if isinstance(job, dict) and str(job.get("project_id", "")) == project_id and job.get("id"):
                jobs_by_id.setdefault(str(job["id"]), job)
        jobs = list(jobs_by_id.values())
        if any(job.get("status") in {"queued", "running"} or job['id'] in getattr(self.context, 'executing_jobs', set()) for job in jobs):
            raise RuntimeError("项目仍有任务正在生成，请先取消任务")

        collaborations = self._project_collaborations(project_id)
        # A project may be deleted together with stale conversations waiting
        # for user input/confirmation. Only work that can still execute in the
        # background must block deletion; the collaboration rows are removed
        # with the project below.
        active_collaborations = {"queued", "running"}
        if any(item.get("status") in active_collaborations for item in collaborations):
            raise RuntimeError("项目仍有智能协作任务，请先完成或取消任务")
        self._check_application_tasks(project_id)

        plugins_path = getattr(self.context.paths, "plugins", None)
        if plugins_path:
            from ..generation.plugins import PluginCatalog
            PluginCatalog(plugins_path, self.context).application_event(
                "project_delete", self.context, project_id=project_id
            )

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
        cleanup_warnings = []
        for job in jobs:
            cleanup_warnings.extend(self.delete_job_published(job))
            self._delete_task_package(job, task_dirs.get(str(job.get("id", ""))))
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        for collaboration_id in collaboration_ids:
            self._delete_collaboration_directory(collaboration_id)
        self.storage.delete_prefix(str(project["output_subdir"]))
        self.context.db.delete_project(project_id)
        for collaboration_id in collaboration_ids:
            self.context.db.delete_collaboration(collaboration_id)
        runtime_jobs = getattr(self.context, "jobs", None)
        if isinstance(runtime_jobs, dict):
            for job in jobs:
                runtime_jobs.pop(job["id"], None)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return cleanup_warnings
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

    def _check_application_tasks(self, project_id: str) -> None:
        tasks = getattr(self.context, "application_tasks", {})
        if any(isinstance(key, tuple) and len(key) > 1 and key[1] == project_id
               and not task.done() for key, task in tasks.items()):
            raise RuntimeError("项目仍有插件应用任务运行，请先完成或取消")

    def _delete_plugin_category_directories(self, project_id: str, category_id: str, catalog) -> None:
        project = self.context.db.project(project_id)
        if not project:
            return
        root = self.ensure_directory(project).resolve()
        for plugin in catalog.scan()[0]:
            target = (root / ".plugins" / plugin["id"] / "categories" / category_id).resolve()
            if root in target.parents and target.is_dir():
                shutil.rmtree(target)

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

    def check_application_references(self, project_id: str, job_ids: set[str]) -> None:
        self.context.db.check_plugin_references(project_id, job_ids)

    def delete_job_published(self, job: dict[str, Any]) -> list[dict[str, str]]:
        project_id = job.get('project_id')
        if project_id:
            self.check_application_references(project_id, {job['id']})
        from ..generation.plugins import PluginCatalog
        cleanup_warnings = []
        if getattr(self.context.paths, "plugins", None):
            cleanup_warnings = PluginCatalog(self.context.paths.plugins, self.context).resource_event(
                "delete", self.context, job=job
            ) or []
        artifacts = job.get("artifacts") or []
        self.delete_published(artifacts)
        project = self.context.db.project(project_id) if project_id else None
        if not project:
            return
        job_id = str(job.get("id") or "")
        # Older records omitted project_path. The job prefix is deterministic and
        # limited to the project's own media directories.
        if job_id:
            for directory in set(MEDIA_DIRECTORIES.values()):
                for item in self.storage.list_files(f"{project['output_subdir']}/{directory}"):
                    if Path(item.key).name.startswith(f"{job_id}_"):
                        self.storage.delete(item.key)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return cleanup_warnings
    def resolve_job_project(self, parent_job_id: str | None = None) -> dict[str, Any]:
        if parent_job_id:
            parent = self.context.db.job(str(parent_job_id))
            if parent and parent.get("project_id"):
                project = self.context.db.project(parent["project_id"])
                if project:
                    return project
        return self.current()

    def output_prefix(self, job: dict[str, Any], media_kind: str) -> str:
        project = self.context.db.project(job.get("project_id")) if job.get("project_id") else None
        if not project:
            raise ValueError("生成任务必须属于一个项目")
        directory = MEDIA_DIRECTORIES.get(media_kind, "images")
        return f"projects/{project['output_subdir']}/{directory}/{job['id']}"

    def publish(self, job: dict[str, Any], paths: list[Path]) -> list[dict[str, str]]:
        project = self.context.db.project(job.get("project_id")) if job.get("project_id") else None
        if not project:
            raise ValueError("生成任务必须属于一个项目")
        media_kind = job.get("kind", "image")
        output_dir = f"{project['output_subdir']}/{MEDIA_DIRECTORIES.get(media_kind, 'images')}"
        published = []
        for index, source in enumerate(paths):
            filename = f"{job['id']}_{index}{source.suffix.lower()}"
            relative = f"{output_dir}/{filename}"
            self.storage.put_file(source, relative, link_if_possible=True)
            published.append({"path": str(self.storage.local_path(relative)), "relative_path": relative})
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
        return published

    def delete_published(self, artifacts: list[dict[str, Any]]) -> None:
        for artifact in artifacts:
            relative = str(artifact.get("project_path") or "").strip()
            if not relative:
                continue
            self.storage.delete(relative)
        self.context.library_cache.update(directory="", created_at=0.0, items=[])
