import json
import urllib.error
import urllib.request


class Provider:
    def __init__(self, manifest):
        self.thinking = manifest.get("thinking", "none")

    @staticmethod
    def endpoint(base_url):
        value = str(base_url).rstrip("/")
        return value if value.endswith("/chat/completions") else value + "/chat/completions"

    def build_chat_request(self, settings, messages, max_tokens, tools, tool_choice,
                           *, plain_request=False, disable_thinking=False):
        body = {
            "model": settings["ai_model"].strip(),
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if tools:
            body.update({"tools": tools, "tool_choice": tool_choice or "auto", "parallel_tool_calls": True})
        mode = str(settings.get("ai_thinking_mode") or "medium").lower()
        mode = {"auto": "medium", "on": "medium"}.get(mode, mode)
        mode = mode if mode in {"off", "low", "medium", "high"} else "medium"
        model = str(settings.get("ai_model", "")).lower()
        optional = not plain_request
        if self.thinking == "deepseek" and not plain_request:
            body["thinking"] = {"type": "disabled" if disable_thinking or mode == "off" else "enabled"}
            optional = True
        elif self.thinking == "custom" and not plain_request:
            body["chat_template_kwargs"] = {"enable_thinking": not disable_thinking and mode != "off"}
            if not disable_thinking and mode != "off":
                body["reasoning_effort"] = mode
            optional = True
        elif self.thinking == "openai" and optional and mode != "off" and model.startswith(("o1", "o3", "o4", "gpt-5")):
            body["reasoning_effort"] = mode
        headers = {"Content-Type": "application/json"}
        api_key = str(settings.get("ai_api_key", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return self.endpoint(settings["ai_base_url"]), body, headers, optional and (
            self.thinking in {"deepseek", "custom"} or "reasoning_effort" in body
        )

    @staticmethod
    def parse_chat_response(payload):
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            finish_reason = str(choice.get("finish_reason", ""))
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("AI 服务返回了无法识别的数据") from exc
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        return {
            "content": str(content).strip(),
            "tool_calls": message.get("tool_calls", []) if isinstance(message, dict) else [],
            "reasoning": message.get("reasoning_content", "") if isinstance(message, dict) else "",
            "finish_reason": finish_reason,
        }

    @staticmethod
    def list_models(base_url, api_key=""):
        url = str(base_url).rstrip("/") + "/models"
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法获取模型列表: {exc}") from exc
        rows = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
        return sorted({str(item.get("id") or item.get("name")) for item in rows
                       if isinstance(item, dict) and (item.get("id") or item.get("name"))}, key=str.lower)
