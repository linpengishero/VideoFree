import hashlib
import json
from pathlib import Path


def items(context):
    import os
    from ..generation.plugins import PluginCatalog
    configured = os.getenv('MEDIA_STYLE_DIR')
    if configured:
        return catalog(configured)
    result, errors = [], []
    plugins, _ = PluginCatalog(context.paths.plugins, context).scan()
    for plugin in plugins:
        declaration = plugin.get('style_library')
        if not declaration:
            continue
        rows, failures = catalog(context.comfyui_output_dir.parent / declaration['comfyui_directory'])
        prefix = declaration.get('category_prefix', '')
        for row in rows:
            if prefix and row['category'].startswith(prefix):
                row['category'] = row['category'][len(prefix):]
        result.extend(rows)
        errors.extend(failures)
    return result, errors


def catalog(root):
    root = Path(root).resolve()
    items, errors = [], []
    if not root.is_dir():
        return [], [f'风格资源目录不存在: {root}']
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
    if not items and not errors:
        errors.append(f'风格资源目录中没有可用风格: {root}')
    return items, errors


def apply_style(style, prompt):
    if style is None:
        return prompt
    return style['prompt'].replace('{prompt}', prompt) if '{prompt}' in style['prompt'] else prompt + '\n' + style['prompt']
