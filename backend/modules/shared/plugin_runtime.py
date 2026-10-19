"""Stable system services exposed to trusted local plugin handlers."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.schemas import AgentChatRequest, GenerateRequest, TTSRequest
from ...core.errors import AgentCollaborationCancelled, GatewayError as PluginError

def apply_image_dimensions(*args, **kwargs):
    from ...integrations.comfyui.compiler import apply_image_dimensions as impl
    return impl(*args, **kwargs)
def apply_storyboard_grid(*args, **kwargs):
    from ...integrations.comfyui.compiler import apply_storyboard_grid as impl
    return impl(*args, **kwargs)
def fit_aligned_dimensions(*args, **kwargs):
    from ...integrations.comfyui.compiler import fit_aligned_dimensions as impl
    return impl(*args, **kwargs)
def apply_style(*args, **kwargs):
    from ..presets.style_library import apply_style as impl
    return impl(*args, **kwargs)
def parse_agent_json(*args, **kwargs):
    from ..collaboration.analysis import parse_agent_json as impl
    return impl(*args, **kwargs)
def parse_agent_result(*args, **kwargs):
    from ..collaboration.analysis import parse_agent_result as impl
    return impl(*args, **kwargs)
def normalized_agent_questions(*args, **kwargs):
    from ..collaboration.analysis import normalized_agent_questions as impl
    return impl(*args, **kwargs)
def agent_skill_prompt(*args, **kwargs):
    from ..collaboration.prompts import agent_skill_prompt as impl
    return impl(*args, **kwargs)


@dataclass(frozen=True, slots=True)
class PluginRuntime:
    plugin_id: str
    configuration: Mapping[str, Any]
    _context: Any
    project_id: str | None = None
    category_id: str | None = None
    _single: Callable[..., Any] | None = None
    _call_model: Callable[..., str] | None = None
    _submit: Callable[..., Any] | None = None
    _invoke_capability: Callable[..., Any] | None = None

    @property
    def application(self):
        from .application_runtime import ApplicationRuntime
        return ApplicationRuntime(self._context, self.plugin_id, self.project_id, self.category_id)

    async def single(self, request):
        """Run the platform's standard one-stage collaboration flow."""
        if self._single is None:
            raise RuntimeError("Collaboration service is unavailable for this action")
        return await self._single(request)

    async def execute_action(self, action_id: str, inputs: dict[str, Any], *, source_job_id=None,
                             project_id=None, category_id=None):
        """Run another registered plugin action through the platform dispatcher."""
        if not self._submit:
            raise RuntimeError("Plugin action dispatcher is unavailable")
        from ..generation.actions import execute_action
        from ..generation.plugins import PluginCatalog
        if self.project_id and project_id and self.project_id != project_id:
            raise ValueError("项目不属于当前调用")
        source = None
        if source_job_id:
            source = self._context.jobs.get(source_job_id) or self._context.db.job(source_job_id)
            if not source:
                raise ValueError("源任务不存在")
            if self.project_id and source.get("project_id") != self.project_id:
                raise ValueError("源任务不属于当前调用")
        return await execute_action(
            PluginCatalog(self._context.paths.plugins, self._context), action_id, inputs,
            self._context, self._submit, source=source, project_id=project_id or self.project_id,
            category_id=self.category_id if category_id is None else category_id,
            invoke_capability=self._invoke_capability,
        )

    async def invoke_capability(self, capability_id: str, prompt: str, *, inputs=None, settings=None,
                                parameters=None, lyrics="", parent_job_id=None, idempotency_key=None,
                                project_id=None, category_id=None):
        """Submit a registered capability through the platform generation contract."""
        if self._invoke_capability is None:
            raise RuntimeError("Plugin capability dispatcher is unavailable")
        if self.project_id and project_id and self.project_id != project_id:
            raise ValueError("项目不属于当前调用")
        target_project = project_id or self.project_id
        if not target_project:
            raise ValueError("当前调用没有项目上下文")
        return await self._invoke_capability({
            "capability_id": capability_id,
            "prompt": prompt,
            "lyrics": lyrics,
            "inputs": list(inputs or []),
            "settings": dict(settings or {}),
            "parameters": dict(parameters or {}),
            "parent_job_id": parent_job_id,
            "prompt_processing": "direct",
        }, project_id=target_project,
           category_id=self.category_id if category_id is None else category_id,
           idempotency_key=idempotency_key)

    def call_model(self, messages: list[dict[str, Any]], max_tokens: int = 2500) -> str:
        """Call the platform LLM without exposing its credentials to the plugin."""
        if self._call_model is None:
            raise RuntimeError("LLM service is unavailable for this action")
        return self._call_model(messages, max_tokens)

    def comfyui_request(self, path: str, method="GET", body: bytes | None = None):
        """Access the configured system ComfyUI adapter."""
        from ...bootstrap import comfyui_client
        return comfyui_client.request(path, method, body)

    def comfyui_upload(self, body: bytes, media_type: str, filename: str) -> str:
        """Upload a plugin-owned temporary input through the configured ComfyUI adapter."""
        from ...bootstrap import comfyui_client
        return comfyui_client.upload_input(body, media_type, filename)

    def job_request(self, job: dict[str, Any]) -> dict[str, Any]:
        """Read a durable job request without exposing the task-store layout."""
        from ..generation.task_store import TaskStore
        return TaskStore(self._context.paths.tasks, self._context.paths.uploads).hydrate(job)

    def jobs(self) -> list[dict[str, Any]]:
        return [job for job in self._context.db.jobs(limit=None)
                if self.project_id is None or job.get("project_id") == self.project_id]

    def update_job_parameters(self, job, parameters, **metadata):
        """Persist plugin result metadata to the job and its durable task package."""
        from ..generation.task_store import TaskStore
        store = TaskStore(self._context.paths.tasks, self._context.paths.uploads)
        request = dict(job.get("request") or {})
        request["params"] = {**request.get("params", {}), **parameters}
        job["request"] = request
        if job["id"] in self._context.jobs:
            self._context.jobs[job["id"]].update(request=request, **metadata)
        compact = {key: value for key, value in request.items() if key not in {"references", "reference_audio"}}
        compact["params"] = {key: value for key, value in request["params"].items() if key not in {"videos", "audios"}}
        self._context.db.update_job_request(job["id"], compact)
        manifest_path = store.directory(job["id"]) / "manifest.json"
        if manifest_path.is_file():
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stored = dict(manifest.get("parameters", {}))
            stored["params"] = {**stored.get("params", {}), **compact["params"]}
            store.write_json(manifest_path, {**manifest, "parameters": stored, **metadata})
            store.write_json(store.directory(job["id"]) / "config" / "request.json", compact)

    def free_comfyui_memory(self):
        from ...bootstrap import comfyui_client
        comfyui_client.free_memory()

    def voice_preset(self, preset_id):
        """Read a registered voice and its usable reference sample; never mutate it."""
        from ..presets.voices import VoicePresets
        presets = VoicePresets(self._context)
        preset = presets.get(preset_id)
        if not preset:
            raise ValueError("声音预设不存在")
        sample = presets.sample_path(preset)
        if not sample or not sample.is_file():
            raise ValueError("该声音预设尚未生成可用音色样本")
        return preset

    def style_items(self):
        from ..presets.style_library import items
        return items(self._context, self.plugin_id)

    def voice_sample(self, preset):
        from ..presets.voices import VoicePresets
        path = VoicePresets(self._context).sample_path(preset)
        return path if path and path.is_file() else None

    def reference(self, upload_id: str, media: str):
        import mimetypes
        import re
        if not re.fullmatch(r"[a-fA-F0-9]{32}", upload_id):
            raise ValueError("无效的参考素材 ID")
        paths = list(self._context.paths.uploads.glob(f"{upload_id}.*"))
        if not paths or (mimetypes.guess_type(paths[0].name)[0] or "").split("/", 1)[0] != media:
            raise ValueError(f"参考素材不存在或类型不是 {media}")
        return f"upload:{upload_id}"

    def comfyui_output_file(self, relative: str) -> Path | None:
        """Resolve one file below configured ComfyUI output roots."""
        candidate_name = Path(relative)
        if candidate_name.is_absolute() or ".." in candidate_name.parts:
            return None
        root = self._context.comfyui_output_dir.resolve()
        path = (root / candidate_name).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
        for root in self._comfyui_output_roots():
            path = (root / candidate_name).resolve()
            if path.is_relative_to(root.resolve()) and path.is_file():
                return path
        return None

    def comfyui_output_files(self, directory: str, pattern: str, *, detect: bool = True) -> list[Path]:
        """List files in one output subdirectory, without recursive or parent globs."""
        relative = Path(directory)
        if relative.is_absolute() or ".." in relative.parts or "/" in pattern or "\\" in pattern or ".." in pattern:
            raise ValueError("Invalid output search path")
        result = set()
        for root in self._comfyui_output_roots(detect=detect):
            folder = (root / relative).resolve()
            if folder.is_relative_to(root.resolve()):
                result.update(path.resolve() for path in folder.glob(pattern)
                              if path.is_file() and path.resolve().is_relative_to(root.resolve()))
        return sorted(result, key=lambda path: path.stat().st_mtime, reverse=True)

    def _comfyui_output_roots(self, *, detect=True):
        import time
        roots = [self._context.comfyui_output_dir]
        cache = self._context.comfyui_output_locations
        address = self._context.comfyui_url
        cached = cache.get(address)
        try:
            from ..settings import SettingsService
            from ...bootstrap import comfyui_client
            if detect and (cached is None or time.monotonic() - cached[0] > (300 if cached[1] else 15)):
                live = SettingsService(self._context, comfyui_client).local_comfyui_output_directory(
                    SettingsService(self._context, comfyui_client).read()
                )
                cached = (time.monotonic(), live)
                cache[address] = cached
            live = cached[1] if cached else None
            if live and live.resolve() not in {root.resolve() for root in roots}:
                roots.append(live)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError):
            pass
        return roots

    def session(self, session_id: str | None):
        return self._context.agent_sessions.get(session_id) if session_id else None

    def save_session(self, session: dict[str, Any], limit: int = 50) -> None:
        self._context.agent_sessions[session["id"]] = session
        while len(self._context.agent_sessions) > limit:
            oldest = min(self._context.agent_sessions.values(), key=lambda item: item["created_at"])
            self._context.agent_sessions.pop(oldest["id"], None)

    @staticmethod
    def initial_message(request):
        from ..collaboration.service import initial_agent_message
        return initial_agent_message(request)

    @staticmethod
    def staged_context(request):
        from ..collaboration.service import staged_generation_context
        return staged_generation_context(request)

    @staticmethod
    def repair_result(messages, result, model, mode, validator=None):
        from ..collaboration.service import repair_agent_result
        return repair_agent_result(messages, result, model, mode, validator)

    @staticmethod
    def start_progress(*args):
        from ..collaboration.service import start_agent_progress
        return start_agent_progress(*args)

    @staticmethod
    def update_progress(*args):
        from ..collaboration.service import update_agent_progress
        return update_agent_progress(*args)

    @staticmethod
    def finish_progress(*args):
        from ..collaboration.service import finish_agent_progress
        return finish_agent_progress(*args)

    @staticmethod
    def fail_progress(*args):
        from ..collaboration.service import fail_agent_progress
        return fail_agent_progress(*args)
