# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Project-scoped storage and managed tasks for installed application plugins."""
import asyncio
import re

from ..projects import ProjectService


class ApplicationRuntime:
    def __init__(self, context, plugin_id, project_id=None, category_id=None):
        self._context = context
        self.plugin_id = plugin_id
        self.project_id = project_id
        self.category_id = category_id

    @property
    def root(self):
        return self._context.paths.root

    @property
    def projects_root(self):
        return ProjectService(self._context).projects_root

    def project(self, project_id):
        if self.project_id is not None and project_id != self.project_id:
            raise ValueError('项目不属于当前调用')
        project = self._context.db.project(project_id)
        if not project:
            raise ValueError('项目不存在')
        return project

    def projects(self):
        return [self.project(self.project_id)] if self.project_id else self._context.db.projects(True)

    def categories(self, project_id=None):
        project_id = project_id or self.project_id
        if not project_id:
            raise ValueError('当前调用没有项目上下文')
        if self.project_id is not None and project_id != self.project_id:
            raise ValueError('项目不属于当前调用')
        from ..projects import ProjectService
        return ProjectService(self._context).categories(project_id)

    def category(self, project_id=None, category_id=None):
        project_id = project_id or self.project_id
        category_id = self.category_id if category_id is None else category_id
        if category_id is None:
            return None
        return next((item for item in self.categories(project_id) if item['id'] == category_id), None)

    def directory(self, project_id):
        project_root = ProjectService(self._context).ensure_directory(self.project(project_id))
        directory = (project_root / ".plugins" / self.plugin_id).resolve()
        if project_root not in directory.parents:
            raise ValueError("插件目录无效")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def resolve_library_path(self, project_id, relative_path, allowed_suffixes=None):
        """Resolve a project library asset without exposing the project root to plugins."""
        project = self.project(project_id)
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("素材路径无效")
        service = ProjectService(self._context)
        root = service.ensure_directory(project).resolve()
        try:
            path = service.storage.local_path(relative_path)
        except (ValueError, FileNotFoundError) as exc:
            raise ValueError("项目素材文件不存在") from exc
        if root not in path.parents:
            raise ValueError("项目素材文件不存在")
        if allowed_suffixes and path.suffix.lower() not in set(allowed_suffixes):
            raise ValueError("素材文件类型不符合用途")
        return path

    def upload_file(self, upload_id):
        """Server-trusted file for a browser upload referenced by its id."""
        if not isinstance(upload_id, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', upload_id):
            raise ValueError('上传引用无效')
        matches = sorted(self._context.paths.uploads.glob(f'{upload_id}.*'))
        if not matches:
            raise ValueError('上传文件不存在或已过期')
        return matches[0]

    def library(self, project_id=None, *, kind="all", offset=0, limit=None,
                sort="new", category_id=None):
        """List the project library through the framework-owned storage boundary."""
        project_id = project_id or self.project_id
        if not project_id:
            raise ValueError("当前调用没有项目上下文")
        if self.project_id is not None and project_id != self.project_id:
            raise ValueError("项目不属于当前调用")
        result = ProjectService(self._context).library(
            project_id, kind=kind, offset=offset, limit=limit, sort=sort,
            category_id=self.category_id if category_id is None else category_id,
        )
        result.pop("output_dir", None)
        return result

    def upload_exists(self, upload_id):
        """Check that an upload is a live gateway-issued reference without exposing its path."""
        if not isinstance(upload_id, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", upload_id):
            return False
        if not self._context.db.upload_exists(upload_id):
            return False
        upload_root = self._context.paths.uploads.resolve()
        matches = [path for path in upload_root.glob(f"{upload_id}.*")
                   if path.is_file() and not path.is_symlink() and path.resolve().parent == upload_root]
        return len(matches) == 1

    def import_upload(self, upload_id, *, project_id=None, name="", kind=None,
                      category_id=None):
        """Persist a browser upload as a project-library asset and return its handle."""
        project_id = project_id or self.project_id
        if not project_id:
            raise ValueError("当前调用没有项目上下文")
        if self.project_id is not None and project_id != self.project_id:
            raise ValueError("项目不属于当前调用")
        return ProjectService(self._context).import_upload(
            project_id, upload_id, name=name, kind=kind,
            category_id=self.category_id if category_id is None else category_id,
        )

    def category_directory(self, project_id=None, category_id=None):
        project_id = project_id or self.project_id
        category_id = self.category_id if category_id is None else category_id
        if category_id is None:
            raise ValueError("当前调用没有分类上下文")
        self.category(project_id, category_id)
        directory = (self.directory(project_id) / "categories" / category_id).resolve()
        if self.directory(project_id) not in directory.parents:
            raise ValueError("插件分类目录无效")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def job(self, job_id):
        job = self._context.db.job(job_id)
        if job and (self.project_id is None or job.get('project_id') == self.project_id):
            return job
        return None

    def jobs(self, project_id):
        self.project(project_id)
        return self._context.db.jobs(limit=None, project_id=project_id)

    def selected(self):
        return self._context.db.plugin_job_marks(self.plugin_id)

    def mark(self, job_id, selected):
        if not self.job(job_id):
            raise ValueError('素材不存在或不属于当前项目')
        self._context.db.mark_plugin_job(self.plugin_id, job_id, selected)

    def documents(self, project_id=None, category_id=None):
        project_id = project_id or self.project_id
        if not project_id:
            raise ValueError('当前调用没有项目上下文')
        self.project(project_id)
        category_id = self.category_id if category_id is None else category_id
        if category_id is not None and not self.category(project_id, category_id):
            raise ValueError('分类不存在或不属于当前项目')
        return self._context.db.plugin_documents(self.plugin_id, project_id, category_id)

    def document(self, project_id, document_id, category_id=None):
        project_id = project_id or self.project_id
        if not project_id:
            raise ValueError('当前调用没有项目上下文')
        self.project(project_id)
        category_id = self.category_id if category_id is None else category_id
        if category_id is not None and not self.category(project_id, category_id):
            raise ValueError('分类不存在或不属于当前项目')
        return self._context.db.plugin_document(self.plugin_id, project_id, document_id, category_id)

    def save(self, document, references, active=False, selected_job_id=None):
        document = dict(document)
        document.setdefault('schema_version', 1)
        self.project(document['project_id'])
        category_id = document.get('category_id', self.category_id)
        if category_id is not None and not self.category(document['project_id'], category_id):
            raise ValueError('分类不存在或不属于当前项目')
        if self.category_id is not None and category_id != self.category_id:
            raise ValueError('文档不属于当前分类')
        document['category_id'] = category_id or ''
        self._context.db.save_plugin_document(self.plugin_id, document, references, active, selected_job_id)

    def delete(self, project_id, document_id, category_id=None):
        self.project(project_id)
        category_id = self.category_id if category_id is None else category_id
        if category_id is not None and not self.category(project_id, category_id):
            raise ValueError('分类不存在或不属于当前项目')
        self._context.db.delete_plugin_document(self.plugin_id, project_id, document_id, category_id)

    def invalidate_library(self):
        self._context.library_cache.update(directory='', created_at=0.0, items=[])

    def start(self, key, coroutine):
        key = (self.plugin_id, self.project_id, key)
        if key in self._context.application_tasks:
            coroutine.close()
            raise RuntimeError('应用任务已经运行')
        task = asyncio.create_task(coroutine, name=f'app-{self.plugin_id}-{key[-1]}')
        self._context.application_tasks[key] = task
        task.add_done_callback(lambda finished: self._context.application_tasks.pop(key, None))
        return task

    def cancel(self, key):
        """Cancel one background task owned by this plugin and project."""
        task = self._context.application_tasks.get((self.plugin_id, self.project_id, key))
        if not task or task.done():
            return False
        task.cancel()
        return True

    def semaphore(self):
        return self._context.application_semaphores.setdefault(self.plugin_id, asyncio.Semaphore(1))
