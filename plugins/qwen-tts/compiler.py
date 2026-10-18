"""Qwen speech nodes belong to the Qwen plugin."""


def prepare(workflow, config, request, media, job_id, prompt):
    for node in workflow.values():
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "Qwen3VoiceClone":
            inputs["text"] = request.text
        elif node.get("class_type") == "Qwen3VoiceDesign":
            inputs["text"] = request.text
            inputs["instruct"] = request.instruction or inputs.get("instruct", "")
        elif node.get("class_type") == "LoadAudio" and media["audio"]:
            inputs["audio"] = media["audio"][0]
