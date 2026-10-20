# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path
    data: Path
    artifacts: Path
    projects: Path
    cache: Path
    tasks: Path
    collaborations: Path
    uploads: Path
    plugins: Path
    static_dist: Path
    legacy_settings: Path

    @classmethod
    def from_root(cls, root: Path) -> "ProjectPaths":
        root = root.resolve()
        data = Path(os.getenv("MEDIA_GATEWAY_DATA", root / "data")).resolve()
        cache = data / "cache"
        plugins = Path(os.getenv("MEDIA_GATEWAY_PLUGINS", root / "plugins")).resolve()
        return cls(
            root=root,
            data=data,
            artifacts=data / "artifacts",
            projects=data / "projects",
            cache=cache,
            tasks=data / "tasks",
            collaborations=data / "collaborations",
            uploads=cache / "uploads",
            plugins=plugins,
            static_dist=root / "static" / "dist",
            legacy_settings=data / "settings.json",
        )

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.artifacts,
            self.projects,
            self.uploads,
            self.tasks,
            self.collaborations,
            self.plugins,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    host: str
    port: int
    api_token: str
    max_text: int
    max_upload_bytes: int
    max_total_upload_bytes: int
    generation_concurrency: int
    max_queue_size: int
    max_agent_queue_size: int
    upload_max_age_seconds: int
    collaboration_max_age_seconds: int
    agent_timeout_seconds: int
    default_comfyui_url: str
    default_comfyui_output_dir: Path

    @classmethod
    def load(cls, paths: ProjectPaths) -> "EnvironmentConfig":
        return cls(
            host=os.getenv("MEDIA_GATEWAY_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=int(os.getenv("MEDIA_GATEWAY_PORT", "8765")),
            api_token=os.getenv("MEDIA_GATEWAY_TOKEN", ""),
            max_text=int(os.getenv("MAX_TEXT_LENGTH", "20000")),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            max_total_upload_bytes=int(os.getenv("MAX_TOTAL_UPLOAD_BYTES", str(300 * 1024 * 1024))),
            generation_concurrency=max(1, int(os.getenv("MEDIA_CONCURRENCY", "1"))),
            max_queue_size=max(1, int(os.getenv("MAX_QUEUE_SIZE", "20"))),
            max_agent_queue_size=max(1, int(os.getenv("MAX_AGENT_QUEUE_SIZE", "3"))),
            upload_max_age_seconds=max(3600, int(os.getenv("UPLOAD_MAX_AGE_SECONDS", "86400"))),
            collaboration_max_age_seconds=max(
                86400,
                int(os.getenv("COLLABORATION_MAX_AGE_SECONDS", str(30 * 86400))),
            ),
            agent_timeout_seconds=max(0, int(os.getenv("AGENT_TIMEOUT_SECONDS", "0"))),
            default_comfyui_url=os.getenv("COMFYUI_URL", "http://127.0.0.1:8189").rstrip("/"),
            default_comfyui_output_dir=Path(
                os.getenv("COMFYUI_OUTPUT_DIR", paths.data / "comfyui_output")
            ).resolve(),
        )
