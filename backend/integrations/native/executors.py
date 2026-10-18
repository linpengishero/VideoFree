"""Execution contracts for trusted plugin executors."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class NativeExecutionCancelled(Exception):
    pass


@dataclass
class NativeExecutionContext:
    job_id: str
    config: dict[str, Any]
    prompt: str
    references: list[str]
    params: dict[str, Any]
    api_key: str
    output_dir: Path
    media_loader: Callable[[str], tuple[bytes, str]]
    cancelled: Callable[[], bool]


@dataclass
class NativeExecutionResult:
    paths: list[Path]
    width: int | None = None
    height: int | None = None
