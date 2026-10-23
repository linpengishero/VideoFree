"""Plugin-owned workflow preparation; shared execution stays in the gateway.

The bundled snapshot carries a two-segment chain (segment 1 node 136, segment 2
node 224). This compiler extends it to 2-5 segments by cloning the segment-2
subgraph, cascading the last-frame guide, and growing the picture/audio merge
chains. Segment count and per-segment prompts come from plugin parameters, so
director collaboration decides them and one job renders the whole video.
"""

import secrets

from backend.modules.shared.plugin_runtime import PluginError

MIN_SEGMENTS = 1
MAX_SEGMENTS = 5

# Segment-2 subgraph cloned for every extra segment.
SEGMENT_TEMPLATE = ["224", "215", "221", "220", "225", "218", "219", "216", "217", "227", "232"]
# Shared nodes every clone keeps referencing.
SHARED = {"clip": ["128", 0], "vae": ["119", 0], "audio_vae": ["120", 0],
          "length": ["131", 1], "width": ["900", 0], "height": ["901", 0],
          "model": ["222", 0]}
# Node 131's frame-count expression (seconds -> 17k+5 frames), cloned per segment
# when the director's plan gives segments unequal durations.
LENGTH_EXPRESSION = "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17"


def _frames_for(duration):
    """Frames a seconds value produces through node 131's 17k+5 expression."""
    frames = max(5, round(float(duration) * 24))
    return frames + (5 - frames % 17) % 17


def resolve_segments(plugin_parameters):
    try:
        segments = int(plugin_parameters.get("segments", MIN_SEGMENTS))
    except (TypeError, ValueError):
        segments = MIN_SEGMENTS
    return max(MIN_SEGMENTS, min(MAX_SEGMENTS, segments))


def resolve_durations(plugin_parameters, segments):
    """Per-segment durations from the director plan; None keeps the uniform binding.

    Wire format is a comma-separated string (the framework parameter schema has
    no array type); lists are accepted for in-process callers.
    """
    raw = plugin_parameters.get("durations")
    if isinstance(raw, str):
        raw = raw.replace("，", ",").split(",")
    if not isinstance(raw, list) or len(raw) < segments:
        return None
    durations = []
    for item in raw[:segments]:
        try:
            value = float(item)
        except (TypeError, ValueError):
            return None
        durations.append(max(1.0, min(15.0, value)))
    return durations


def _add_length_pair(workflow, index, duration):
    """Give segment `index` its own seconds -> frames pair (mirrors nodes 132/131)."""
    workflow[f"{index}132"] = {"class_type": "PrimitiveFloat", "inputs": {"value": duration}}
    workflow[f"{index}131"] = {"class_type": "ComfyMathExpression",
                               "inputs": {"values.a": [f"{index}132", 0], "expression": LENGTH_EXPRESSION}}
    return [f"{index}131", 1]


def segment_prompts(plugin_parameters, prompt, segments):
    """Per-segment prompts; missing continuations reuse the main prompt."""
    prompts = [str(prompt or "").strip()]
    for index in range(2, MAX_SEGMENTS + 1):
        value = str(plugin_parameters.get(f"prompt_{index}", "") or "").strip()
        prompts.append(value or prompts[0])
    return prompts[:segments]


def _clone_segment(workflow, index, prompt):
    clone = {node_id: f"{index}{node_id}" for node_id in SEGMENT_TEMPLATE}
    for node_id in SEGMENT_TEMPLATE:
        template = workflow[node_id]
        # Copy widget values and reference links; loaders and model chain stay shared.
        workflow[clone[node_id]] = {"class_type": template["class_type"], "inputs": dict(template["inputs"])}
    workflow[clone["224"]]["inputs"]["prompt"] = prompt
    workflow[clone["225"]]["inputs"]["noise_seed"] = secrets.randbelow(2 ** 48)
    return clone


