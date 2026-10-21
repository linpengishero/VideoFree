# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Framework-owned storage provider contract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol


@dataclass(frozen=True, slots=True)
class StorageObject:
    key: str
    size: int
    modified_at: float


class StorageProviderError(RuntimeError):
    """A storage operation could not complete without risking data loss."""


class StorageProvider(Protocol):
    @property
    def root(self) -> Path: ...

    def ensure_directory(self, key: str) -> Path: ...
    def local_path(self, key: str) -> Path: ...
    def open(self, key: str) -> BinaryIO: ...
    def put_stream(self, source: BinaryIO, key: str) -> StorageObject: ...
    def put_file(self, source: Path, key: str, *, link_if_possible: bool = False) -> StorageObject: ...
    def delete(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> int: ...
    def list_files(self, prefix: str = "") -> list[StorageObject]: ...
    def materialize(self, key: str) -> Iterator[Path]: ...
