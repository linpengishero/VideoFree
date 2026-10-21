# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Local filesystem implementation of the project-library storage contract."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
from typing import BinaryIO, Callable, Iterator
import uuid

from .protocol import StorageObject, StorageProviderError


class LocalStorageProvider:
    def __init__(self, root: Path | Callable[[], Path]):
        self._root = root

    @property
    def root(self) -> Path:
        value = self._root() if callable(self._root) else self._root
        return Path(value).expanduser().resolve()

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("storage key must be a non-empty relative path")
        normalized = key.replace("\\", "/")
        candidate = Path(normalized)
        if (candidate.is_absolute() or ":" in normalized
                or any(part in {"", ".", ".."} for part in normalized.split("/"))):
            raise ValueError("storage key must remain inside the storage root")
        root = self.root
        target = (root / Path(*normalized.split("/"))).resolve()
        if not target.is_relative_to(root):
            raise ValueError("storage key must remain inside the storage root")
        return target

    def ensure_directory(self, key: str) -> Path:
        path = self._path(key)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def local_path(self, key: str) -> Path:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def open(self, key: str) -> BinaryIO:
        return self.local_path(key).open("rb")

    def put_stream(self, source: BinaryIO, key: str) -> StorageObject:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return self._metadata(destination)

    def put_file(self, source: Path, key: str, *, link_if_possible: bool = False) -> StorageObject:
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source != destination:
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                if link_if_possible:
                    try:
                        os.link(source, temporary)
                    except OSError:
                        shutil.copy2(source, temporary)
                else:
                    shutil.copy2(source, temporary)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return self._metadata(destination)

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.is_file():
            return False
        try:
            path.unlink()
        except OSError as exc:
            raise self._delete_error(exc) from exc
        return True

    def delete_prefix(self, prefix: str) -> int:
        path = self._path(prefix)
        if path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                raise self._delete_error(exc) from exc
            return 1
        if not path.is_dir():
            return 0
        files = [item for item in path.rglob("*") if item.is_file()]
        try:
            for item in files:
                item.unlink()
            shutil.rmtree(path)
        except OSError as exc:
            raise self._delete_error(exc) from exc
        return len(files)

    def list_files(self, prefix: str = "") -> list[StorageObject]:
        base = self.root if not prefix else self._path(prefix)
        if not base.exists():
            return []
        paths = [base] if base.is_file() else [item for item in base.rglob("*") if item.is_file()]
        return sorted((self._metadata(path) for path in paths), key=lambda item: item.key)

    @contextmanager
    def materialize(self, key: str) -> Iterator[Path]:
        """Provide a local path for tools such as FFmpeg that require one."""
        yield self.local_path(key)

    def _metadata(self, path: Path) -> StorageObject:
        stat = path.stat()
        return StorageObject(path.relative_to(self.root).as_posix(), stat.st_size, stat.st_mtime)

    @staticmethod
    def _delete_error(exc: OSError) -> StorageProviderError:
        return StorageProviderError(
            "文件清理未完成，部分文件可能已移除；请关闭占用文件的程序或检查目录权限后重试。"
        )