def prepare(workflow, config, request, media, job_id, prompt, runtime=None):
    plugin_parameters = request.params.get("plugin_parameters", {}) or {}
    if str(plugin_parameters.get("director_plan", "")) != "confirmed":
        # The framework mandates a direct mode, but this plugin only makes sense
        # with the director's segment plan; block raw direct submissions.
        raise PluginError(422, "本插件仅支持导演协作提交，请通过“导演协作”模式生成")
    segments = resolve_segments(plugin_parameters)
    prompts = segment_prompts(plugin_parameters, prompt, segments)
    durations = resolve_durations(plugin_parameters, segments)
    # Independent random noise per segment; the framework writes one seed to all bindings.
    workflow["129"]["inputs"]["noise_seed"] = secrets.randbelow(2 ** 48)
    # The framework binds the whole-video total to node 132; per-clip seconds are
    # the compiler's decision, so always overwrite it.
    workflow["132"]["inputs"]["value"] = (
        durations[0] if durations else min(float(request.duration_seconds or 5), 15.0))
    if segments == 1:
        # Single clip: ImageBatchMulti needs inputcount>=2 and AudioConcat requires
        # audio2, so the merge nodes cannot shrink to one input — bypass them and
        # wire the final combine straight onto segment 1's decoders. Pruning then
        # drops the merge chain and the whole segment-2 subgraph.
        workflow["237"]["inputs"]["images"] = ["122", 0]
        workflow["236"]["inputs"]["audio"] = ["121", 0]
        return
    workflow["224"]["inputs"]["prompt"] = prompts[1]
    workflow["225"]["inputs"]["noise_seed"] = secrets.randbelow(2 ** 48)
    if durations:
        # Every segment beyond the first gets its own seconds -> frames pair.
        workflow["224"]["inputs"]["length"] = _add_length_pair(workflow, 2, durations[1])
    # Continuity guide: the 5 frames just before the previous segment's final frame
    # (skipping the last frame avoids flash/motion-blur artifacts). ComfyUI validates
    # start_index >= -1, so compute the positive offset from the previous segment's
    # frame count instead of relying on negative indexing.
    frames = ([_frames_for(item) for item in durations] if durations
              else [_frames_for(workflow["132"]["inputs"]["value"])] * segments)
    workflow["227"]["inputs"]["start_index"] = frames[0] - 6
    last_image, audio_tail = "216", "235"
    # The template subgraph is segment 2; clones start at segment 3.
    for index in range(3, segments + 1):
        clone = _clone_segment(workflow, index, prompts[index - 1])
        # The clone copied segment 2's length link; point it at its own pair or the shared one.
        workflow[clone["224"]]["inputs"]["length"] = (
            _add_length_pair(workflow, index, durations[index - 1]) if durations else SHARED["length"])
        # Cascade: this segment is guided by the previous segment's last decoded frame.
        workflow[clone["227"]]["inputs"]["images"] = [last_image, 0]
        workflow[clone["227"]]["inputs"]["start_index"] = frames[index - 2] - 6
        workflow[clone["232"]]["inputs"].update(
            positive=[clone["224"], 0], latent=[clone["224"], 1],
            vae=SHARED["vae"], audio_vae=SHARED["audio_vae"], image=[clone["227"], 0],
        )
        workflow[clone["215"]]["inputs"].update(model=SHARED["model"], conditioning=[clone["232"], 0])
        workflow[clone["221"]]["inputs"]["model"] = SHARED["model"]
        workflow[clone["219"]]["inputs"].update(
            noise=[clone["225"], 0], guider=[clone["215"], 0], sampler=[clone["218"], 0],
            sigmas=[clone["220"], 0], latent_image=[clone["224"], 1],
        )
        workflow[clone["216"]]["inputs"].update(samples=[clone["219"], 0], vae=SHARED["vae"])
        workflow[clone["217"]]["inputs"].update(samples=[clone["219"], 0], vae=SHARED["audio_vae"])
        # Grow the merge chains: picture batch takes one more input, audio concat chains.
        workflow["234"]["inputs"][f"image_{index}"] = [clone["216"], 0]
        workflow["234"]["inputs"]["inputcount"] = index
        concat = f"{index}235"
        workflow[concat] = {"class_type": "AudioConcat",
                            "inputs": {"audio1": [audio_tail, 0], "audio2": [clone["217"], 0], "direction": "after"}}
        workflow["236"]["inputs"]["audio"] = [concat, 0]
        audio_tail = concat
        last_image = clone["216"]
