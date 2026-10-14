import hashlib
import json
from pathlib import Path


def catalog(root):
    root = Path(root).resolve()
    items, errors = [], []
    for path in sorted(root.rglob('*.json')):
        try:
            rows = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('prompt'), str) or not row.get('name'):
                    continue
                key = str(path.relative_to(root)) + ':' + row['name']
                item = dict(row, id=hashlib.sha256(key.encode()).hexdigest()[:24], category=path.stem)
                thumbnail = row.get('thumbnail')
                item.pop('thumbnail', None)
                if isinstance(thumbnail, str) and not thumbnail.startswith(('http:', 'https:')):
                    for base in (path.parent, root):
                        candidate = (base / thumbnail).resolve()
                        if candidate.is_relative_to(root) and candidate.is_file():
                            item['thumbnail_path'] = str(candidate)
                            break
                items.append(item)
        except (OSError, ValueError) as exc:
            errors.append(f'{path.name}: {exc}')
    return items, errors


def apply_style(workflow, style, prompt):
    # Resolve the exported style selectors to their original positive/negative
    # input. The selected library template is applied once by the gateway.
    selectors = {key: node for key, node in workflow.items() if node['class_type'] == 'easy stylesSelector'}
    for node in workflow.values():
        for key, value in list(node['inputs'].items()):
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in selectors:
                source = selectors[str(value[0])]['inputs']
                node['inputs'][key] = source.get('positive' if value[1] == 0 else 'negative', '')
    for key in selectors:
        del workflow[key]
    if style is None:
        return prompt
    return style['prompt'].replace('{prompt}', prompt) if '{prompt}' in style['prompt'] else prompt + '\n' + style['prompt']
