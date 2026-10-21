import asyncio
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from backend.core.errors import GatewayError

from backend.modules.generation.actions import action_matches_source, discover_actions, execute_action, prepare_action, public_action, uploaded_source
from backend.modules.generation.plugins import PluginCatalog
from backend.modules.shared.plugin_runtime import PluginRuntime


ROOT = Path(__file__).resolve().parents[1]


class PluginActionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name) / 'commands'
        folder.mkdir()
        (folder / 'handler.py').write_text(
            'async def inspect(request, runtime):\n'
            '    return {"value": request["inputs"]["items"][0], "project_id": runtime.project_id}\n',
            encoding='utf-8')
        self.action = {
            'id':'commands.inspect','name':'Inspect','scope':'workspace','automation':True,
            'handler':'handler.py:inspect',
            'input_schema':{'type':'object','properties':{'items':{'type':'array','minItems':1,
                'items':{'type':'integer','minimum':1}}},'required':['items'],'additionalProperties':False},
        }
        self.manifest = {'schema_version':1,'id':'commands','version':'1.0.0',
                         'categories':[],'capabilities':{},'actions':[self.action]}
        self.folder = folder
        (self.folder/'INSTALL.md').write_text('# Install\n\nNo external dependencies.\n', encoding='utf-8')
        self.catalog = PluginCatalog(folder.parent)
        self.context = SimpleNamespace(paths=SimpleNamespace(plugins=folder.parent),
            db=SimpleNamespace(project=lambda key:{'id':key,'status':'active'}))
        self.submit = AsyncMock()

    def save(self):
        (self.folder/'plugin.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    async def test_action_only_plugin_async_result_without_generation(self):
        self.save()
        self.assertEqual(self.catalog.scan()[1], [])
        result = await execute_action(self.catalog,'commands.inspect',{'items':[2]},
                                      self.context,self.submit,project_id='p1')
        self.assertEqual(result, {'action_id':'commands.inspect','status':'completed',
                                  'result':{'value':2,'project_id':'p1'}})
        self.submit.assert_not_awaited()
        action = discover_actions(self.catalog, automation_only=True)[0]
        self.assertNotIn('handler', public_action(action))
        self.assertNotIn('plugin_folder', public_action(action))

    async def test_nested_schema_rejects_bad_values_before_handler(self):
        self.save()
        for inputs in ({'items':[]}, {'items':[True]}, {'items':[0]}, {'items':[1],'extra':1}, {'items':[float('nan')]}):
            with self.subTest(inputs=inputs), self.assertRaises(GatewayError) as caught:
                await prepare_action(self.catalog,'commands.inspect',inputs,self.context)
            self.assertEqual(caught.exception.status_code, 422)

    async def test_project_mismatch_and_missing_project_precede_plugin_execution(self):
        self.save()
        with patch('backend.modules.generation.actions.prepare_action', new_callable=AsyncMock) as prepare:
            with self.assertRaises(GatewayError) as caught:
                await execute_action(self.catalog,'commands.inspect',{},self.context,self.submit,
                                      source={'project_id':'p1'},project_id='p2')
            self.assertEqual(caught.exception.status_code,422)
            self.context.db.project = lambda key:None
            with self.assertRaises(GatewayError) as caught:
                await execute_action(self.catalog,'commands.inspect',{},self.context,self.submit,project_id='missing')
            self.assertEqual(caught.exception.status_code,404)
            prepare.assert_not_awaited()

    async def test_bad_schema_and_handler_paths_are_isolated(self):
        for change in ({'input_schema':{'type':'object','properties':{'n':{'type':'invalid'}}}},
                       {'input_schema':{'type':'object','$ref':'https://example.com/schema'}},
                       {'handler':'../outside.py:inspect'}):
            self.manifest['actions'] = [{**self.action,**change}]
            self.save()
            plugins, errors = self.catalog.scan()
            self.assertEqual(plugins,[])
            self.assertEqual(len(errors),1)

    async def test_duplicate_action_across_plugins_is_isolated(self):
        self.save()
        other = self.folder.parent/'other'
        other.mkdir()
        data = copy.deepcopy(self.manifest)
        data['id'] = 'other'
        (other/'handler.py').write_text('def inspect(request,runtime): return {}',encoding='utf-8')
        (other/'INSTALL.md').write_text('# Install\n\nNo external dependencies.\n',encoding='utf-8')
        (other/'plugin.json').write_text(json.dumps(data),encoding='utf-8')
        plugins, errors = self.catalog.scan()
        self.assertEqual(len(plugins),1)
        self.assertIn('Duplicate plugin actions', errors[0]['error'])

    async def test_source_schema_applies_to_all_media_kinds(self):
        for kind in ('image', 'video', 'tts', 'music', 'audio'):
            action = {**self.action, 'scope':'resource', 'source_types':[kind],
                      'source_schema':{'type':'object','properties':{'codec':{'const':'supported'}},'required':['codec']}}
            self.assertTrue(action_matches_source(action, {'kind':kind,'status':'completed','codec':'supported'}))
            self.assertFalse(action_matches_source(action, {'kind':kind,'status':'completed'}))
            self.assertFalse(action_matches_source(action, {'kind':kind,'status':'running','codec':'supported'}))

    async def test_availability_shared_by_discovery_and_execution(self):
        with (self.folder/'handler.py').open('a', encoding='utf-8') as handle:
            handle.write('\ndef available(request,runtime):\n'
                         '    return {"available":False,"reason":"missing auxiliary file"}\n')
        self.manifest['actions'] = [{**self.action, 'scope':'resource', 'source_types':['image'],
                                     'availability_handler':'handler.py:available'}]
        self.save()
        source = {'kind':'image','status':'completed'}
        self.assertEqual(discover_actions(self.catalog, source=source, context=self.context), [])
        unavailable = discover_actions(self.catalog, source=source, context=self.context, include_unavailable=True)[0]
        self.assertFalse(unavailable['available'])
        self.assertNotIn('availability_handler', public_action(unavailable))
        with self.assertRaises(GatewayError) as caught:
            await prepare_action(self.catalog,'commands.inspect',{'items':[2]},self.context,source)
        self.assertIn('missing auxiliary file', str(caught.exception.detail))

    async def test_invalid_source_and_lifecycle_declarations_are_isolated(self):
        for change in ({'source_schema':{'type':'object','properties':{'x':{'type':'bad'}}}},
                       {'availability_handler':'../outside.py:check'}, {'requires_latent':True}):
            self.manifest['actions'] = [{**self.action, **change}]
            self.save()
            self.assertEqual(self.catalog.scan()[0], [])
        self.manifest['actions'] = [self.action]
        self.manifest['resource_lifecycle'] = {'delete':'../outside.py:delete'}
        self.save()
        self.assertEqual(self.catalog.scan()[0], [])

    async def test_external_source_is_typed_and_category_preserved(self):
        from backend.core.schemas import GenerateRequest
        self.context.paths.uploads = self.folder/'uploads'
        self.context.paths.uploads.mkdir()
        self.context.paths.tasks = self.folder/'tasks'
        upload_id = 'a'*32
        (self.context.paths.uploads/f'{upload_id}.mp4').write_bytes(b'test')
        source = uploaded_source(self.context, upload_id)
        self.assertEqual(source['kind'], 'video')
        self.assertTrue(source['external'])
        self.assertNotIn('request', source)
        self.save()
        request = GenerateRequest(prompt='enhance')
        submit = AsyncMock(return_value={'job_id':'result'})
        with patch('backend.modules.generation.actions.prepare_action', new_callable=AsyncMock,
                   return_value=('video',request)):
            await execute_action(self.catalog,'commands.inspect',{},self.context,submit,
                                 source=source,project_id='p1',category_id='episode-2')
        self.assertEqual(request.category_id, 'episode-2')
        self.assertNotIn('parent_job_id', request.params)
        with self.assertRaises(GatewayError):
            uploaded_source(self.context, 'b'*32)

    async def test_translation_is_plugin_action_using_system_llm(self):
        catalog = PluginCatalog(ROOT/'plugins')
        context = SimpleNamespace(paths=SimpleNamespace(plugins=ROOT/'plugins'),
                                  db=SimpleNamespace(project=lambda key:{'id':key,'status':'active'}))
        draft = '<Subject 1>主角</Subject 1> <d>[Chinese]你好</d>'
        english = '<Subject 1>Main character</Subject 1> <d>[Chinese]你好</d>'
        with patch('backend.modules.collaboration.service.call_agent_model',
                   return_value=json.dumps({'english_prompt':english})) as llm:
            result = await execute_action(catalog,'h3_translate',{'text':draft},context,
                                          self.submit,project_id='p1')
            self.assertEqual(result['result']['english_prompt'],english)
            messages, limit = llm.call_args.args
            self.assertEqual(limit,7000)
            self.assertEqual(json.loads(messages[1]['content'])['chinese_draft'],draft)
            self.submit.assert_not_awaited()
        with patch('backend.modules.collaboration.service.call_agent_model',return_value='{}'):
            with self.assertRaises(GatewayError) as caught:
                await execute_action(catalog,'h3_translate',{'text':draft},context,
                                     self.submit,project_id='p1')
            self.assertEqual(caught.exception.status_code,502)

    async def test_speech_speed_validation_and_submission_preserve_project(self):
        catalog = PluginCatalog(ROOT/'plugins')
        context = SimpleNamespace(paths=SimpleNamespace(plugins=ROOT/'plugins'),
                                  db=SimpleNamespace(project=lambda key:{'id':key,'status':'active'}))
        for speed in (0.4,2.1,True):
            with self.assertRaises(GatewayError) as caught:
                await prepare_action(catalog,'speech_describe',
                    {'text':'hello','voice_description':'calm male','speed':speed},context)
            self.assertEqual(caught.exception.status_code,422)
        submit = AsyncMock(return_value={'job_id':'j1'})
        result = await execute_action(catalog,'speech_describe',
            {'text':'hello','voice_description':'calm male','speed':1.2},context,submit,project_id='p1')
        kind, request = submit.call_args.args
        self.assertEqual(kind,'tts')
        self.assertEqual(request.voice_model,'qwen3_tts')
        self.assertEqual(request.params['capability_id'], 'tts.describe')
        self.assertEqual(request.speed,1.2)
        self.assertEqual(request.internal_project_id,'p1')
        self.assertEqual(result['job_id'],'j1')

    async def test_plugin_runtime_invokes_capability_with_bound_context(self):
        invoke = AsyncMock(return_value={'job_id': 'image-one', 'status': 'queued'})
        runtime = PluginRuntime('workflow-studio', {}, self.context, project_id='p1',
                                category_id='episode-1', _invoke_capability=invoke)
        result = await runtime.invoke_capability(
            'image.qwen.text_to_image', 'sunrise', settings={'resolution': '1K'},
            parameters={'steps': 8}, idempotency_key='node-run-1')
        self.assertEqual(result['job_id'], 'image-one')
        payload = invoke.await_args.args[0]
        self.assertEqual(payload['capability_id'], 'image.qwen.text_to_image')
        self.assertEqual(payload['prompt_processing'], 'direct')
        self.assertEqual(invoke.await_args.kwargs, {
            'project_id': 'p1', 'category_id': 'episode-1', 'idempotency_key': 'node-run-1'})
        with self.assertRaisesRegex(ValueError, '项目不属于当前调用'):
            await runtime.invoke_capability('image.qwen.text_to_image', 'x', project_id='p2')

    async def test_plugin_runtime_passes_source_job_to_resource_action(self):
        source = {'id': 'video-one', 'kind': 'video', 'status': 'completed', 'project_id': 'p1'}
        context = SimpleNamespace(
            paths=SimpleNamespace(plugins=self.folder.parent), jobs={'video-one': source},
            db=SimpleNamespace(job=lambda key: source if key == 'video-one' else None))
        nested = AsyncMock(return_value={'action_id': 'video.refine', 'status': 'completed'})
        dispatcher = AsyncMock()
        runtime = PluginRuntime('workflow-studio', {}, context, project_id='p1',
                                _submit=self.submit, _invoke_capability=dispatcher)
        with patch('backend.modules.generation.actions.execute_action', nested):
            result = await runtime.execute_action('video.refine', {'strength': 0.4},
                                                  source_job_id='video-one')
        self.assertEqual(result['action_id'], 'video.refine')
        self.assertIs(nested.await_args.kwargs['source'], source)
        self.assertEqual(nested.await_args.kwargs['project_id'], 'p1')
        self.assertIs(nested.await_args.kwargs['invoke_capability'], dispatcher)
        with self.assertRaisesRegex(ValueError, '源任务不存在'):
            await runtime.execute_action('video.refine', {}, source_job_id='missing')


class ResourceLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = PluginCatalog(ROOT/'plugins')
        cls.config = cls.catalog.capabilities()['video.reference']
        cls.hooks = {name: cls.catalog._load_handler(cls.config, f'checkpoints.py:{name}')
                     for name in ('completed','recover','delete')}

    def setUp(self):
        from backend.core.schemas import GenerateRequest
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkpoint = self.root/'video-test_1.h3latent.safetensors'
        self.checkpoint.write_bytes(b'checkpoint')
        self.request = GenerateRequest(prompt='test', duration_seconds=5,
                                      params={'video_model':'minimax','width':768,'height':432})
        self.job = {'id':'video-test','kind':'video','status':'completed',
                    'request':self.request.model_dump(),
                    'artifacts': [{'name': 'video-test.mp4'}]}
        def update(job, parameters, **metadata):
            job['request']['params'].update(parameters)
            job.update(metadata)
        self.runtime = SimpleNamespace(
            comfyui_output_files=Mock(return_value=[self.checkpoint]),
            comfyui_output_file=Mock(return_value=self.checkpoint),
            save_job_file=Mock(return_value={'sha256': 'a' * 64, 'size': len(b'checkpoint')}),
            job_file=Mock(return_value=None),
            update_job_parameters=Mock(side_effect=update), free_comfyui_memory=Mock(),
            jobs=Mock(return_value=[self.job]), job_request=lambda job:job['request'])

    def hook(self, name, **event):
        self.hooks[name](event, self.runtime)

    def test_completion_persists_native_checkpoint_and_releases_memory(self):
        self.hook('completed', job=self.job, request=self.request, config={'save_h3_latent':{'node':'1'}})
        params = self.job['request']['params']
        self.assertTrue(params['latent_checkpoint_ready'])
        self.assertEqual(params['latent_checkpoint_owner'], self.job['id'])
        self.assertEqual(params['latent_size'], len(b'checkpoint'))
        self.assertEqual(len(params['latent_sha256']), 64)
        self.assertEqual(params['latent_frames'] % 17, 5)
        self.runtime.free_comfyui_memory.assert_called_once()

    def test_missing_checkpoint_warns_without_losing_generated_video(self):
        self.runtime.comfyui_output_files.return_value = []
        self.hook('completed', job=self.job, request=self.request, config={'save_h3_latent':True})
        self.assertFalse(self.job['latent_checkpoint_ready'])
        self.assertTrue(self.job['latent_checkpoint_warning'])
        self.runtime.free_comfyui_memory.assert_called_once()

    def test_recovery_is_local_and_ignores_other_models(self):
        foreign = copy.deepcopy(self.job)
        foreign['request']['generation'] = {'plugin_id':'another-model'}
        self.runtime.jobs.return_value.append(foreign)
        self.hook('recover')
        self.runtime.comfyui_output_files.assert_called_once_with(
            'MiniMaxH3/latent_checkpoints', 'video-test_*.h3latent.safetensors', detect=False)
        self.assertTrue(self.job['request']['params']['latent_checkpoint_ready'])
        self.assertNotIn('latent_checkpoint_ready', foreign['request']['params'])

    def test_deletion_preserves_running_references_and_child_ownership(self):
        params = self.job['request']['params']
        params.update(latent_checkpoint=self.checkpoint.name, latent_checkpoint_owner=self.job['id'])
        child = {'id':'child','status':'queued','request':{'params':dict(params)}}
        self.runtime.jobs.return_value.append(child)
        with self.assertRaises(RuntimeError):
            self.hook('delete', job=self.job)
        self.assertTrue(self.checkpoint.exists())
        child['status'] = 'completed'
        child['kind'] = 'video'
        self.hook('delete', job=child)
        self.assertTrue(self.checkpoint.exists())
        self.hook('delete', job=self.job)
        self.assertFalse(self.checkpoint.exists())

    def test_missing_comfyui_cache_still_protects_queued_refinement(self):
        params = self.job['request']['params']
        params.update(latent_checkpoint=self.checkpoint.name, latent_checkpoint_owner=self.job['id'])
        self.runtime.comfyui_output_file.return_value = None
        self.runtime.jobs.return_value.append({'id': 'child', 'status': 'queued',
                                              'request': {'params': dict(params)}})
        with self.assertRaises(RuntimeError):
            self.hook('delete', job=self.job)

    def test_refinement_links_and_restores_archived_dependency(self):
        compiler = self.catalog._load_handler(self.config, 'compiler.py:prepare')
        self.request.params.update(refine_mode='h3_refine', latent_archive_job='video-source',
                                   latent_checkpoint=self.checkpoint.name)
        self.runtime.link_job_file = Mock(return_value={'sha256': 'a' * 64, 'size': len(b'checkpoint')})
        self.runtime.restore_job_file = Mock()
        compiler({}, {}, self.request, {'image': [], 'video': [], 'audio': []},
                 self.job['id'], 'test', self.runtime)
        self.runtime.link_job_file.assert_called_once_with('video-source', 'native-latent', self.job['id'])
        self.runtime.restore_job_file.assert_called_once_with(self.job['id'], 'native-latent',
            'MiniMaxH3/latent_checkpoints/' + self.checkpoint.name)
        self.assertEqual(self.request.params['latent_archive_job'], self.job['id'])

    def test_refinement_reuses_only_verified_local_checkpoint(self):
        import hashlib
        compiler = self.catalog._load_handler(self.config, 'compiler.py:prepare')
        checksum = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.runtime.link_job_file = Mock(return_value={'sha256': checksum, 'size': self.checkpoint.stat().st_size})
        self.runtime.restore_job_file = Mock()
        for state in ('matching', 'wrong-size', 'wrong-hash', 'missing'):
            with self.subTest(state=state):
                self.request.params.update(refine_mode='h3_refine', latent_archive_job='video-source',
                                           latent_checkpoint=self.checkpoint.name)
                self.checkpoint.write_bytes(b'checkpoint' if state == 'matching' else
                                            b'bad' if state == 'wrong-size' else b'XXXXXXXXXX')
                self.runtime.comfyui_output_file.return_value = None if state == 'missing' else self.checkpoint
                self.runtime.restore_job_file.reset_mock()
                compiler({}, {}, self.request, {'image': [], 'video': [], 'audio': []},
                         self.job['id'], 'test', self.runtime)
                self.assertEqual(self.runtime.restore_job_file.call_count, int(state != 'matching'))

    def test_h3_discovery_uses_metadata_and_submission_checks_files(self):
        self.job['request']['params'].update(latent_checkpoint_ready=True,latent_checkpoint=self.checkpoint.name)
        action = self.catalog.actions()['h3_refine']
        availability = self.catalog.availability(action)
        self.assertTrue(availability({'action':action,'source':self.job},self.runtime)['available'])
        self.job['request']['generation'] = {'plugin_id':'another-model'}
        self.assertFalse(availability({'action':action,'source':self.job},self.runtime)['available'])
        self.job['request']['generation']['plugin_id'] = 'minimax-h3'
        self.runtime.comfyui_output_file.return_value = None
        self.assertTrue(availability({'action':action,'source':self.job},self.runtime)['available'])
        self.runtime.comfyui_output_file.assert_not_called()
        with self.assertRaises(GatewayError) as caught:
            self.catalog.action_handler(action)({'action':action,'source':self.job,
                'inputs':{'width':1280,'height':720}},self.runtime)
        self.assertEqual(caught.exception.status_code,409)
        self.assertFalse(availability({'action':action,'source':{'external':True}},self.runtime)['available'])

    def test_refinement_menu_checks_metadata_without_output_detection(self):
        self.job['request']['params'].update(latent_checkpoint_ready=True,
            latent_checkpoint=self.checkpoint.name, speed='quick_preview',
            h3_checkpoint_kind='sigma_intermediate')
        with patch('backend.modules.generation.actions.PluginRuntime', return_value=self.runtime), \
             patch('backend.modules.generation.actions.PluginSettings') as settings:
            settings.return_value.runtime.return_value = {}
            actions = discover_actions(self.catalog, scope='resource', source=self.job,
                context=SimpleNamespace(), include_unavailable=True)
        states = {action['id']:action['available'] for action in actions}
        self.assertTrue(states['h3_refine'])
        self.assertTrue(states['ltx_ultra'])
        self.assertNotIn('preview_refine_fast', states)
        self.assertNotIn('preview_refine_stable', states)
        self.runtime.comfyui_output_file.assert_not_called()
        self.runtime.comfyui_output_files.assert_not_called()

    def test_unified_h3_action_selects_native_refinement_workflow(self):
        action = self.catalog.actions()['h3_refine']
        handler = self.catalog.action_handler(action)
        for speed, kind, expected in (
            ('preview', 'completed_draft_latent', 'preview_refine_stable'),
            ('preview', 'sigma_intermediate', 'staged_refine'),
            ('quick_preview', 'denoised_preview_latent', 'staged_refine'),
            ('normal', 'completed_draft_latent', 'latent_refine'),
        ):
            with self.subTest(speed=speed, kind=kind):
                self.job['request']['params'].update(latent_checkpoint_ready=True,
                    latent_checkpoint=self.checkpoint.name, speed=speed, h3_checkpoint_kind=kind)
                _, request = handler({'action':action,'source':self.job,
                    'inputs':{'width':1280,'height':720}}, self.runtime)
                self.assertEqual(request.params['speed'], expected)

    def test_h3_refine_keeps_conditioning_linked_to_actual_upscaled_size(self):
        from backend.modules.generation.workflow_registry import WorkflowRegistry
        registry = WorkflowRegistry(ROOT / 'plugins', lambda names: {})
        config = registry.capability('video.reference', 'latent_refine')
        workflow = registry.load('video', config['file'])
        request = self.request.model_copy(update={'mode': 'reference', 'params': {
            **self.request.params, 'speed': 'latent_refine', 'latent_checkpoint': str(self.checkpoint),
        }})
        self.catalog.prepare(config, workflow, request, {'image': [], 'video': [], 'audio': []},
                             self.job['id'], request.prompt, self.runtime)
        upscaler_id, upscaler = next((key, node) for key, node in workflow.items()
                                      if node.get('class_type') == 'MiniMaxH3LearnedLatentUpscaleT8Advanced')
        conditioning = next(node for node in workflow.values()
                            if node.get('class_type') in {'MiniMaxH3ReferenceToVideo', 'MiniMaxH3ImageToVideo'})
        self.assertEqual(conditioning['inputs']['width'], [upscaler_id, 1])
        self.assertEqual(conditioning['inputs']['height'], [upscaler_id, 2])
        self.assertNotIn(upscaler.get('class_type'), {'MinimaxH3LatentUpscalerNode2D', 'MinimaxH3LatentUpscaler3D'})

    def test_catalog_dispatch_uses_request_plugin_identity(self):
        self.job['request']['generation'] = {'plugin_id':'another-model'}
        with patch.object(self.catalog, '_load_handler') as handler:
            self.catalog.resource_event('delete', SimpleNamespace(), job=self.job)
            handler.assert_not_called()
        self.assertTrue(all('resource_lifecycle' not in plugin for plugin in self.catalog.public()['items']))

    def test_delete_resource_permission_failure_is_reported_not_fatal(self):
        with patch.object(self.catalog, '_load_handler', side_effect=PermissionError('file is busy')):
            warnings = self.catalog.resource_event('delete', SimpleNamespace(), job=self.job)
        self.assertEqual(warnings[0]['code'], 'resource_cleanup_pending')

    def test_output_lookup_avoids_network_for_local_files_and_recovery(self):
        from backend.modules.shared.plugin_runtime import PluginRuntime
        context = SimpleNamespace(comfyui_output_dir=self.root, comfyui_output_locations={},
                                  comfyui_url='http://127.0.0.1:8189')
        runtime = PluginRuntime('test',{},context)
        with patch('backend.modules.settings.SettingsService.local_comfyui_output_directory') as detect:
            self.assertEqual(runtime.comfyui_output_file(self.checkpoint.name),self.checkpoint)
            self.assertEqual(runtime.comfyui_output_files('', '*.safetensors',detect=False),[self.checkpoint])
            self.assertIsNone(runtime.comfyui_output_file('../outside'))
            detect.assert_not_called()


class PluginActionHTTPTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.interfaces.http.dependencies import auth
        self.app = app
        previous = app.dependency_overrides.copy()
        self.addCleanup(lambda: (app.dependency_overrides.clear(), app.dependency_overrides.update(previous)))
        app.dependency_overrides[auth] = lambda: None
        # No lifespan: contract checks must not start workers or submit real jobs.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_action_publishes_response_schema(self):
        paths = self.app.openapi()['paths']
        schema = paths['/api/v2/plugin-actions/{action_id}/execute']['post']['responses']['202']['content']['application/json']['schema']
        self.assertEqual(schema['$ref'], '#/components/schemas/PluginActionResponse')

    def test_application_errors_are_mapped_at_http_boundary(self):
        response = self.client.post('/api/v2/plugin-actions/missing.action/execute', json={'inputs': {}})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()['detail'], '插件动作不存在: missing.action')

    def test_obsolete_endpoints_are_not_registered(self):
        paths = self.app.openapi()['paths']
        obsolete = {
            '/api/v2/tts/preset', '/api/v2/tts/describe', '/api/v2/tts/clone',
            '/v1/image/generate', '/v1/video/generate', '/v1/music/generate',
            '/v1/tts/generate', '/v1/jobs/{job_id}/refine', '/v1/agent/translate-h3',
            '/v1/agent/chat', '/v1/agent/collaborations',
        }
        self.assertFalse(obsolete & paths.keys())
        self.assertFalse(any(path.startswith('/v1/agent/') for path in paths))
        for path in obsolete:
            with self.subTest(path=path):
                response = self.client.post(path.replace('{job_id}', 'source'), json={})
                self.assertEqual(response.status_code, 404, response.text)

    def test_speech_action_returns_job_not_session(self):
        inputs = {'text':'hello', 'voice_description':'calm male', 'speed':1.2}
        with patch('backend.interfaces.http.api_v2.execute_action',
                new_callable=AsyncMock, return_value={'action_id':'speech_describe',
                    'status':'queued', 'job_id':'j1', 'capability_id':'tts.describe'}) as execute:
            with patch('backend.interfaces.http.api_v2.ProjectService') as projects:
                projects.return_value.authorize.return_value = {'id': 'p1'}
                response = self.client.post('/api/v2/plugin-actions/speech_describe/execute',
                                            json={'project_id':'p1', 'inputs':inputs})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()['job_id'], 'j1')
            self.assertEqual(response.json()['job_url'], '/api/v2/jobs/j1')
            self.assertNotIn('session_id', response.json())
            self.assertEqual(execute.call_args.args[1:3], ('speech_describe', inputs))
            self.assertEqual(execute.call_args.kwargs['project_id'], 'p1')
            self.assertTrue(callable(execute.call_args.kwargs['invoke_capability']))

    def test_generation_requires_explicit_capability(self):
        from fastapi import HTTPException
        from backend.interfaces.http.v1_generation import validate_generation_request
        with self.assertRaises(HTTPException) as error:
            validate_generation_request('video', {'prompt':'hello', 'mode':'reference'})
        self.assertEqual(error.exception.status_code, 422)



if __name__ == '__main__':
    unittest.main()
