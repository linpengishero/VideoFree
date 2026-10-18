"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

import re

from backend.modules.shared.plugin_runtime import apply_image_dimensions, apply_storyboard_grid

from backend.modules.shared.plugin_runtime import apply_style


def storyboard_shots(prompt, count):
    # Split only explicit shot headings; ordinary story sentences remain context.
    headings = list(re.finditer(
        r'(?:^|\n)[ \t]*(?:#{1,6}[ \t]*)?(?:(?:镜头|分镜|画面|shot|frame)[ \t]*([1-4一二三四])|([1-4])[.、)）])[ \t]*[:：]?[ \t]*',
        prompt, re.IGNORECASE,
    ))
    numbers = [match.group(1) or match.group(2) for match in headings]
    numbers = ['一二三四'.index(value) + 1 if value in '一二三四' else int(value) for value in numbers]
    if numbers == list(range(1, count + 1)):
        context = prompt[:headings[0].start()].strip()
        shots = [prompt[match.end():headings[index + 1].start() if index + 1 < count else len(prompt)].strip()
                 for index, match in enumerate(headings)]
        if all(shots):
            return [f'{context}\n\n{shot}'.strip() for shot in shots]
    stages = ('Establish the scene and the initial situation before the main action.',
              'Show the beginning of the main action, advancing from the initial situation.',
              'Show the central action or turning point, advancing from the previous frame.',
              'Show the outcome or final situation after the action.')
    return [f'Story context (do not depict the entire story in one frame):\n{prompt}\n\n'
            f'Render only storyboard frame {index + 1} of {count}. {stages[index]}'
            for index in range(count)]



def bind_inputs(workflow, config, prompt, images):
    for node in workflow.values():
        inputs = node.setdefault("inputs", {})
        if not config.get("prompt", {}).get("preserve_all") and node.get("class_type") in {
            "CLIPTextEncode", "easy showAnything", "PrimitiveStringMultiline", "Krea2EditGroundedEncode",
        }:
            for key in ("text", "string", "value"):
                if key in inputs:
                    current = inputs[key]
                    if not (node["class_type"] == "PrimitiveStringMultiline" and isinstance(current, str)
                            and "character reference sheet" in current.lower() and "four" in current.lower()):
                        inputs[key] = prompt
                    break
    if images and not config.get("media_bindings", {}).get("image"):
        loaders = [node for node in workflow.values() if node.get("class_type") == "LoadImage"]
        for node, filename in zip(loaders, images):
            node["inputs"]["image"] = filename

def resolve_style_selectors(workflow):
    selectors = {key: node for key, node in workflow.items() if node.get("class_type") == "easy stylesSelector"}
    for node in workflow.values():
        for key, value in list(node.get("inputs", {}).items()):
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in selectors:
                source = selectors[str(value[0])]["inputs"]
                node["inputs"][key] = source.get("positive" if value[1] == 0 else "negative", "")
    for key in selectors:
        del workflow[key]


def prepare(workflow, config, request, media, job_id, prompt, runtime=None):
    uploaded = media["image"]
    apply_image_dimensions(workflow, config, request)
    apply_storyboard_grid(workflow, config, request.params.get("width", 1024), request.params.get("height", 1024))
    bind_inputs(workflow, config, prompt, uploaded)
    resolve_style_selectors(workflow)
    if config.get('shot_nodes'):
        selected = next((s for s in (runtime.style_items()[0] if runtime else []) if s["id"] == request.params.get("style_id")), None)
        shots = request.params.get('shots')
        if shots is None or shots == []:
            shots = storyboard_shots(request.prompt, len(config['shot_nodes']))
        if not isinstance(shots, list) or len(shots) != len(config['shot_nodes']) or any(not isinstance(s, str) or not s.strip() for s in shots):
            raise ValueError('Four nonempty shot descriptions are required')
        shot_instruction = config.get(
            'shot_instruction',
            'Generate one cinematic frame. Image1 is the scene reference, image2 is character A, image3 is character B. Preserve identity, clothing and scene geometry. No collage, no text.',
        )
        for node_id, shot in zip(config['shot_nodes'], shots):
            if request.params.get('style_prompt'):
                shot += '\n\n风格要求：' + request.params['style_prompt']
            styled = apply_style(selected, shot)
            workflow[node_id]['inputs']['prompt'] = shot_instruction + ' ' + styled

