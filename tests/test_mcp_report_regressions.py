"""Regressions from the MCP full-tool report; no live generation required."""
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from backend.integrations.comfyui.client import ComfyUIClient
from backend.integrations.comfyui.workflow_loader import validate_choices
from backend.modules.collaboration import modes, service
from backend.modules.collaboration.analysis import parse_agent_result
from backend.modules.generation.actions import prepare_action
from backend.modules.generation.plugins import PluginCatalog
from backend.modules.projects.assets import PublicAssetService
from backend.modules.projects.service import ProjectService
from backend.core.schemas import AgentChatRequest
from backend.persistence.database import Database

ROOT = Path(__file__).resolve().parents[1]
READY = {'status': 'ready', 'optimized_prompt': 'A red ball on a table.',
         'optimized_prompt_zh': '桌上的红球。'}
QUESTION = {'status': 'needs_input', 'questions': [
    {'text': 'Which color?', 'options': ['Red', 'Blue']}]}


class CollaborationReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_director_initializes_real_progress_and_returns_session(self):
        state = SimpleNamespace(agent_sessions={}, agent_progress={}, state_lock=threading.RLock(),
                                db=SimpleNamespace(collaboration=lambda key: None))
        with patch.object(modes, 'context', state), \
             patch('backend.modules.collaboration.progress.context', state), \
             patch.object(modes, 'agent_skill_prompt', return_value='contract'), \
             patch.object(service, 'initial_agent_message', return_value='request'), \
             patch.object(service, 'call_agent_model', return_value=json.dumps(READY)):
            result = await modes.single(AgentChatRequest(message='A red ball', model='qwen', mode='create'))
        self.assertEqual(result['status'], 'ready')
        self.assertIn(result['session_id'], state.agent_sessions)
        self.assertEqual(state.agent_progress[result['progress_id']]['stages'][0]['id'], 'optimize')

    async def test_tts_actions_inject_declared_capabilities(self):
        context = SimpleNamespace(paths=SimpleNamespace(plugins=ROOT / 'plugins'))
        catalog = PluginCatalog(context.paths.plugins)
        with patch('backend.modules.shared.plugin_runtime.PluginRuntime.reference', return_value='upload:' + 'a' * 32):
            for action, inputs, capability in (
                ('speech_preset', {'text': 'Hello', 'preset_id': 'warm_male'}, 'tts.cosyvoice3.preset'),
                ('speech_clone', {'text': 'Hello', 'reference_upload_id': 'a' * 32}, 'tts.cosyvoice3.clone'),
            ):
                kind, request = await prepare_action(catalog, action, inputs, context)
                self.assertEqual(kind, 'tts')
                self.assertEqual(request.params['capability_id'], capability)

    def test_questionless_model_response_is_repaired(self):
        with patch.object(service, 'call_agent_model', return_value=json.dumps(QUESTION)) as model:
            result = service.repair_agent_result([], parse_agent_result('not JSON'), 'qwen', 'create')
        self.assertEqual(result['status'], 'needs_input')
        self.assertTrue(result['questions'])
        model.assert_called_once()
        with patch.object(service, 'call_agent_model', return_value='invalid again'):
            with self.assertRaises(ValueError):
                service.repair_agent_result([], parse_agent_result('invalid'), 'qwen', 'create')

    def test_valid_questions_do_not_trigger_prompt_repair(self):
        with patch.object(service, 'call_agent_model') as model:
            result = service.repair_agent_result([], parse_agent_result(json.dumps(QUESTION)), 'qwen', 'create')
        self.assertTrue(result['questions'])
        model.assert_not_called()

    def test_qwen_confirmation_preserves_selected_dimensions(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        handler = catalog.confirmation(catalog.capabilities()['image.qwen.text_to_image'])
        self.assertEqual(
            handler({'settings': {'ratio': '1:1', 'resolution': '768P'}}, {}, None),
            {'settings': {'ratio': '1:1', 'resolution': '768P'}},
        )
        self.assertEqual(
            handler({'settings': {'ratio': '1:1', 'resolution': '720P'}}, {}, None),
            {'settings': {'ratio': '1:1', 'resolution': '768P'}},
        )

    def test_krea_confirmation_applies_revised_dimensions(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        handler = catalog.confirmation(catalog.capabilities()['image.krea2.text_to_image'])
        self.assertEqual(
            handler({'settings': {'ratio': '16:9', 'resolution': '720P'}},
                    {'generation_payload': {'aspect_ratio': '1:1', 'resolution': '1K'}}, None),
            {'settings': {'ratio': '1:1', 'resolution': '1K'}},
        )


class CatalogAndValidationTests(unittest.TestCase):
    def test_postprocessors_declare_human_readable_task_identity(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        expected = {
            'image.split': ('图片分割工作流', '四宫格分割'),
            'image.split_6': ('图片分割工作流', '六宫格分割'),
            'image.krea2_upscale': ('Krea2', '高清增强'),
            'video.lms_enhance': ('MiniMax H3', 'LMS 清晰度增强'),
            'video.interpolate': ('RIFE', '视频补帧'),
            'video.upscale': ('LTX 2.5', '视频放大'),
        }
        capabilities = catalog.capabilities()
        for capability_id, identity in expected.items():
            with self.subTest(capability_id=capability_id):
                item = capabilities[capability_id]
                self.assertEqual((item['model_name'], item['mode_name']), identity)

    def test_fixed_postprocessors_do_not_advertise_ignored_dimensions(self):
        catalog = PluginCatalog(ROOT / 'plugins')
        for action_id in ('interpolate', 'upscale', 'krea2_upscale', 'lms_enhance'):
            with self.subTest(action_id=action_id):
                properties = catalog.actions()[action_id]['input_schema']['properties']
                self.assertTrue({'width', 'height', 'upscaler'}.isdisjoint(properties))

    def test_uploaded_video_choices_are_not_validated_against_stale_comfy_cache(self):
        workflow = {'24': {'class_type': 'VHS_LoadVideo', 'inputs': {'video': 'new-job.mp4'}}}
        info = {'VHS_LoadVideo': {'input': {'required': {'video': [['old-job.mp4']]}}}}
        validate_choices(workflow, info)

    def test_qwen_only_advertises_implemented_voice_design(self):
        plugin = json.loads((ROOT / 'plugins/qwen-tts/plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(set(plugin['capabilities']), {'tts.describe'})

    def test_missing_and_empty_styles_include_diagnostics(self):
        from backend.modules.presets.style_library import catalog
        with tempfile.TemporaryDirectory() as directory:
            for path in (Path(directory), Path(directory) / 'missing'):
                items, errors = catalog(path)
                self.assertEqual(items, [])
                self.assertTrue(errors)

    def test_preset_validation_rejects_before_submission(self):
        from backend.interfaces.http.v1_generation import validate_generation_request
        from backend.modules.generation.service import validate_voice_preset
        config = {'kind': 'tts', 'mode': 'preset', 'plugin_id': 'cosyvoice3', 'references': {}}
        context = SimpleNamespace(paths=SimpleNamespace(plugins=ROOT / 'plugins'))
        with patch('backend.modules.generation.service.context', context), \
             patch('backend.modules.generation.service.registry_service') as registry:
            registry.return_value.capability.return_value = config
            with self.assertRaisesRegex(ValueError, '声音预设不存在'):
                validate_generation_request('tts', {'mode': 'preset', 'character': 'invalid',
                    'params': {'capability_id': 'tts.cosyvoice3.preset'}})
            self.assertEqual(validate_voice_preset(config, 'warm_male')['plugin_id'], 'cosyvoice3')
            with self.assertRaisesRegex(ValueError, '不属于当前插件'):
                validate_voice_preset({**config, 'plugin_id': 'other'}, 'warm_male')

    def test_custom_asset_kind_updates_and_project_filter_precedes_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / 'test.db')
            db.initialize({})
            context = SimpleNamespace(db=db, paths=SimpleNamespace(projects=root / 'projects'))
            project = ProjectService(context).create('Test project')['id']
            assets = PublicAssetService(context)
            asset = assets.save(project, 'Test', 'custom', '')
            assets.save(project, 'Test', 'custom-updated', '', asset['id'])
            self.assertEqual(assets.get(project, asset['id'])['kind'], 'custom-updated')
            for identifier, owner in (('own', project), ('foreign', 'other')):
                db.create_collaboration({'id': identifier, 'project_id': owner, 'status': 'failed',
                    'capability_id': 'removed', 'model_id': 'removed', 'mode_id': 'create', 'request': {}})
            self.assertEqual([row['id'] for row in db.collaborations(limit=1, project_id=project)], ['own'])

    def test_comfy_upload_converts_pcm8_and_preserves_pcm16(self):
        for width, frames in ((1, bytes([0, 128, 255, 64])), (2, b'\x00\x80\x00\x00\x00\x7f\x00\x40')):
            source = io.BytesIO()
            with wave.open(source, 'wb') as audio:
                audio.setnchannels(2)
                audio.setsampwidth(width)
                audio.setframerate(16000)
                audio.writeframes(frames)
            original = source.getvalue()
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b'{"name":"sample.wav"}'
            with patch('urllib.request.urlopen', return_value=response) as upload:
                ComfyUIClient('http://unused').upload_input(original, 'audio/wav', 'sample.wav')
            body = upload.call_args.args[0].data.split(b'\r\n\r\n', 1)[1].rsplit(b'\r\n------MediaGatewayBoundary', 1)[0]
            with wave.open(io.BytesIO(body), 'rb') as converted:
                self.assertEqual((converted.getsampwidth(), converted.getnchannels(), converted.getframerate()), (2, 2, 16000))
                if width == 1:
                    self.assertEqual(converted.readframes(2), b'\x00\x80\x00\x00\x00\x7f\x00\xc0')
                else:
                    self.assertEqual(body, original)
