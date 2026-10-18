"""Director skill discovery and stable system prompts."""

import json
from pathlib import Path
import re
from typing import Any

AGENT_SKILLS = Path(__file__).resolve().parent / "skills"
PLATFORM_SYSTEM = AGENT_SKILLS / "system.md"

AGENT_MODES = {
    "minimax-h3": {
        "text_to_video": "t2va", "image_to_video": "i2va",
        "first_last_frame": "fl2va", "last_frame": "l2va", "reference": "ref2va",
    },
    "krea2": {"text_to_image": "text_to_image", "image_to_image": "image_to_image", "character": "character"},
    "qwen": {
        "text_to_image": "text_to_image", "image_to_image": "image_to_image",
        "character": "character", "storyboard_4": "storyboard_4",
    },
    "ltx2_5": {
        "text_to_video": "text_to_video", "image_to_video": "image_to_video",
        "first_last_frame": "first_last_frame", "multi_reference": "multi_reference",
    },
    "minimax_music3": {"preset": "preset", "creative": "creative"},
    "ace_step": {"background": "background"},
}


AGENT_MODEL_ALIASES = {
    "minimax": "minimax-h3",
    "music3": "minimax_music3",
    "ace-step-1.5": "ace_step",
}


def read_agent_files(paths: list[Path]) -> str:
    sections = []
    for path in paths:
        sections.append(f"# Source: {path.name}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(sections)


def agent_skill_prompt(model: str, mode: str) -> str:
    model = AGENT_MODEL_ALIASES.get(model, model)
    code = AGENT_MODES.get(model, {}).get(mode)
    if not code:
        raise ValueError(f"当前智能协作不支持 {model} / {mode} 模式")
    model_dir = "minimax-h3" if model == "minimax-h3" else model
    paths = [
        PLATFORM_SYSTEM,
        AGENT_SKILLS / "models" / model_dir / "model.md",
        AGENT_SKILLS / "models" / model_dir / "modes" / f"{code}.md",
    ]
    try:
        return "\n\n---\n\n".join(path.read_text(encoding="utf-8") for path in paths)
    except OSError as exc:
        raise ValueError(f"智能体技能文件不可用: {exc}") from exc


def requirements_stage_prompt() -> str:
    return read_agent_files([AGENT_SKILLS / "pipeline" / "requirements.md"])


def scene_design_stage_prompt(
    content_type: str = "general",
    shot_type: str = "general",
    *,
    action_level: str = "simple",
    action_domain: str = "none",
    dialogue_required: bool = False,
    closeup_emotion_required: bool = False,
) -> str:
    domain_skills = {
        "explainer": "explainer-clip.md",
        "commerce": "commerce-clip.md",
        "product_showcase": "product-showcase-clip.md",
    }
    shot_skills = {
        "combat_exchange": "combat-exchange.md",
        "ultimate_move": "ultimate-move.md",
        "dialogue_performance": "dialogue-performance.md",
        "emotional_closeup": "emotional-closeup.md",
    }
    paths = [AGENT_SKILLS / "pipeline" / "scene-design.md"]
    if content_type in domain_skills:
        paths.append(AGENT_SKILLS / "pipeline" / domain_skills[content_type])
    selected_shot_skill = shot_skills.get(shot_type)
    if action_level == "combat" or action_domain == "combat":
        selected_shot_skill = "combat-exchange.md"
    if selected_shot_skill:
        paths.append(AGENT_SKILLS / "pipeline" / selected_shot_skill)
    if dialogue_required and shot_type != "dialogue_performance":
        paths.append(AGENT_SKILLS / "pipeline" / "dialogue-performance.md")
    if closeup_emotion_required and shot_type != "emotional_closeup":
        paths.append(AGENT_SKILLS / "pipeline" / "emotional-closeup.md")
    return read_agent_files(paths)


def final_review_prompt() -> str:
    return read_agent_files([AGENT_SKILLS / "pipeline" / "final-review.md"])


def shot_direction_prompt() -> str:
    return read_agent_files([AGENT_SKILLS / "pipeline" / "shot-direction.md"])


def h3_task_prompt(mode: str, task_skill: str) -> str:
    code = AGENT_MODES["minimax-h3"].get(mode)
    if not code:
        raise ValueError(f"当前智能协作不支持 minimax-h3 / {mode} 模式")
    official = AGENT_SKILLS / "models" / "minimax-h3" / "upstream" / "h3-prompt-writing"
    guide = "ref-en.txt" if code == "ref2va" else "base-en.txt"
    prompt = read_agent_files([
        PLATFORM_SYSTEM,
        official / "SKILL.md",
        official / "references" / guide,
        AGENT_SKILLS / "models" / "minimax-h3" / "model.md",
        AGENT_SKILLS / "models" / "minimax-h3" / "modes" / f"{code}.md",
        AGENT_SKILLS / "pipeline" / task_skill,
    ])
    # The upstream reference contains an older public duration range. The
    # gateway accepts the selected local duration, including 1-3 second clips.
    return prompt.replace("4–15", "1–15").replace("4-15", "1-15")


def h3_compiler_prompt(mode: str) -> str:
    return h3_task_prompt(mode, "h3-director-compiler.md")


DIRECTOR_CORE_SKILLS = {
    "combat_continuity": ("combat-continuity", "处理连续攻防、受力、重心、道具占用和动作衔接", "combat-exchange.md"),
    "ultimate_action": ("ultimate-action", "处理大招、爆发动作和高强度结果", "ultimate-move.md"),
    "dialogue_performance": ("dialogue-performance", "处理对白归属、听者反应、潜台词和口型", "dialogue-performance.md"),
    "facial_performance": ("facial-performance", "处理微表情、情绪变化和可见表演", "emotional-closeup.md"),
    "explainer": ("explainer", "处理单段解说和信息表达", "explainer-clip.md"),
    "commerce": ("commerce", "处理单段电商展示和卖点动作", "commerce-clip.md"),
    "product_showcase": ("product-showcase", "处理产品展示、功能动作和视觉重点", "product-showcase-clip.md"),
    "chase_motion": ("chase-motion", "处理追逐、转向、跨越地形和追逐中的瞬时交锋", "chase-motion.md"),
}


def director_extension_directory() -> Path:
    directory = AGENT_SKILLS / "pipeline" / "extensions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def director_skill_catalog() -> list[dict[str, str]]:
    catalog = [
        {"id": value[0], "name": value[0], "summary": value[1], "source": "core"}
        for value in DIRECTOR_CORE_SKILLS.values()
    ]
    for path in sorted(director_extension_directory().glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata: dict[str, str] = {}
        for line in text.splitlines()[:16]:
            match = re.match(r"^\s*(id|name|summary)\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                metadata[match.group(1).lower()] = match.group(2).strip().strip('"')
        skill_id = metadata.get("id") or path.stem
        catalog.append({
            "id": skill_id,
            "name": metadata.get("name") or skill_id,
            "summary": metadata.get("summary") or next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), skill_id),
            "source": path.name,
        })
    return catalog


def director_skill_planner_prompt() -> str:
    return read_agent_files([
        PLATFORM_SYSTEM,
        AGENT_SKILLS / "pipeline" / "skill-planner.md",
    ])


def load_director_skill(skill_id: str) -> str:
    for item in director_skill_catalog():
        if item["id"] != skill_id:
            continue
        if item["source"] == "core":
            for value in DIRECTOR_CORE_SKILLS.values():
                if value[0] == skill_id:
                    return (AGENT_SKILLS / "pipeline" / value[2]).read_text(encoding="utf-8")
        return (director_extension_directory() / item["source"]).read_text(encoding="utf-8")
    raise ValueError(f"未注册的导演技能: {skill_id}")


def h3_director_prompt(mode: str, requirements: dict[str, Any], selected_skill_text: str = "") -> str:
    capability_skills = {
        "combat_continuity": "combat-exchange.md",
        "ultimate_action": "ultimate-move.md",
        "dialogue_performance": "dialogue-performance.md",
        "facial_performance": "emotional-closeup.md",
        "explainer": "explainer-clip.md",
        "commerce": "commerce-clip.md",
        "product_showcase": "product-showcase-clip.md",
        "chase_motion": "chase-motion.md",
    }
    capabilities = list(requirements.get("capabilities", []))
    if requirements.get("action_level") == "combat" or requirements.get("action_domain") == "combat" or requirements.get("shot_type") == "combat_exchange":
        capabilities.append("combat_continuity")
    if requirements.get("shot_type") == "ultimate_move": capabilities.append("ultimate_action")
    if requirements.get("dialogue_required") or requirements.get("content_type") == "dialogue_performance": capabilities.append("dialogue_performance")
    if requirements.get("closeup_emotion_required") or requirements.get("shot_type") == "emotional_closeup": capabilities.append("facial_performance")
    if requirements.get("content_type") in {"explainer", "commerce", "product_showcase"}: capabilities.append(requirements["content_type"])
    if requirements.get("shot_type") == "chase_motion" or requirements.get("martial_arts_plan", {}).get("context") == "chase":
        capabilities.append("chase_motion")
    selected = [capability_skills[item] for item in dict.fromkeys(capabilities) if item in capability_skills]
    paths = [AGENT_SKILLS / "pipeline" / name for name in dict.fromkeys(selected)]
    prompt = h3_compiler_prompt(mode)
    if paths:
        prompt += "\n\n---\n\n# Selected Directing Capabilities\n\n" + read_agent_files(paths)
    if selected_skill_text:
        prompt += "\n\n---\n\n# AI-Selected Director Skills\n\n" + selected_skill_text
    martial_plan = requirements.get("martial_arts_plan")
    if isinstance(martial_plan, dict) and martial_plan.get("required"):
        prompt += "\n\n---\n\n# Martial Arts Action Contract\n\n" + json.dumps(martial_plan, ensure_ascii=False)
    return prompt


def h3_conformance_prompt() -> str:
    return read_agent_files([
        PLATFORM_SYSTEM,
        AGENT_SKILLS / "pipeline" / "h3-conformance.md",
    ])


def h3_conformance_review_prompt() -> str:
    return read_agent_files([
        PLATFORM_SYSTEM,
        AGENT_SKILLS / "pipeline" / "h3-conformance-review.md",
    ])


def h3_quick_prompt(mode: str) -> str:
    return h3_task_prompt(mode, "h3-quick-converter.md")

