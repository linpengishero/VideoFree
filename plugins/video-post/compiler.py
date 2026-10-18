"""Video enhancement graph adaptation, independent from prompt modes."""


def prepare(workflow, config, request, media, job_id, prompt):
    for node in workflow.values():
        if node.get("class_type") == "CreateVideo":
            node.setdefault("inputs", {}).update(fps=24, bit_depth=8)
        elif node.get("class_type") == "SaveVideo":
            node.setdefault("inputs", {}).setdefault("codec", "auto")

