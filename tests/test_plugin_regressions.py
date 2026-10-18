import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.modules.generation.plugins import PluginCatalog, validate_action_schema
from backend.modules.generation.actions import action_availability, action_matches_source


class PluginRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'sample'
        self.folder.mkdir()
        self.manifest = {'schema_version':1, 'id':'sample', 'version':'1.0',
            'categories':[], 'capabilities':{},
            'settings':{'fields':[{'key':'VALUE','label':'Value','runtime_key':'value','default':'configured'}]},
            'resource_lifecycle':{'recover':'handler.py:recover'},
            'actions':[{'id':'sample.inspect','name':'Inspect','scope':'resource',
                'source_types':['video'], 'input_schema':{'type':'object'},
                'handler':'handler.py:inspect','availability_handler':'handler.py:available'}]}
        (self.folder/'INSTALL.md').write_text('# Install\n\nNo external dependencies.\n', encoding='utf-8')
        (self.folder/'plugin.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        (self.folder/'handler.py').write_text(
            'import time\ntime.sleep(.05)\n'
            'def inspect(request, runtime): return {}\n'
            'def available(request, runtime): return {"available":runtime.configuration["value"]=="configured"}\n'
            'def recover(event, runtime): runtime._context.received=runtime.configuration["value"]\n', encoding='utf-8')
        self.context = SimpleNamespace(paths=SimpleNamespace(plugins=self.root),
            plugin_catalogs={}, plugin_catalog_lock=threading.RLock())

    def test_parallel_first_import_returns_complete_handler(self):
        catalog = PluginCatalog(self.root)
        action = catalog.actions()['sample.inspect']
        barrier = threading.Barrier(8)
        def load(_):
            barrier.wait(timeout=5)
            return catalog.action_handler(action)
        with ThreadPoolExecutor(max_workers=8) as executor:
            handlers = list(executor.map(load, range(8)))
        self.assertTrue(all(handler is handlers[0] for handler in handlers))

    def test_failed_import_does_not_leave_partial_module(self):
        marker = self.folder / 'first-import'
        (self.folder/'handler.py').write_text(
            'from pathlib import Path\n'
            f'marker=Path({str(marker)!r})\n'
            'if not marker.exists():\n'
            '    marker.touch()\n'
            '    raise RuntimeError("first import failed")\n'
            'def inspect(request, runtime): return {"ready": True}\n', encoding='utf-8')
        catalog = PluginCatalog(self.root)
        action = catalog.actions()['sample.inspect']
        with self.assertRaisesRegex(RuntimeError, 'first import failed'):
            catalog.action_handler(action)
        self.assertEqual(catalog.action_handler(action)({}, None), {'ready': True})

    def test_registry_snapshot_is_shared_and_cannot_be_mutated_by_caller(self):
        catalog = PluginCatalog(self.root, self.context)
        catalog.scan()[0][0]['name'] = 'tampered'
        with patch.object(PluginCatalog, '_scan', side_effect=AssertionError('rescanned')):
            snapshot = PluginCatalog(self.root, self.context).scan()
            self.assertNotIn('name', snapshot[0][0])
        action = catalog.actions()['sample.inspect']
        with (self.folder/'handler.py').open('a', encoding='utf-8') as handle:
            handle.write('\n# changed revision\n')
        with self.assertRaisesRegex(ValueError, '重启'):
            catalog.action_handler(action)

    def test_configuration_reaches_availability_and_lifecycle(self):
        catalog = PluginCatalog(self.root, self.context)
        action = catalog.actions()['sample.inspect']
        source = {'kind':'video', 'status':'completed'}
        self.assertTrue(action_availability(catalog, action, source, self.context)['available'])
        catalog.resource_event('recover', self.context)
        self.assertEqual(self.context.received, 'configured')

    def test_configuration_reaches_application_startup(self):
        self.manifest['application'] = {'name':'Sample','entry':'ui/page.vue','startup':'startup.py:start'}
        (self.folder/'ui').mkdir()
        (self.folder/'ui/page.vue').write_text('<template />', encoding='utf-8')
        (self.folder/'startup.py').write_text(
            'async def start(runtime): runtime._context.received=runtime.configuration["value"]', encoding='utf-8')
        (self.folder/'plugin.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        asyncio.run(PluginCatalog(self.root, self.context).start_applications(self.context))
        self.assertEqual(self.context.received, 'configured')

    def test_local_schema_references_are_validated_without_remote_lookup(self):
        for reference in ('#/$defs/missing', '#missing', 'https://example.com/schema'):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                validate_action_schema({'type':'object','$ref':reference})
        validate_action_schema({'type':'object','$defs':{'item':{'type':'object'}},'$ref':'#/$defs/item'})
        validate_action_schema({'type':'object','properties':{'next':{'$ref':'#'}}})
        broken = {'scope':'resource','source_types':['video'],
                  'source_schema':{'type':'object','$ref':'#/$defs/missing'}}
        self.assertFalse(action_matches_source(broken, {'kind':'video','status':'completed'}))

    def test_final_outputs_are_strict_and_all_are_saved(self):
        from backend.modules.generation import service
        from backend.integrations.comfyui.compiler import history_media
        outputs = {'2':{'audio':[{'filename':'preview.wav'}]},
                   '9':{'audio':[{'filename':'final.wav'}, {'filename':'second.wav'}]}}
        with patch.object(service, 'ARTIFACTS', self.root), \
             patch.object(service, 'download_output', side_effect=lambda value:value['filename'].encode()):
            paths = service.collect_outputs('tts-test', outputs, {'output_nodes':['9']})
            self.assertEqual([path.read_bytes() for path in paths], [b'final.wav',b'second.wav'])
            with self.assertRaises(RuntimeError):
                service.collect_outputs('tts-test', outputs, {'output_nodes':['missing']})
        self.assertEqual(list(history_media(outputs, ['missing'])), [])

    def test_tts_waits_for_completion_and_collects_declared_outputs(self):
        from backend.modules.generation import service
        from backend.core.schemas import TTSRequest
        config = {'plugin_id':'sample','plugin_folder':'sample', 'plugin_revision':'test',
                  'file':'workflow.json','output_nodes':['9']}
        (self.root/'workflow.json').write_text('{}', encoding='utf-8')
        preview = {'outputs':{'2':{'audio':[{'filename':'preview.wav'}]}},'status':{'completed':False}}
        final = {'outputs':{**preview['outputs'],'9':{'audio':[{'filename':'one.wav'},{'filename':'two.wav'}]}},
                 'status':{'completed':True}}
        request = TTSRequest(text='hello',mode='describe',instruction='calm voice',
                             params={'capability_id':'sample.speak'})
        with patch.object(service, 'registry_service') as registry, \
             patch.object(service, 'WORKFLOWS', self.root), \
             patch.object(service, 'context', SimpleNamespace(jobs={'j':{'comfy_prompt_id':'p'}})), \
             patch.object(service, 'workflow_for', return_value={}), \
             patch.object(service, 'PluginCatalog') as catalog, \
             patch.object(service, 'VoicePresets') as presets, \
             patch.object(service, 'plugin_runtime', return_value=None), \
             patch.object(service, 'comfy', side_effect=[{'p':preview},{'p':final}]), \
             patch.object(service.time, 'sleep') as sleep, \
             patch.object(service, 'collect_outputs', return_value=[Path('one.wav'),Path('two.wav')]) as collect:
            registry.return_value.capability.return_value = config
            catalog.return_value.speech.return_value = None
            catalog.return_value.assert_current = Mock()
            presets.return_value.get.return_value = {}
            self.assertEqual(len(service.run_tts('j',request)),2)
            sleep.assert_called_once()
            collect.assert_called_once_with('j',final['outputs'],config)

    def test_tts_explicit_capability_can_use_native_executor(self):
        from backend.modules.generation import service
        from backend.core.schemas import TTSRequest
        config = {'kind':'tts','mode':'describe','executor':'cloud', 'plugin_id':'sample'}
        request = TTSRequest(text='hello',mode='describe',instruction='calm',
            params={'capability_id':'sample.speak','plugin_parameters':{'emotion':'warm'}})
        with patch.object(service, 'registry_service') as registry, \
             patch.object(service, 'PluginCatalog') as catalog, \
             patch.object(service, 'VoicePresets') as presets, \
             patch.object(service, 'run_native', return_value=[Path('audio.wav')]) as native:
            registry.return_value.capability.return_value = config
            catalog.return_value.assert_current = Mock()
            presets.return_value.get.return_value = {}
            catalog.return_value.speech.return_value = None
            self.assertEqual(service.run_tts('j',request), [Path('audio.wav')])
            forwarded = native.call_args.args[2]
            self.assertEqual(forwarded.params['capability_id'], 'sample.speak')
            self.assertEqual(forwarded.params['plugin_parameters'], {'emotion':'warm'})
            self.assertEqual(forwarded.params['instruction'], 'calm')

    def test_tts_hydration_distinguishes_generic_and_speech_requests(self):
        from backend.modules.generation.task_store import TaskStore
        store = TaskStore(self.root/'tasks', self.root/'uploads')
        manifest = self.root/'manifest.json'
        manifest.write_text(json.dumps({'inputs':[{'type':'audio','index':1,'path':'input/audio/001.wav'}]}), encoding='utf-8')
        for request in ({'prompt':'hello'}, {'text':'hello'}):
            restored = store.hydrate({'id':'j','kind':'tts','request':request,'manifest_path':str(manifest)})
            if 'text' in request:
                self.assertEqual(restored['reference_audio'], 'task:input/audio/001.wav')
            else:
                self.assertEqual(restored['params']['audios'], ['task:input/audio/001.wav'])
                self.assertNotIn('reference_audio', restored)

    def test_cloud_tts_recovery_resolves_execution_plane_without_snapshot(self):
        from backend.modules.generation import service
        with patch.object(service, 'tts_config', return_value={'execution_plane':'cloud'}):
            self.assertEqual(service.job_execution_plane({'kind':'tts', 'request':{
                'text':'hello','params':{'capability_id':'sample.speak'}}}), 'cloud')
