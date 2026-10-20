# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import copy
import json
import secrets
import struct
from pathlib import Path

# File pickers are populated from ComfyUI's input directory and can change
# after object_info was cached. Upload success and ComfyUI prompt validation
# are authoritative for these fields; cached combo choices are not.
DYNAMIC_FILE_INPUTS = {
    ('LoadImage', 'image'),
    ('LoadAudio', 'audio'),
    ('VHS_LoadVideo', 'video'),
    ('VHS_LoadVideoPath', 'video'),
}


def is_dynamic_file_input(class_type, input_name):
    return (class_type, input_name) in DYNAMIC_FILE_INPUTS


def workflow_from_png(path):
    """Extract ComfyUI's API prompt embedded in a workflow PNG."""
    data = Path(path).read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f"Not a PNG workflow: {path}")
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += length + 12
        if kind != b'tEXt' or b'\0' not in payload:
            continue
        key, value = payload.split(b'\0', 1)
        if key == b'prompt':
            return json.loads(value.decode('utf-8'))
    raise ValueError(f"PNG does not contain an API prompt: {path}")

def convert_workflow(source, info):
    if 'nodes' not in source:
        return copy.deepcopy(source)
    links = {str(x[0]): [str(x[1]), x[2]] for x in source['links']}
    result = {}
    for node in source['nodes']:
        kind = node.get('type')
        if node.get('mode', 0) != 0 or kind in {'Note', 'MarkdownNote', 'Label (rgthree)', 'AboutAuthorNode|Mie', 'Fast Groups Bypasser (rgthree)', 'Fast Groups Muter (rgthree)'}:
            continue
        if kind not in info:
            raise ValueError(f"Node {node['id']}: {kind} unavailable; export API format for frontend-only nodes")
        schema = info[kind].get('input', {})
        fields = {**schema.get('required', {}), **schema.get('optional', {})}
        raw = node.get('widgets_values') or []
        # Recent ComfyUI canvas exports may store widget values as an object
        # (notably video-save nodes). Named values remain authoritative; only
        # index into the legacy list representation when it is actually a list.
        raw_values = raw if isinstance(raw, list) else []
        named = node.get('widgets_values_named') or {}
        ports = node.get('inputs', [])
        widgets = [p['name'] for p in ports if p.get('widget')]
        if not widgets:
            widgets = [k for k, v in fields.items() if isinstance(v, list) and
                       (isinstance(v[0], list) or v[0] in {'INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO'}) and
                       not (len(v) > 1 and v[1].get('forceInput'))]
        inputs, cursor = {}, 0
        for key in widgets:
            if key not in fields:
                continue
            definition = fields[key]
            options = definition[1] if len(definition) > 1 else {}
            if cursor >= len(raw_values) and key not in named:
                raise ValueError(f"Node {node['id']} ({kind}): missing widget {key}; export API format")
            value = named.get(key, raw_values[cursor] if cursor < len(raw_values) else None)
            cursor += 1
            if options.get('control_after_generate') and cursor < len(raw_values) and raw_values[cursor] in ('fixed', 'randomize', 'increment', 'decrement'):
                control = raw_values[cursor]
                cursor += 1
                if control == 'randomize':
                    value = secrets.randbelow(min(options.get('max', 2**48), 2**48) + 1)
            if key in {'seed', 'noise_seed'} and isinstance(value, int) and value < 0:
                value = secrets.randbelow(min(options.get('max', 2**48), 2**48) + 1)
            inputs[key] = value
        for p in ports:
            if p.get('link') is not None:
                inputs[p['name']] = links[str(p['link'])]
        result[str(node['id'])] = {'class_type': kind, 'inputs': inputs}
    return result


def validate_choices(workflow, info):
    for node_id, node in workflow.items():
        fields = info.get(node['class_type'], {}).get('input', {})
        for key, spec in {**fields.get('required', {}), **fields.get('optional', {})}.items():
            if is_dynamic_file_input(node['class_type'], key):
                continue
            if key not in node['inputs'] or not isinstance(spec, list):
                continue
            value = node['inputs'][key]
            if isinstance(value, list):
                continue
            choices = spec[0] if isinstance(spec[0], list) else (spec[1].get('options') if spec[0] == 'COMBO' and len(spec) > 1 else None)
            if choices and value not in choices:
                raise ValueError(f"Node {node_id} ({node['class_type']}), {key}: {value!r} unavailable in ComfyUI; available: {choices[:12]!r}")
