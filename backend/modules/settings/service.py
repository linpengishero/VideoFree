import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request
import urllib.parse

from ...core.context import ApplicationContext
from ...integrations.comfyui import ComfyUIClient


class SettingsService:
    def __init__(self, context: ApplicationContext, comfyui: ComfyUIClient):
        self.context = context
        self.comfyui = comfyui
        self.legacy_settings_path = context.paths.legacy_settings

    def read(self) -> dict[str, Any]:
        defaults = {
            "comfyui_url": self.context.comfyui_url,
            "comfyui_output_dir": str(self.context.comfyui_output_dir),
            "ai_provider": os.getenv("AI_PROVIDER", "openai"),
            "ai_base_url": os.getenv("AI_BASE_URL", ""),
            "ai_api_key": os.getenv("AI_API_KEY", ""),
            "ai_model": os.getenv("AI_MODEL", "gpt-4.1-mini"),
            "ai_multimodal_video": os.getenv("AI_MULTIMODAL_VIDEO", "true"),
            "ai_thinking_mode": os.getenv("AI_THINKING_MODE", "medium"),
            "grsai_api_key": os.getenv("GRSAI_API_KEY", ""),
        }
        stored = self.context.db.settings()
        if self.legacy_settings_path.exists():
            try:
                legacy = json.loads(self.legacy_settings_path.read_text(encoding="utf-8"))
                missing = {key: value for key, value in legacy.items() if key not in stored}
                if missing:
                    self.context.db.save_settings(missing)
                    stored.update({key: str(value) for key, value in missing.items()})
                self.legacy_settings_path.unlink()
            except (OSError, json.JSONDecodeError):
                pass
        defaults.update(stored)
        defaults["ai_multimodal_video"] = str(defaults.get("ai_multimodal_video", "true")).lower() in {
            "1", "true", "yes", "on",
        }
        if defaults.get("ai_provider") not in {"openai", "deepseek", "custom"}:
            defaults["ai_provider"] = "custom"
        if str(defaults.get("ai_thinking_mode", "")).lower() in {"", "auto", "on"}:
            defaults["ai_thinking_mode"] = "medium"
        return defaults

    def effective_output_directory(self, settings: dict[str, Any], *, detect_comfyui: bool = True) -> Path:
        configured = str(settings.get("comfyui_output_dir", "")).strip()
        fallback = (self.context.paths.data / "comfyui_output").resolve()
        if detect_comfyui and (not configured or Path(configured).expanduser().resolve() == fallback):
            detected = self.local_comfyui_output_directory(settings)
            if detected:
                return detected
        return (
            Path(configured).expanduser().resolve()
            if configured
            else fallback
        )

    def local_comfyui_output_directory(self, settings: dict[str, Any]) -> Path | None:
        """Return the real output directory reported by a local ComfyUI process.

        The gateway's own project library is intentionally separate from this
        directory. H3 nodes write resumable latent checkpoints directly here.
        """
        address = str(settings.get("comfyui_url") or self.context.comfyui_url)
        if urllib.parse.urlparse(address).hostname not in {"localhost", "127.0.0.1", "::1"}:
            return None
        try:
            argv = self.comfyui.request("/system_stats").get("system", {}).get("argv", [])
            main_file = Path(argv[0]).expanduser()
            if "--output-directory" in argv:
                directory = Path(argv[argv.index("--output-directory") + 1]).expanduser()
                if not directory.is_absolute():
                    directory = main_file.parent / directory
            else:
                directory = main_file.parent / "output"
            return directory.resolve() if directory.is_dir() else None
        except (OSError, RuntimeError, ValueError, IndexError, TypeError, KeyError):
            return None

    def ai_is_configured(self, settings: dict[str, Any] | None = None) -> bool:
        values = settings or self.read()
        if not str(values.get("ai_base_url", "")).strip() or not str(values.get("ai_model", "")).strip():
            return False
        return values.get("ai_provider") == "custom" or bool(str(values.get("ai_api_key", "")).strip())

    def apply(self, values: dict[str, str]) -> dict[str, Any]:
        settings = self.read()
        settings.update({
            key: value.strip() if isinstance(value, str) else value
            for key, value in values.items() if value is not None
        })
        if not settings["comfyui_url"]:
            raise ValueError("comfyui_url is required")
        self.context.comfyui_url = settings["comfyui_url"].rstrip("/")
        self.comfyui.configure(self.context.comfyui_url)
        self.context.comfyui_output_dir = self.effective_output_directory(settings)
        grsai_key = str(settings.get("grsai_api_key", "")).strip()
        if grsai_key and not grsai_key.startswith("sk-"):
            raise ValueError("GrisAI API Key 必须以 sk- 开头")
        self.context.db.save_settings(settings)
        return settings

    def configured_grsai_key(self, settings: dict[str, Any] | None = None) -> str:
        stored = self.context.db.settings() if settings is None else {}
        values = settings or self.read()
        if settings is None and "grsai_api_key" in stored:
            return str(stored["grsai_api_key"]).strip()
        direct = str(values.get("grsai_api_key") or os.getenv("GRSAI_API_KEY", "")).strip()
        if direct:
            return direct
        env_path = self.effective_output_directory(values).parent / "custom_nodes" / "ComfyUI-GrsAI" / ".env"
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("GRSAI_API_KEY="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return ""

    @staticmethod
    def fetch_ai_models(base_url: str, api_key: str = "") -> list[str]:
        url = base_url.rstrip("/") + "/models"
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法获取模型列表: {exc}") from exc
        rows = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
        return sorted({
            str(item.get("id") or item.get("name"))
            for item in rows
            if isinstance(item, dict) and (item.get("id") or item.get("name"))
        }, key=str.lower)
