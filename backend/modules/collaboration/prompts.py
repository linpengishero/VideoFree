"""Shared prompt loading from installed plugins."""

from pathlib import Path

from ...core.config import ProjectPaths
from ..generation.plugins import PluginCatalog


def agent_capability(model, mode, capability_id=None, kind=None):
    from ...bootstrap import context
    plugins = ProjectPaths.from_root(Path(__file__).resolve().parents[3]).plugins
    configs = PluginCatalog(plugins, context).capabilities()
    config = configs.get(capability_id) if capability_id else next((
        item for item in configs.values()
        if model in {item.get("model_family"), item.get("model_id"), *item.get("model_aliases", [])}
        and mode in {item["mode"], *item.get("mode_aliases", [])}
        and (kind is None or item["kind"] == kind)
    ), None)
    if config is None or (kind is not None and config["kind"] != kind):
        raise ValueError(f"Unregistered collaboration model/mode: {model}/{mode}")
    return config


def agent_skill_prompt(model: str, mode: str, capability_id: str | None = None) -> str:
    plugins = ProjectPaths.from_root(Path(__file__).resolve().parents[3]).plugins
    config = agent_capability(model, mode, capability_id)
    skill_root = plugins / config["plugin_folder"] / "collaboration" / "skills"
    model_name = config.get("skill_model", config.get("model_family", config.get("model_id", model)))
    mode_name = config.get("skill_mode", mode)
    paths = [skill_root / "system.md", skill_root / "models" / model_name / "model.md", skill_root / "models" / model_name / "modes" / f"{mode_name}.md"]
    try:
        return "\n\n---\n\n".join(path.read_text(encoding="utf-8") for path in paths)
    except OSError as exc:
        raise ValueError(f"智能体技能文件不可用: {exc}") from exc
