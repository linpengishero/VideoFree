from pathlib import Path
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .core.context import ApplicationContext
from .core.config import EnvironmentConfig, ProjectPaths
from .integrations.comfyui import ComfyUIClient
from .integrations.system_services import LLMProviderCatalog
from .persistence import Database


ROOT = Path(__file__).resolve().parents[1]


def create_context(root: Path) -> ApplicationContext:
    paths = ProjectPaths.from_root(root)
    paths.ensure_runtime_directories()
    config = EnvironmentConfig.load(paths)
    return ApplicationContext(
        paths=paths,
        config=config,
        db=Database(paths.data / "media_gateway.db"),
        comfyui_url=config.default_comfyui_url,
        comfyui_output_dir=config.default_comfyui_output_dir,
        system_services=LLMProviderCatalog(root / "backend" / "integrations" / "system_services" / "llm_providers"),
    )


context = create_context(ROOT)
comfyui_client = ComfyUIClient(context.comfyui_url)

def check_installation(root: Path = ROOT) -> None:
    """Check the release package without contacting providers or starting workers."""
    import socket
    import ssl
    import sqlite3
    from .modules.generation.plugins import PluginCatalog

    plugins, errors = PluginCatalog(root / "plugins").scan()
    if errors:
        raise RuntimeError(f"Invalid plugins: {errors}")
    dist = root / "static" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError("Frontend build missing: run npm ci and npm run build in frontend")

    class AssetParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in {"script", "link"}:
                return
            attributes = dict(attrs)
            url = urlsplit(attributes.get("src" if tag == "script" else "href", ""))
            if url.scheme or url.netloc or not url.path:
                return
            asset = (dist / url.path.lstrip("/")).resolve()
            if not asset.is_relative_to(dist.resolve()) or not asset.is_file():
                raise RuntimeError(f"Frontend asset missing: {url.path}; rebuild frontend")

    AssetParser().feed(index.read_text(encoding="utf-8"))
    manifest_path = dist / ".vite" / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Frontend manifest missing: rebuild frontend with npm run build")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("Empty or invalid manifest")
        for entry in manifest.values():
            for filename in [entry["file"], *entry.get("css", []), *entry.get("assets", [])]:
                asset = (dist / filename).resolve()
                if not asset.is_relative_to(dist.resolve()) or not asset.is_file():
                    raise RuntimeError(f"Frontend asset missing: {filename}; rebuild frontend")
            for dependency in [*entry.get("imports", []), *entry.get("dynamicImports", [])]:
                if dependency not in manifest:
                    raise RuntimeError(f"Frontend chunk missing from manifest: {dependency}; rebuild frontend")
        for plugin in plugins:
            for field in ("entry", "resource_entry"):
                entry = plugin.get("application", {}).get(field)
                if entry and f"../plugins/{plugin['_plugin_folder']}/{entry}" not in manifest:
                    raise RuntimeError(f"Plugin application not built: {plugin['id']}/{entry}; rebuild frontend")
            independent = plugin.get("application", {}).get("ui", {})
            if isinstance(independent, dict) and independent.get("entry"):
                entry_path = (root / "plugins" / plugin["_plugin_folder"] / independent["entry"]).resolve()
                plugin_root = (root / "plugins" / plugin["_plugin_folder"]).resolve()
                if not entry_path.is_relative_to(plugin_root) or not entry_path.is_file():
                    raise RuntimeError(f"Plugin independent UI missing: {plugin['id']}/{independent['entry']}")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError("Frontend manifest invalid: rebuild frontend with npm run build") from exc
    print(f"Release check OK: {len(plugins)} plugins, frontend assets, socket/SSL/SQLite runtime")


__all__ = ["ROOT", "context", "comfyui_client", "create_context", "check_installation"]
