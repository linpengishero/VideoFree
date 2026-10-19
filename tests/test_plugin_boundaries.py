"""Plugin-owned resources and graph rules must not leak into generic execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.integrations.comfyui.compiler import apply_parameter_bindings
from backend.integrations.comfyui.workflow_loader import convert_workflow
from backend.modules.generation.plugins import PluginCatalog
from backend.modules.presets.style_library import apply_style, items
from backend.modules.shared.plugin_runtime import PluginRuntime
from backend.core.schemas import AgentChatRequest, GenerateRequest, TTSRequest

ROOT = Path(__file__).resolve().parents[1]


class PluginBoundaryTests(unittest.TestCase):
    def test_framework_layers_do_not_depend_on_http_or_reverse_dependencies(self):
        for path in [*(ROOT / 'backend/modules').rglob('*.py'), *(ROOT / 'plugins').rglob('*.py')]:
            if 'tests' not in path.parts:
                self.assertNotIn('from fastapi', path.read_text(encoding='utf8'), str(path))
        for path in (ROOT / 'backend/interfaces/http').rglob('*.py'):
            self.assertNotIn('integrations.', path.read_text(encoding='utf8'), str(path))
        collaboration = '\n'.join(path.read_text(encoding='utf8')
                                  for path in (ROOT / 'backend/modules/collaboration').glob('*.py'))
        self.assertNotIn('generation.task_store', collaboration)

    def test_framework_style_application_does_not_rewrite_graph(self):
        graph = {'1': {'class_type': 'easy stylesSelector', 'inputs': {'positive': 'original'}},
                 '2': {'class_type': 'ThirdParty', 'inputs': {'text': ['1', 0]}}}
        original = copy.deepcopy(graph)
        self.assertEqual(apply_style({'prompt': 'Style {prompt}'}, 'hello'), 'Style hello')
        self.assertEqual(graph, original)

    def test_only_krea_compiler_resolves_its_style_nodes(self):
        spec = importlib.util.spec_from_file_location('boundary_krea', ROOT / 'plugins/krea2/compiler.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        graph = {'1': {'class_type': 'easy stylesSelector', 'inputs': {'positive': 'original'}},
                 '2': {'class_type': 'Other', 'inputs': {'text': ['1', 0]}}}
        module.resolve_style_selectors(graph)
        self.assertNotIn('1', graph)
        self.assertEqual(graph['2']['inputs']['text'], 'original')

    def test_binding_defaults_belong_to_declaration(self):
        config = {'file': 'test.json', 'parameter_bindings': {
            'plugin_setting': [{'node': '1', 'input': 'value', 'default': 120}]}}
        for params, expected in [({}, 120), ({'plugin_setting': 90}, 90),
                                 ({'plugin_setting': 90, 'plugin_parameters': {'plugin_setting': 80}}, 80)]:
            graph = {'1': {'inputs': {}}}
            apply_parameter_bindings(graph, config, GenerateRequest(prompt='hello', params=params))
            self.assertEqual(graph['1']['inputs']['value'], expected)
        config['parameter_bindings']['plugin_setting'][0].pop('default')
        with self.assertRaisesRegex(ValueError, 'Missing declared plugin parameter'):
            apply_parameter_bindings({'1': {'inputs': {}}}, config, GenerateRequest(prompt='hello'))

    def test_installed_plugin_special_parameters_have_declared_defaults(self):
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        for config in configs.values():
            graph = {}
            for source, targets in config.get('parameter_bindings', {}).items():
                for target in targets:
                    graph.setdefault(str(target['node']), {'inputs': {}})
                    if source in {'music_bpm', 'music_key', 'music_timesignature', 'latent_checkpoint'}:
                        self.assertIn('default', target, config['id'] if 'id' in config else config['file'])
            if graph:
                apply_parameter_bindings(graph, config, GenerateRequest(prompt='hello'))

    def test_primitive_nodes_are_not_globally_renamed(self):
        source = {'nodes': [{'id': 1, 'type': 'PrimitiveNode', 'widgets_values': [0.25]}], 'links': []}
        info = {'PrimitiveNode': {'input': {'required': {'value': ['FLOAT', {}]}}}}
        result = convert_workflow(source, info)
        self.assertEqual(result['1']['class_type'], 'PrimitiveNode')
        self.assertEqual(result['1']['inputs']['value'], 0.25)

    def test_node_discovery_does_not_apply_builtin_aliases(self):
        from backend.modules.generation import service
        with patch.object(service.comfyui_client, 'node_definitions', return_value={}) as definitions:
            service.node_definitions(['PrimitiveNode'])
        definitions.assert_called_once_with(['PrimitiveNode'], {})

    def test_generic_prompt_has_no_model_rules(self):
        system = (ROOT / 'plugins/qwen-image/collaboration/skills/system.md').read_text(encoding='utf8')
        for token in ('Qwen', 'I2VA', 'FL2VA', 'storyboard_4'):
            self.assertNotIn(token, system)

    def test_specialized_collaboration_skills_keep_model_contracts(self):
        from backend.modules.collaboration.prompts import agent_skill_prompt
        qwen = agent_skill_prompt('qwen', 'image_to_image', 'image.qwen.image_to_image')
        self.assertIn('<image1>', qwen)
        self.assertIn('protected invariants', qwen)
        krea = agent_skill_prompt('krea2', 'text_to_image', 'image.krea2.text_to_image')
        self.assertIn('one cohesive', krea)
        self.assertIn('Do not add objects', krea)
        ltx = agent_skill_prompt('ltx2_5', 'text_to_video', 'video.ltx2_5.text_to_video')
        self.assertIn('4–8', ltx)
        self.assertIn('synchronized audio', ltx)
        music = agent_skill_prompt('minimax_music3', 'create', 'music.create')
        for heading in ('Global Metadata', 'Vocal Details', 'Arrangement'):
            self.assertIn(heading, music)
        ace = agent_skill_prompt('ace_step', 'background', 'music.ace_step.background')
        self.assertIn('[Instrumental]', ace)
        self.assertIn('Keep these values out of the natural-language caption', ace)

    def test_translation_is_declared_by_plugin_not_framework(self):
        from backend.interfaces.http.v2_capabilities import capability
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        for identifier, config in configs.items():
            public = capability(identifier, config)
            self.assertEqual(public['prompt_translation_action'],
                             'h3_translate' if config['plugin_id'] == 'minimax-h3' else None)
        app = (ROOT / 'frontend/src/App.vue').read_text(encoding='utf8')
        self.assertNotIn("runPluginAction('h3_translate'", app)

    def test_h3_prompt_loads_without_bootstrap_state(self):
        spec = importlib.util.spec_from_file_location('boundary_h3_prompts', ROOT / 'plugins/minimax-h3/collaboration/prompts.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.PLATFORM_SYSTEM.is_relative_to(ROOT / 'plugins/minimax-h3'))
        self.assertIn('I2VA', module.h3_quick_prompt('image_to_video'))

    def test_request_defaults_do_not_select_an_installed_model(self):
        speech = TTSRequest(text='hello')
        chat = AgentChatRequest(message='hello')
        self.assertEqual((speech.character, speech.voice_model, chat.model, chat.mode), ('', '', '', ''))
        self.assertEqual(TTSRequest.model_validate(speech.model_dump()).voice_model, '')

    def test_style_library_is_discovered_from_enabled_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin_root = root / 'plugins/test'
            library = plugin_root / 'assets/styles'
            library.mkdir(parents=True)
            (library / 'styles.json').write_text(json.dumps([
                {'id': 'test-realistic', 'name': 'Realistic', 'prompt': 'Realistic {prompt}'}]), encoding='utf8')
            ctx = SimpleNamespace(paths=SimpleNamespace(plugins=root / 'plugins'), comfyui_output_dir=root / 'output')
            declaration = {'id': 'test', '_plugin_folder': 'test', 'style_library': {'directory': 'assets/styles', 'default_id': 'test-realistic'}}
            with patch.dict('os.environ', {}, clear=True), patch.object(PluginCatalog, 'scan', return_value=([declaration], [])):
                rows, errors = PluginRuntime('test', {}, ctx).style_items()
                self.assertFalse(errors)
                self.assertEqual(rows[0]['id'], 'test-realistic')
                self.assertTrue(rows[0]['default'])
                declaration['style_library']['default_id'] = 'missing-style'
                rows, errors = PluginRuntime('test', {}, ctx).style_items()
                self.assertFalse(any(row['default'] for row in rows))
                self.assertIn('default_id is not present', errors[0])
            with patch.dict('os.environ', {}, clear=True), patch.object(PluginCatalog, 'scan', return_value=([], [])):
                self.assertEqual(items(ctx), ([], []))

    def test_style_library_does_not_fall_back_to_another_plugin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin_root = root / 'plugins/test'
            library = plugin_root / 'assets/styles'
            library.mkdir(parents=True)
            (library / 'styles.json').write_text(json.dumps([{'id': 'test-style', 'name': 'Test', 'prompt': 'Test'}]), encoding='utf8')
            ctx = SimpleNamespace(paths=SimpleNamespace(plugins=root / 'plugins'), comfyui_output_dir=root / 'output')
            plugins = [
                {'id': 'test', '_plugin_folder': 'test', 'style_library': {'directory': 'assets/styles', 'default_id': 'test-style'}},
                {'id': 'plain', '_plugin_folder': 'plain'},
            ]
            with patch.dict('os.environ', {'MEDIA_STYLE_DIR': str(root / 'legacy-styles')}), patch.object(PluginCatalog, 'scan', return_value=(plugins, [])):
                rows, errors = items(ctx, 'plain')
                self.assertEqual(rows, [])
                self.assertEqual(errors, [])

    def test_qwen_and_krea_styles_are_self_contained_and_isolated(self):
        context = SimpleNamespace(paths=SimpleNamespace(plugins=ROOT / 'plugins'))
        qwen, qwen_errors = items(context, 'qwen-image')
        krea, krea_errors = items(context, 'krea2')
        self.assertFalse(qwen_errors)
        self.assertFalse(krea_errors)
        self.assertEqual(len(qwen), 6)
        self.assertEqual(len(krea), 6)
        self.assertEqual([row['id'] for row in qwen if row['default']], ['qwen-realistic'])
        self.assertEqual([row['id'] for row in krea if row['default']], ['krea2-realistic'])
        self.assertFalse({row['id'] for row in qwen} & {row['id'] for row in krea})
        self.assertTrue(all(Path(row['thumbnail_path']).is_file() for row in qwen + krea))
        self.assertEqual({row['plugin_id'] for row in qwen}, {'qwen-image'})
        self.assertEqual({row['plugin_id'] for row in krea}, {'krea2'})

    def test_invalid_style_library_declarations_are_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = root / 'test'
            plugin.mkdir()
            (plugin / 'ok').mkdir(exist_ok=True)
            for declaration in ({'directory': '../escape'}, {'directory': 'ok', 'default_id': 5}, {'comfyui_directory': 'ok'}, []):
                (plugin / 'plugin.json').write_text(json.dumps({
                    'schema_version': 1, 'id': 'test', 'version': '1', 'style_library': declaration}), encoding='utf8')
                plugins, errors = PluginCatalog(root).scan()
                self.assertFalse(plugins)
                self.assertTrue(errors)
