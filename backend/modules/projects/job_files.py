# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Licensed under AGPL-3.0; see LICENSE, NOTICE and COMMERCIAL_LICENSE.md.
"""Opaque plugin dependencies owned by projects, independent of worker caches."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import tempfile

from .service import ProjectService


class JobFiles:
    def __init__(self, runtime):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", runtime.plugin_id):
            raise ValueError("Invalid plugin identity")
        self.runtime = runtime
        self.context = runtime._context
        self.storage = ProjectService(self.context).storage
        self.lock = getattr(self.context, "job_file_lock", self.context.state_lock)

    def _job(self, job):
        identity = job if isinstance(job, str) else job["id"]
        value = self.context.db.job(identity)
        if not value or not value.get("project_id"):
            raise ValueError("Job file requires a persisted project job")
        if self.runtime.project_id and value["project_id"] != self.runtime.project_id:
            raise ValueError("Job belongs to another project")
        generation = value.get("request", {}).get("generation", {})
        owner = generation.get("plugin_id")
        if owner != self.runtime.plugin_id:
            raise ValueError("Job belongs to another plugin")
        return value

    @staticmethod
    def _name(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise ValueError("Invalid logical job file name")

    def get(self, job, name):
        value = self._job(job)
        self._name(name)
        return self.context.db.job_file(self.runtime.plugin_id, value["id"], name)

    @contextmanager
    def materialize(self, job, name):
        value = self.get(job, name)
        if not value:
            raise FileNotFoundError(name)
        with self.storage.materialize(value["object_key"]) as path:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if path.stat().st_size != value["size"] or digest.hexdigest() != value["sha256"]:
                raise ValueError("Archived job file failed integrity verification")
            yield path

    def save(self, job, name, *, source=None, output=None, metadata=None, sha256=None, size=None):
        value = self._job(job)
        self._name(name)
        if (source is None) == (output is None):
            raise ValueError("Supply exactly one local source or ComfyUI output descriptor")
        project = self.context.db.project(value["project_id"])
        # Spool to disk: native checkpoints can exceed available RAM.
        with tempfile.TemporaryFile() as staged:
            handle = Path(source).open("rb") if source is not None else self.context.comfyui_provider.open_output(output)
            digest, length = hashlib.sha256(), 0
            with handle as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    length += len(chunk)
                    staged.write(chunk)
            checksum = digest.hexdigest()
            if (sha256 is not None and checksum != sha256.lower()) or (size is not None and length != size):
                raise ValueError("Job file checksum or size mismatch")
            key = f"{project['output_subdir']}/.internal/files/{self.runtime.plugin_id}/{checksum}"
            record = dict(plugin_id=self.runtime.plugin_id, project_id=value["project_id"],
                          job_id=value["id"], name=name, object_key=key, sha256=checksum,
                          size=length, metadata=dict(metadata or {}))
            with self.lock:
                previous = self.get(job, name)
                if previous and previous["sha256"] != checksum:
                    raise ValueError("Job dependency is immutable; use a new logical name")
                staged.seek(0)
                self.storage.put_stream(staged, key)
                try:
                    self.context.db.save_job_file(record)
                except Exception:
                    if not self.context.db.job_file_referenced(key):
                        self.storage.delete(key)
                    raise
        return record

    def link(self, source_job, name, target_job):
        target = self._job(target_job)
        with self.lock:
            source = self.get(source_job, name)
            if not source or source["project_id"] != target["project_id"]:
                raise ValueError("Dependency must exist in the same project")
            previous = self.get(target_job, name)
            if previous and previous["sha256"] != source["sha256"]:
                raise ValueError("Job dependency is immutable")
            self.context.db.save_job_file({**source, "job_id": target["id"]})
        return self.get(target_job, name)

    def restore(self, job, name, relative, *, destination="output"):
        # Restore during the consuming job's execution. Its lifecycle protects
        # deletion; do not hold the global state lock across a large HTTP upload.
        with self.materialize(job, name) as path:
            return self.context.comfyui_provider.upload_file(path, relative, destination)


def delete_job_files(context, job_id):
    storage = ProjectService(context).storage
    with getattr(context, "job_file_lock", context.state_lock):
        records = context.db.job_files(job_id)
        for key in {record["object_key"] for record in records}:
            if not context.db.job_file_referenced(key, excluding_job=job_id):
                storage.delete(key)
        context.db.delete_job_files(job_id)
