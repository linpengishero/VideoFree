import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.modules.generation.plugins import PluginCatalog, validate_parameters
from backend.core.config import ProjectPaths
from backend.modules.generation.workflow_registry import WorkflowRegistry
from backend.integrations.comfyui.compiler import apply_parameter_bindings
from backend.interfaces.http.v2_capabilities import capability
from backend.modules.generation.actions import discover_actions, public_actions, prepare_action
import asyncio


ROOT = Path(__file__).resolve().parents[1]


class PluginTests(unittest.TestCase):
    def test_gpt_image_version_selector_precedes_image_settings(self):
        capabilities = PluginCatalog(ROOT / 'plugins').capabilities()
        configs = [config for config in capabilities.values() if config['plugin_id'] == 'gpt-image']
        self.assertEqual(len(configs), 6)
        for config in configs:
            binds = [field['bind'] for field in config['ui']['fields']]
            self.assertLess(binds.index('settings.native_model'), binds.index('settings.ratio'))

    def test_gpt_image_character_supports_text_only_and_optional_identity_reference(self):
        config = PluginCatalog(ROOT / 'plugins').capabilities()['image.gpt_image.character']
        self.assertEqual(config['references']['image'], {'min': 0, 'max': 1})
        instruction = config['task_instruction']
        self.assertIn('提供参考图时', instruction)
        self.assertIn('未提供参考图时', instruction)

    def test_h3_full_reference_does_not_require_a_video(self):
        capability_config = PluginCatalog(ROOT / 'plugins').capabilities()['video.reference']
        self.assertEqual(capability_config['references']['video'], {'min': 0, 'max': 3})

    def test_ltx_requirements_declare_models_without_permanent_missing_state(self):
        capabilities = PluginCatalog(ROOT / 'plugins').capabilities()
        for capability_id in ('video.ltx2_5.text_to_video', 'video.ltx2_5.image_to_video'):
            requirements = capabilities[capability_id]['requirements']
            self.assertNotIn('missing', requirements)
            self.assertTrue(any('ltx-2.5-22b-distilled-transformer' in item
                                for item in requirements['models']))

    def test_revision_uses_content_not_mtime(self):
        import os
        catalog = self.catalog()
        first = catalog.capabilities()['example.create']['plugin_revision']
        handler = self.folder / 'handler.py'
        original = handler.stat()
        os.utime(handler, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
        self.assertEqual(catalog.capabilities()['example.create']['plugin_revision'], first)
        content = handler.read_text(encoding='utf-8')
        handler.write_text(content.replace('ready', 'error'), encoding='utf-8')
        os.utime(handler, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertNotEqual(catalog.capabilities()['example.create']['plugin_revision'], first)

    def test_plugin_directory_is_at_project_root(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(ProjectPaths.from_root(ROOT).plugins, ROOT / 'plugins')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workflows = Path(self.temp.name)
        self.folder = self.workflows / 'example'
        self.folder.mkdir(parents=True)
        self.manifest = {
            'schema_version': 1, 'id': 'example', 'version': '1.0.0',
            'categories': [{'id': 'custom', 'name': 'Custom'}],
            'ui_models': [{'id': 'example', 'name': 'Example', 'category': 'custom', 'functions': [{'capability_id': 'example.create', 'name': 'Create'}]}],
            'modes': [{'id': 'direct', 'name': 'Direct'},
                      {'id': 'review', 'name': 'Review', 'handler': 'handler.py:review'}],
            'capabilities': {'example.create': {
                'kind': 'image', 'mode': 'create', 'category': 'custom',
                'file': 'workflow.json', 'processing_modes': ['direct', 'review'],
                'ui': {'version':1, 'fields': [{'bind':'settings.ratio','component':'select','label':'Ratio','options':[{'value':'16:9','label':'16:9'}],'default':'16:9'}]},
                'parameters': {'strength': {'type': 'number', 'default': 0.7, 'minimum': 0, 'maximum': 1}},
            }},
        }
        (self.folder / 'workflow.json').write_text('{}', encoding='utf-8')
        (self.folder / 'INSTALL.md').write_text('# Install\n\nNo external dependencies.\n', encoding='utf-8')
        (self.folder / 'handler.py').write_text('async def review(request, runtime):\n    return {"status": "ready"}\n', encoding='utf-8')

    def test_install_guide_is_required(self):
        (self.folder / 'INSTALL.md').unlink()
        self.assertIn('INSTALL.md', self.catalog().scan()[1][0]['error'])

    def catalog(self):
        (self.folder / 'plugin.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        return PluginCatalog(self.workflows)

    def test_custom_category_and_modes_discovered_without_import(self):
        (self.folder / 'handler.py').write_text('raise RuntimeError("not discovery")', encoding='utf-8')
        catalog = self.catalog()
        plugins, errors = catalog.scan()
        self.assertEqual(errors, [])
        self.assertEqual(plugins[0]['capabilities']['example.create']['category'], 'custom')
        public = catalog.public()
        self.assertNotIn('handler', public['items'][0]['modes'][1])
        self.assertEqual(public['categories'][0]['id'], 'custom')

    def test_translation_action_references_are_plugin_scoped(self):
        action = {'id': 'example.translate', 'name': 'Translate', 'scope': 'automation',
                  'handler': 'handler.py:review',
                  'input_schema': {'type': 'object', 'properties': {}}}
        self.manifest['actions'] = [action]
        self.manifest['prompt_translation_action'] = 'example.translate'
        config = self.catalog().capabilities()['example.create']
        self.assertEqual(capability('example.create', config)['prompt_translation_action'], 'example.translate')
        for invalid in ('foreign.translate', 42):
            self.manifest['prompt_translation_action'] = invalid
            self.assertTrue(self.catalog().scan()[1])
        self.manifest['prompt_translation_action'] = 'example.translate'
        action.update(scope='resource', source_types=['image'])
        self.assertTrue(self.catalog().scan()[1])

    def test_declared_assets_are_required_contained_and_versioned(self):
        sample = self.folder / 'voice.mp3'
        sample.write_bytes(b'first audio')
        self.manifest['assets'] = ['voice.mp3']
        first = self.catalog().capabilities()['example.create']['plugin_revision']
        sample.write_bytes(b'updated audio with different size')
        second = self.catalog().capabilities()['example.create']['plugin_revision']
        self.assertNotEqual(first, second)
        sample.unlink()
        self.assertTrue(self.catalog().scan()[1])
        self.manifest['assets'] = ['../outside.mp3']
        self.assertTrue(self.catalog().scan()[1])
        self.manifest['assets'] = 'not-a-list'
        self.assertTrue(self.catalog().scan()[1])

    def test_application_registration_and_disabled_visibility(self):
        (self.folder / 'ui').mkdir()
        (self.folder / 'ui/page.vue').write_text('<template><main /></template>', encoding='utf-8')
        self.manifest['application'] = {'name': 'Editor', 'entry': 'ui/page.vue', 'startup': 'handler.py:review'}
        catalog = self.catalog()
        app = catalog.public()['applications'][0]
        self.assertEqual(app['id'], 'example')
        self.assertNotIn('startup', app)
        self.assertNotIn('_plugin_revision', catalog.public()['items'][0])
        self.manifest['enabled'] = False
        self.assertEqual(self.catalog().public()['applications'], [])

    def test_collaboration_ui_is_plugin_local_and_published(self):
        (self.folder / 'ui').mkdir()
        (self.folder / 'ui/Collaboration.vue').write_text('<template><section /></template>', encoding='utf-8')
        self.manifest['collaboration_ui'] = 'ui/Collaboration.vue'
        config = self.catalog().capabilities()['example.create']
        published = capability('example.create', config)
        self.assertEqual(published['plugin_folder'], 'example')
        self.assertEqual(published['collaboration_ui'], 'ui/Collaboration.vue')
        for invalid in ('../Collaboration.vue', 'handler.py', 'ui/missing.vue'):
            self.manifest['collaboration_ui'] = invalid
            self.assertTrue(self.catalog().scan()[1])

    def test_application_rejects_invalid_entries_and_output_rules(self):
        (self.folder / 'page.vue').write_text('<template><main /></template>', encoding='utf-8')
        (self.folder / 'ui').mkdir()
        (self.folder / 'ui/page.vue').write_text('<template><main /></template>', encoding='utf-8')
        for changes in ({'entry': '../outside.vue'}, {'entry': 'handler.py'}, {'entry': 'page.vue'},
                        {'resource_entry': '../outside.vue'}, {'startup': '../outside.py:run'},
                        {'source_types': 'video'}, {'source_types': ['unknown']},
                        {'library_outputs': {'directory': '..', 'filenames': ['final.mp4']}},
                        {'library_outputs': {'directory': 'renders', 'filenames': ['../final.mp4']}}):
            with self.subTest(changes=changes):
                self.manifest['application'] = {'name': 'Editor', 'entry': 'ui/page.vue', **changes}
                plugins, errors = self.catalog().scan()
                self.assertFalse(plugins)
                self.assertEqual(len(errors), 1)

    def test_handler_relative_imports_and_revision_isolation(self):
        (self.folder / 'helper.py').write_text('VALUE = "first"\n', encoding='utf-8')
        (self.folder / 'handler.py').write_text('from .helper import VALUE\ndef review(request, runtime):\n    return VALUE\n', encoding='utf-8')
        catalog = self.catalog()
        config = catalog.capabilities()['example.create']
        old_handler = catalog.handler(config, 'review')
        self.assertEqual(old_handler(None, None), 'first')
        (self.folder / 'helper.py').write_text('VALUE = "second revision"\n', encoding='utf-8')
        updated = catalog.capabilities()['example.create']
        self.assertNotEqual(config['plugin_revision'], updated['plugin_revision'])
        self.assertEqual(catalog.handler(updated, 'review')(None, None), 'second revision')
        self.assertEqual(old_handler(None, None), 'first')

    def test_registry_ignores_old_registration(self):
        self.catalog()
        (self.workflows / 'registry.json').write_text('not valid JSON', encoding='utf-8')
        self.assertEqual(set(WorkflowRegistry(self.workflows, lambda names: {}).all()), {'example.create'})

    def test_unregistered_modes_are_not_inferred_from_model(self):
        config = {'kind': 'video', 'mode': 'reference', 'model_family': 'minimax'}
        self.assertFalse(capability('video.reference', config)['collaboration_supported'])

    def test_ui_hierarchy_is_declared_by_plugin(self):
        catalog = self.catalog()
        published = capability('example.create', catalog.capabilities()['example.create'])
        self.assertEqual(published['selector_model'], {
            'id':'example', 'name':'Example', 'plugin_id':'example',
            'selector_order': 0, 'default': False,
        })
        self.assertEqual(published['mode_name'], 'Create')
        self.assertEqual(published['parameters']['strength']['default'], 0.7)
        self.assertEqual(published['ui']['fields'][0]['default'], '16:9')
        self.manifest['ui_models'][0]['functions'][0]['capability_id'] = 'missing'
        self.assertIn('Invalid UI function capability', self.catalog().scan()[1][0]['error'])

    def test_ui_hierarchy_rejects_missing_models_and_duplicate_functions(self):
        model = self.manifest.pop('ui_models')
        self.assertIn('declare ui_models', self.catalog().scan()[1][0]['error'])
        self.manifest['ui_models'] = model
        model[0]['functions'] *= 2
        self.assertIn('Invalid UI function capability', self.catalog().scan()[1][0]['error'])

    def test_ui_model_order_and_default_are_plugin_declared(self):
        model = self.manifest['ui_models'][0]
        model.update(selector_order=20, default=True)
        published = capability('example.create', self.catalog().capabilities()['example.create'])
        self.assertEqual(published['selector_model']['selector_order'], 20)
        self.assertTrue(published['selector_model']['default'])
        duplicate = copy.deepcopy(model)
        duplicate['id'] = 'second'
        duplicate['functions'] = [{'capability_id': 'example.other', 'name': 'Other'}]
        self.manifest['capabilities']['example.other'] = copy.deepcopy(self.manifest['capabilities']['example.create'])
        self.manifest['ui_models'].append(duplicate)
        self.assertIn('Invalid or duplicate UI model selector_order', self.catalog().scan()[1][0]['error'])

    def test_unmapped_generation_requires_explicit_hidden_declaration(self):
        other = copy.deepcopy(self.manifest['capabilities']['example.create'])
        self.manifest['capabilities']['example.other'] = other
        self.assertIn('missing from ui_models: example.other', self.catalog().scan()[1][0]['error'])
        other['ui_hidden'] = True
        self.assertEqual(self.catalog().scan()[1], [])
        other['ui_hidden'] = 'true'
        self.assertIn('ui_hidden must be a boolean', self.catalog().scan()[1][0]['error'])

    def test_ui_control_config_rejects_invalid_ranges_and_defaults(self):
        config = self.manifest['capabilities']['example.create']['ui']['fields'][0]
        config['default'] = '9:16'
        self.assertIn('Ratio选项无效', self.catalog().scan()[1][0]['error'])
        config['default'] = '16:9'
        config['minimum'] = 2
        config['maximum'] = 1
        self.assertIn('Invalid UI range', self.catalog().scan()[1][0]['error'])

    def test_builtin_controls_are_plugin_owned(self):
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        self.assertIn('settings.h3_camera_lora', {f['bind'] for f in configs['video.reference']['ui']['fields']})
        self.assertEqual(next(f for f in configs['tts.describe']['ui']['fields'] if f['bind']=='settings.voice_speed')['normal_chars_per_second'], 4.5)
        self.assertIn('settings.music_bpm', {f['bind'] for f in configs['music.ace_step.background']['ui']['fields']})
        preset = configs['music.preset']
        self.assertTrue({'settings.music_style_id', 'settings.singer_id', 'settings.voice_texture_id'} <= {f['bind'] for f in preset['ui']['fields']})

    def test_builtin_ui_deduplicates_aliases_and_preserves_api(self):
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        self.assertNotIn('image.text_to_image', configs)
        self.assertNotIn('image.image_to_image', configs)
        self.assertNotIn('image.character', configs)
        self.assertNotIn('tts.clone', configs)
        self.assertIn('selector_model', configs['image.krea2.text_to_image'])
        for mode in ('text_to_image', 'image_to_image', 'character'):
            config = configs[f'image.krea2.{mode}']
            published = capability(f'image.krea2.{mode}', config)
            self.assertEqual(published['selector_model']['id'], 'krea2')
            self.assertTrue({'settings.ratio', 'settings.resolution', 'settings.style_id'} <= {f['bind'] for f in published['ui']['fields']})
        self.assertEqual(configs['video.reference']['mode_name'], '全能参考')
        self.assertIn('settings.variant', {f['bind'] for f in configs['video.reference']['ui']['fields']})
        self.assertTrue(all(config.get('selector_model') for config in configs.values() if config['plugin_id']=='qwen-image'))

    def test_krea_modes_and_single_prompt_storyboard(self):
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        modes = {config['mode'] for config in configs.values()
                 if config['plugin_id'] == 'krea2' and config.get('selector_model')}
        self.assertEqual(modes, {'text_to_image', 'image_to_image', 'character', 'scene', 'storyboard_4'})
        self.assertNotIn('image.krea2.storyboard_6', configs)
        spec = importlib.util.spec_from_file_location('krea_compiler_test', ROOT / 'plugins/krea2/compiler.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = configs['image.krea2.storyboard_4']
        workflow = {node: {'inputs': {}} for node in config['shot_nodes']}
        with patch.object(module, 'apply_image_dimensions'), patch.object(module, 'apply_storyboard_grid'), \
             patch.object(module, 'bind_inputs'), patch.object(module, 'resolve_style_selectors'):
            module.prepare(workflow, config, SimpleNamespace(params={}, prompt='A person enters a room and sits down.'), {'image': ['scene.png', 'person.png']}, 'test', 'A person enters a room and sits down.')
        for index, node in enumerate(config['shot_nodes']):
            prompt = workflow[node]['inputs']['prompt']
            self.assertIn('A person enters a room and sits down.', prompt)
            self.assertIn(f'frame {index + 1} of 4', prompt)

    def test_krea_numbered_shots_keep_context_without_repeating_other_shots(self):
        registry = WorkflowRegistry(ROOT / 'plugins', lambda names: {})
        config = registry.all()['image.krea2.storyboard_4']
        compiler = PluginCatalog(ROOT / 'plugins').compiler(config)
        import sys
        module = sys.modules[compiler.__module__]
        raw = '同一个房间，同一个人。\n镜头一：推门\n镜头二：走近\n镜头三：坐下\n镜头四：闭眼'
        style = {'id': 'test', 'prompt': 'STYLE {prompt}'}
        for explicit in (None, [], ['推门', '走近', '坐下', '闭眼']):
            with self.subTest(explicit=explicit):
                graph = registry.load('image', config['file'])
                request = SimpleNamespace(prompt=raw, params={'shots': explicit, 'style_id': 'test', 'width': 1024, 'height': 576})
                runtime = SimpleNamespace(style_items=lambda: ([style], []))
                with self.subTest(runtime='explicit'):
                    compiler(graph, config, request, {'image': ['scene.png', 'person.png']}, 'test', 'STYLE ' + raw, runtime=runtime)
                for index, text in enumerate(['推门', '走近', '坐下', '闭眼']):
                    value = graph[config['shot_nodes'][index]]['inputs']['prompt']
                    self.assertIn(text, value)
                    self.assertEqual(value.count('STYLE'), 1)
                    for other in set(['推门', '走近', '坐下', '闭眼']) - {text}:
                        self.assertNotIn(other, value)
                    if not explicit:
                        self.assertIn('同一个房间', value)
                self.assertEqual(graph['5']['inputs']['image'], 'scene.png')
                self.assertEqual(graph['7']['inputs']['image'], 'person.png')

    def test_krea_prompt_headings_and_invalid_explicit_shots(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        config = catalog.capabilities()['image.krea2.storyboard_4']
        compiler = catalog.compiler(config)
        import sys
        module = sys.modules[compiler.__module__]
        for prompt in ('1. enter\n2. walk\n3. sit\n4. sleep', 'Shot 1: enter\nShot 2: walk\nShot 3: sit\nShot 4: sleep'):
            self.assertEqual(module.storyboard_shots(prompt, 4), ['enter', 'walk', 'sit', 'sleep'])
        for shots in (['one'], ['', 'two', 'three', 'four'], 'not a list'):
            with patch.object(module, 'apply_image_dimensions'), patch.object(module, 'apply_storyboard_grid'), \
                 patch.object(module, 'bind_inputs'), patch.object(module, 'resolve_style_selectors'):
                with self.assertRaises(ValueError):
                    compiler({}, config, SimpleNamespace(prompt='story', params={'shots': shots}), {'image': []}, 'test', 'story')

    def test_builtin_postprocessing_and_preview_filter(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        source = {'kind': 'video', 'status': 'completed', 'request': {'params': {'video_model': 'minimax', 'speed': 'preview', 'latent_checkpoint_ready': True, 'latent_checkpoint':'saved.h3latent.safetensors'}}}
        with patch('backend.modules.shared.plugin_runtime.PluginRuntime.comfyui_output_file', return_value=Path('saved')):
            actions = discover_actions(catalog, source=source, context=SimpleNamespace(paths=SimpleNamespace(plugins=ROOT/'plugins')))
        ids = {item['id'] for item in actions}
        self.assertNotIn('preview_refine_fast', ids)
        self.assertNotIn('preview_refine_stable', ids)
        self.assertIn('ltx_ultra', ids)
        self.assertIn('h3_refine', ids)
        source['request']['params']['h3_checkpoint_kind'] = 'sigma_intermediate'
        with patch('backend.modules.shared.plugin_runtime.PluginRuntime.comfyui_output_file', return_value=Path('saved')):
            ids = {item['id'] for item in discover_actions(catalog, source=source, context=SimpleNamespace(paths=SimpleNamespace(plugins=ROOT/'plugins')))}
        self.assertIn('h3_refine', ids)
        self.assertNotIn('preview_refine_fast', ids)
        self.assertTrue(all('handler' not in item for item in public_actions(actions)))
        self.assertEqual(discover_actions(catalog, source={'kind':'video','status':'running'}), [])
        image = discover_actions(catalog, source={'kind':'image','status':'completed'})
        self.assertEqual({item['id'] for item in image}, {'split','split_6','krea2_upscale'})
        for action in actions:
            self.assertTrue(action.get('description'))
            self.assertEqual(public_actions([action])[0]['description'], action['description'])

    def test_postprocess_description_is_optional_string(self):
        action = {'id':'test','name':'Test','scope':'resource','capability_id':'example.create','source_types':['image'], 'ui':{'version':1,'fields':[]}}
        self.manifest['actions'] = [action]
        self.assertEqual(self.catalog().scan()[1], [])
        action['description'] = 123
        self.assertIn('description must be a string', self.catalog().scan()[1][0]['error'])

    def test_audio_postprocessor_discovery_and_prepare(self):
        config = self.manifest['capabilities']['example.create']
        config.update(kind='audio', operation='postprocess', references={'audio':{'min':1,'max':1}})
        self.manifest['actions'] = [{'id':'normalize','name':'Normalize','model_name':'Audio Pipeline','scope':'resource','capability_id':'example.create','source_types':['tts','music','audio'], 'ui':{'version':1,'fields':[]}}]
        self.manifest['ui_models'] = []
        catalog = self.catalog()
        source = {'id':'tts-example', 'kind':'tts', 'status':'completed', 'artifact_name':'voice.wav', 'request':{'text':'hello'}}
        self.assertEqual(discover_actions(catalog, source=source)[0]['id'], 'normalize')
        paths = SimpleNamespace(artifacts=self.workflows, uploads=self.workflows/'uploads', plugins=self.workflows)
        (self.workflows/'voice.wav').write_bytes(b'example')
        with patch('backend.modules.shared.plugin_runtime.PluginRuntime.job_request', return_value=source['request']):
            kind, request = asyncio.run(prepare_action(catalog,'normalize',{'parameters':{'strength':0.5}},SimpleNamespace(paths=paths), source))
        self.assertEqual(kind,'audio')
        self.assertEqual(request.params['capability_id'],'example.create')
        self.assertEqual(request.params['_action_id'],'normalize')
        self.assertEqual(request.params['_action_name'],'Normalize')
        self.assertEqual(request.params['_action_model_name'],'Audio Pipeline')
        self.assertEqual(request.params['parent_job_id'],'tts-example')
        self.assertEqual(request.params['plugin_parameters'],{'strength':0.5})
        self.assertEqual(request.references,[])
        self.assertEqual(len(request.params['audios']),1)
        self.assertEqual(len(list(paths.uploads.glob('*.wav'))),1)

    def test_action_identity_becomes_task_snapshot_without_leaking_internal_params(self):
        from backend.modules.generation.service import generation_metadata
        params = {'capability_id':'example.create', '_action_id':'normalize',
                  '_action_name':'Normalize', '_action_model_name':'Audio Pipeline'}
        registry = Mock()
        registry.capability.return_value = {'kind':'audio', 'mode':'create', 'model_family':'example',
                                            'model_id':'example', 'model_name':'Example'}
        with patch('backend.modules.generation.service.registry_service', return_value=registry):
            snapshot = generation_metadata('audio', {'mode':'create', 'params':params})
        self.assertEqual((snapshot['model_name'], snapshot['mode_id'], snapshot['mode_name']),
                         ('Audio Pipeline', 'normalize', 'Normalize'))
        self.assertFalse(any(key.startswith('_action_') for key in params))

    def test_postprocessor_rejects_conflicting_actions(self):
        self.manifest['actions'] = [{'id':'test','name':'Test','scope':'resource','capability_id':'example.create','source_types':['image'], 'ui':{'version':1,'fields':[]}}] * 2
        self.assertIn('duplicate plugin action',self.catalog().scan()[1][0]['error'])

    def test_postprocess_variant_does_not_inherit_source_speed(self):
        registry = WorkflowRegistry(ROOT/'plugins',lambda names:{})
        self.assertEqual(registry.capability('video.upscale','preview')['mode'],'upscale')

    def test_refine_plugin_preserves_variant_and_parent(self):
        catalog = PluginCatalog(ROOT/'plugins')
        action = catalog.actions()['h3_refine']
        handler = catalog.action_handler(action)
        original = {'prompt':'test','mode':'reference','params':{'video_model':'minimax','latent_checkpoint_ready':True,'latent_checkpoint':'saved.h3latent.safetensors','latent_width':768,'latent_height':432,'h3_checkpoint_kind':'sigma_intermediate','capability_id':'video.reference'}}
        source = {'id':'video-test','kind':'video','status':'completed','request':original,
                  'artifacts': [{'name': 'video-test.mp4'}]}
        runtime = SimpleNamespace(job_request=lambda job: original, comfyui_output_file=lambda name: Path('saved'), jobs=lambda:[])
        kind, request = handler({'action':action,'source':source,'inputs':{'width':1280,'height':720}}, runtime)
        self.assertEqual(kind,'video')
        self.assertEqual(request.params['speed'],'staged_refine')
        self.assertEqual(request.params['parent_job_id'],'video-test')
        self.assertEqual(request.params['videos'], ['task:output/video-test.mp4'])
        self.assertFalse(request.params['latent_checkpoint_ready'])

    def test_builtin_plugins_and_all_hooks_load(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        plugins, errors = catalog.scan()
        self.assertEqual(errors, [])
        self.assertEqual(len(plugins), 13)
        self.assertEqual(catalog.public()['applications'][0]['id'], 'film-studio')
        self.assertIn('ai-project-progress', [item['id'] for item in catalog.public()['project_tools']])
        self.assertEqual(sum(len(p['capabilities']) for p in plugins), 35)
        registry = WorkflowRegistry(ROOT / 'plugins', lambda names: {})
        for plugin in plugins:
            for key, config in plugin['capabilities'].items():
                registry.capability(key, 'normal')
                self.assertEqual(capability(key, config)['plugin_id'], plugin['id'])
                if config.get('compiler_handler'):
                    self.assertTrue(callable(catalog.compiler(config)))
                for field, loader in (('executor_handler', catalog.execution),
                                      ('speech_handler', catalog.speech),
                                      ('confirmation_handler', catalog.confirmation)):
                    if config.get(field):
                        self.assertTrue(callable(loader(config)))
                for mode in config['processing_modes']:
                    if mode['id'] != 'direct':
                        self.assertTrue(callable(catalog.handler(config, mode['id'])))
        from backend.modules.collaboration.prompts import agent_skill_prompt
        self.assertTrue(agent_skill_prompt('minimax-h3', 'reference', 'video.reference'))
        handler = catalog.handler(catalog.capabilities()['video.reference'], 'compile')
        import sys
        prompts = sys.modules[handler.__module__.rsplit('.', 1)[0] + '.prompts']
        self.assertTrue(prompts.PLATFORM_SYSTEM.is_file())
        h3 = catalog.capabilities()['video.reference']
        self.assertEqual({m['id'] for m in h3['processing_modes']}, {'direct', 'compile', 'director'})

    def test_native_executor_is_registered_without_platform_whitelist(self):
        config = self.manifest['capabilities']['example.create']
        config.update(executor='third-party-engine', executor_handler='handler.py:execute',
                      model_id='custom-model', name='Custom generation')
        config.pop('file')
        (self.folder / 'handler.py').write_text(
            'from backend.integrations.native import NativeExecutionResult\n'
            'def execute(context):\n'
            '    return NativeExecutionResult([context.output_dir / "custom.png"], 32, 24)\n',
            encoding='utf-8')
        catalog = self.catalog()
        config = catalog.capabilities()['example.create']
        result = catalog.execution(config)(SimpleNamespace(output_dir=self.folder))
        self.assertEqual(result.paths, [self.folder / 'custom.png'])
        self.assertEqual(result.width, 32)
        public = capability('example.create', config)
        self.assertEqual(public['model'], 'custom-model')
        self.assertEqual(public['name'], 'Custom generation')
        self.assertEqual(public['ratios'], ['16:9'])
        self.assertEqual(public['resolutions'], [])

    def test_compiler_service_injection_and_plain_signature(self):
        self.manifest['capabilities']['example.create']['compiler_handler'] = 'compiler.py:prepare'
        for service_aware in (False, True):
            with self.subTest(service_aware=service_aware):
                signature = ', runtime=None' if service_aware else ''
                expression = 'runtime.project_id' if service_aware else 'job_id'
                (self.folder / 'compiler.py').write_text(
                    f'def prepare(workflow, config, request, media, job_id, prompt{signature}):\n'
                    f'    workflow["result"] = {expression}\n', encoding='utf-8')
                catalog = self.catalog()
                config = catalog.capabilities()['example.create']
                workflow = {}
                catalog.prepare(config, workflow, None, {}, 'job-test', '',
                                SimpleNamespace(project_id='project-test'))
                self.assertEqual(workflow['result'], 'project-test' if service_aware else 'job-test')

    def test_execution_hooks_cannot_escape_plugin_folder(self):
        (self.folder.parent / 'outside.py').write_text('def run(): pass\n', encoding='utf-8')
        for field in ('executor_handler', 'speech_handler', 'confirmation_handler', 'compiler_handler'):
            with self.subTest(field=field):
                config = self.manifest['capabilities']['example.create']
                config[field] = '../outside.py:run'
                plugins, errors = self.catalog().scan()
                self.assertFalse(plugins)
                self.assertIn('outside its folder', errors[0]['error'])
                config.pop(field)

    def test_collaboration_skills_and_aliases_are_plugin_owned(self):
        from backend.modules.collaboration.prompts import agent_skill_prompt, agent_capability
        self.assertTrue(agent_skill_prompt('music3', 'creative'))
        self.assertTrue(agent_skill_prompt('music3', 'preset'))
        self.assertEqual(agent_capability('music3', 'preset')['skill_mode'], 'preset')
        with self.assertRaises(ValueError):
            agent_capability('unregistered-model', 'unknown')
        with self.assertRaises(ValueError):
            agent_capability('qwen', 'scene')

    def test_invalid_capability_metadata_is_isolated(self):
        config = self.manifest['capabilities']['example.create']
        for field, value in (('model_aliases', 'bad'), ('mode_aliases', [{}]),
                             ('duration', {'min': 1, 'max': 0, 'default': 3}),
                             ('dimension_alignment', 0), ('model_name', [])):
            with self.subTest(field=field):
                config[field] = value
                plugins, errors = self.catalog().scan()
                self.assertFalse(plugins)
                self.assertIn(field, errors[0]['error'])
                config.pop(field)

    def test_h3_graph_binding_and_validation_survive_plugin_migration(self):
        import sys
        from backend.core.schemas import GenerateRequest
        catalog = PluginCatalog(ROOT / 'plugins')
        config = catalog.capabilities()['video.reference']
        compiler = catalog.compiler(config)
        graph = sys.modules[compiler.__module__.rsplit('.', 1)[0] + '.graph']
        workflow = {'ref': {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': {
            'ref_images.ref_image_0': ['old', 0]}},
            'sample': {'class_type': 'KSampler', 'inputs': {}}}
        request = GenerateRequest(prompt='A scene', mode='reference', duration_seconds=3)
        graph.apply_h3_reference_bindings(workflow, {}, request, ['new.png'], ['new.mp4'], ['new.wav'])
        self.assertEqual(workflow['gateway_image_0_0']['inputs']['image'], 'new.png')
        self.assertEqual(workflow['gateway_video_0_0']['inputs']['video'], 'new.mp4')
        self.assertEqual(workflow['gateway_audio_0_0']['inputs']['audio'], 'new.wav')
        graph.inject_h3_checkpoint_save(workflow, {'save_h3_latent': {'node': 'sample'}}, 'job-test')
        self.assertEqual(workflow['gateway_h3_latent_save']['inputs']['checkpoint_id'], 'job-test')
        handler = catalog.handler(config, 'compile')
        analysis = sys.modules[handler.__module__.rsplit('.', 1)[0] + '.analysis']
        self.assertTrue(analysis.agent_prompt_issues('A short sentence', 'minimax-h3', 'reference'))

    def test_speech_and_confirmation_adjustments_are_plugin_owned(self):
        from backend.core.schemas import TTSRequest
        catalog = PluginCatalog(ROOT / 'plugins')
        configs = catalog.capabilities()
        speech_config = next(item for item in configs.values()
                             if item['plugin_id'] == 'cosyvoice3' and item['mode'] == 'preset')
        request = TTSRequest(text='Test', mode='preset', speed=1.2)
        speech = catalog.speech(speech_config)
        result = speech(request, {}, SimpleNamespace(voice_sample=lambda preset: self.folder / 'sample.wav'))
        self.assertEqual(result.reference_audio, str(self.folder / 'sample.wav'))
        self.assertEqual(result.speed, 1.2)
        with self.assertRaises(ValueError):
            speech(request, {}, SimpleNamespace(voice_sample=lambda preset: None))
        config = next(item for item in configs.values() if item.get('confirmation_handler'))
        patch = catalog.confirmation(config)({}, {'generation_payload': {'music_bpm': 88}}, None)
        self.assertEqual(patch, {'lyrics': '[Instrumental]', 'settings': {'music_bpm': 88}})
        ace = configs['music.ace_step.background']
        graph = {
            'encoder': {'class_type': 'TextEncodeAceStepAudio1.5', 'inputs': {}},
            'latent': {'class_type': 'EmptyAceStep1.5LatentAudio', 'inputs': {}},
        }
        catalog.compiler(ace)(graph, ace, SimpleNamespace(duration_seconds=30), {}, 'test', '')
        self.assertEqual(graph['encoder']['inputs']['lyrics'], '[Instrumental]')
        self.assertEqual(graph['encoder']['inputs']['duration'], 30.0)

    def test_minimax_music_presets_are_plugin_owned(self):
        configs = PluginCatalog(ROOT / 'plugins').capabilities()
        preset = capability('music.preset', configs['music.preset'])
        self.assertIn('prompt_template', preset['ui'])
        self.assertEqual(preset['mode'], 'create')
        self.assertEqual(preset['mode_name'], '预设创作')
        self.assertEqual([len(f['options']) for f in preset['ui']['fields'] if f['bind'] in {'settings.music_style_id','settings.singer_id','settings.voice_texture_id'}], [10, 2, 9])
        self.assertTrue(all(item['prompt'] for f in preset['ui']['fields'] if f['bind'] in preset['ui']['prompt_template']['fields'] for item in f['options']))
        self.assertEqual(configs['music.create']['mode_name'], '自由创作')

    def test_invalid_plugin_isolated_and_traversal_rejected(self):
        self.manifest['capabilities']['example.create']['file'] = '../outside.json'
        (self.folder.parent / 'outside.json').write_text('{}', encoding='utf-8')
        plugins, errors = self.catalog().scan()
        self.assertFalse(plugins)
        self.assertIn('outside its folder', errors[0]['error'])

    def test_duplicate_capabilities_isolated(self):
        catalog = self.catalog()
        other = self.folder.parent / 'other'
        other.mkdir()
        value = copy.deepcopy(self.manifest)
        value['id'] = 'other'
        value['capabilities']['example.create']['executor'] = 'native'
        value['capabilities']['example.create']['executor_handler'] = 'handler.py:execute'
        (other / 'handler.py').write_text('def execute(context):\n    return None\n', encoding='utf-8')
        (other / 'INSTALL.md').write_text('# Install\n\nNo external dependencies.\n', encoding='utf-8')
        value['capabilities']['example.create'].pop('file')
        value['modes'] = value['modes'][:1]
        value['capabilities']['example.create']['processing_modes'] = ['direct']
        (other / 'plugin.json').write_text(json.dumps(value), encoding='utf-8')
        plugins, errors = catalog.scan()
        self.assertEqual(len(plugins), 1)
        self.assertIn('Duplicate capabilities', errors[0]['error'])

    def test_revision_changes_with_workflow(self):
        catalog = self.catalog()
        old = catalog.capabilities()['example.create']['plugin_revision']
        (self.folder / 'workflow.json').write_text('{"changed":true}', encoding='utf-8')
        self.assertNotEqual(old, catalog.capabilities()['example.create']['plugin_revision'])

    def test_parameters_reject_unknown_types_and_nonfinite(self):
        config = self.catalog().capabilities()['example.create']
        self.assertEqual(validate_parameters(config, {}), {'strength': 0.7})
        for values in ({'unknown': 1}, {'strength': True}, {'strength': 2}, {'strength': float('nan')}):
            with self.assertRaises(ValueError):
                validate_parameters(config, values)
        config['parameters']['required'] = {'type': 'string', 'required': True}
        with self.assertRaises(ValueError):
            validate_parameters(config, {})

    def test_invalid_bound_isolated_at_registration(self):
        self.manifest['capabilities']['example.create']['parameters']['strength']['minimum'] = 'bad'
        self.assertTrue(self.catalog().scan()[1])

    def test_declarative_bindings_preserve_scalar_and_unrelated_nodes(self):
        graph = {'1': {'inputs': {'strength': 0}}, '2': {'inputs': {'text': 'negative'}}}
        config = {'file': 'workflow.json', 'parameter_bindings': {'strength': [{'node': '1', 'input': 'strength'}]}}
        request = SimpleNamespace(params={'plugin_parameters': {'strength': 0.25}, 'seed': 0}, duration_seconds=5)
        apply_parameter_bindings(graph, config, request)
        self.assertEqual(graph['1']['inputs']['strength'], 0.25)
        self.assertEqual(graph['2']['inputs']['text'], 'negative')
        self.assertEqual(request.params['seed'], 0)

    def test_cosyvoice_hook_preserves_text_speed_and_reference(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        config = catalog.capabilities()['tts.cosyvoice3.clone']
        graph = {'1': {'class_type': 'FL_CosyVoice3_Instruct2', 'inputs': {}},
                 '2': {'class_type': 'LoadAudio', 'inputs': {}}}
        request = SimpleNamespace(text='hello', speed=1.4, instruction='calm', speaker_preset='')
        catalog.compiler(config)(graph, config, request, {'audio': ['sample.wav']}, 'test', '')
        self.assertEqual(graph['1']['inputs']['speed'], 1.4)
        self.assertEqual(graph['1']['inputs']['text'], 'hello')
        self.assertEqual(graph['2']['inputs']['audio'], 'sample.wav')


if __name__ == '__main__':
    unittest.main()
