"""Translate authoritative ComfyUI failures without probing optional nodes."""

import json
import re


MODEL_DIRECTORIES = {
    "vae_name": "models/vae/", "lora_name": "models/loras/",
    "ckpt_name": "models/checkpoints/", "unet_name": "models/diffusion_models/",
    "clip_name": "models/text_encoders/",
}


def describe_failure(raw: str) -> dict:
    result = {"code": "generation_failed", "message": raw, "suggestion": "查看原始错误与 ComfyUI 日志。", "missing_items": [], "raw": raw}
    payload = None
    start = raw.find("{")
    if start >= 0:
        try:
            payload = json.loads(raw[start:])
        except (ValueError, TypeError):
            pass
    if isinstance(payload, dict):
        error = payload.get("error", {})
        if isinstance(error, dict) and error.get("type") == "missing_node_type":
            extra = error.get("extra_info") or {}
            node = extra.get("class_type") or extra.get("node_title")
            if node:
                return {**result, "code": "comfyui_missing_node", "message": f"ComfyUI 未加载节点：{node}", "missing_items": [node], "suggestion": "安装提供该节点的插件并重启 ComfyUI；若已安装，检查启动日志中的依赖或导入错误。"}
        for event in payload.get("messages", []):
            if isinstance(event, (list, tuple)) and len(event) > 1 and event[0] == "execution_error" and isinstance(event[1], dict):
                detail = event[1]
                result["node_type"] = detail.get("node_type")
                raw = str(detail.get("exception_message", raw))
                break
        for node in (payload.get("node_errors") or {}).values():
            if not isinstance(node, dict):
                continue
            for error in node.get("errors", []):
                if not isinstance(error, dict) or error.get("type") != "value_not_in_list":
                    continue
                extra = error.get("extra_info") or {}
                key, value = extra.get("input_name"), extra.get("received_value")
                directory = MODEL_DIRECTORIES.get(key)
                if directory and value is not None:
                    return {**result, "code": "comfyui_missing_model", "message": f"ComfyUI 找不到模型：{value}", "missing_items": [str(value)], "suggestion": f"检查文件名及子目录路径，放入 {directory} 后刷新或重启 ComfyUI。"}
    match = re.search(r"Node ([^:]+): (\S+) unavailable;", raw)
    if match:
        node = match[2]
        return {**result, "code": "comfyui_missing_node", "message": f"ComfyUI 未加载节点：{node}", "missing_items": [node], "suggestion": "检查插件安装及启动日志并重启；若为仅前端节点，请导出 API 格式工作流。"}
    match = re.search(r"(\w+): (.+?) unavailable in ComfyUI; available:", raw)
    if match:
        key, value = match.groups()
        directory = MODEL_DIRECTORIES.get(key)
        return {**result, "code": "comfyui_missing_model" if directory else "comfyui_invalid_choice", "message": f"ComfyUI 找不到{'模型' if directory else '选项'}：{value}", "missing_items": [value], "suggestion": f"检查文件名及子目录路径，放入 {directory} 后刷新或重启 ComfyUI。" if directory else "检查该节点的可选值；原始错误包含当前可用列表。"}
    lower = raw.lower()
    if "out of memory" in lower or "outofmemoryerror" in lower:
        node = result.get("node_type")
        return {**result, "code": "comfyui_out_of_memory", "message": f"GPU 显存不足{f'，发生在 {node}' if node else ''}", "suggestion": "降低目标分辨率或时长，关闭其他占用显存的程序后重试。"}
    if "sageattention" in lower and any(word in lower for word in ("no module", "import", "not found")):
        return {**result, "code": "comfyui_missing_dependency", "message": "SageAttention 未安装或加载失败", "missing_items": ["sageattention"], "suggestion": "在 ComfyUI 使用的 Python 环境安装匹配的 SageAttention，检查 PyTorch/CUDA 兼容性并重启。"}
    if raw.startswith("无法连接 ComfyUI："):
        return {**result, "code": "comfyui_connection_failed", "message": raw, "suggestion": "检查 ComfyUI 是否启动、连接地址和防火墙；网关在线不代表 ComfyUI 在线。"}
    return result
