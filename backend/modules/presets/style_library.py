import hashlib
import json
from pathlib import Path


def items(context, plugin_id=None):
    from ..generation.plugins import PluginCatalog
    result, errors = [], []
    plugins, _ = PluginCatalog(context.paths.plugins, context).scan()
    matching = [plugin for plugin in plugins if not plugin_id or plugin.get('id') == plugin_id]
    for plugin in matching:
        declaration = plugin.get('style_library')
        if not declaration:
            continue
        plugin_root = context.paths.plugins / plugin['_plugin_folder']
        rows, failures = catalog(plugin_root / declaration['directory'], namespace=plugin['id'])
        default_id = declaration.get('default_id', '')
        if default_id and rows and not any(row['id'] == default_id for row in rows):
            failures.append(f"style_library default_id is not present in {plugin['id']} styles: {default_id}")
        for row in rows:
            row['default'] = row['id'] == default_id
            row['plugin_id'] = plugin['id']
        result.extend(rows)
        errors.extend(failures)
    return result, errors


def catalog(root, namespace=''):
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
                style_id = row.get('id') or hashlib.sha256(f'{namespace}:{key}'.encode()).hexdigest()[:24]
                item = dict(row, id=style_id, category=row.get('category') or path.stem)
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
