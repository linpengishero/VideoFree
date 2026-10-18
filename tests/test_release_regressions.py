"""Release regressions: no GPU, user data or running gateway required."""

import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from backend.interfaces.http.api_v2 import build_router
from backend.interfaces.http.v2_schemas import (
    CreateRequest, CollaborationCreateRequest, CollaborationMessageRequest,
    CollaborationConfirmRequest, RegenerateRequest,
)
from backend.modules.generation.service import submit_idempotent
from backend.modules.projects import ProjectService
from backend.core.schemas import AgentChatRequest, GenerateRequest, TTSRequest
from backend.persistence.database import Database


class ReleaseRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_progress_accepts_plugin_owned_stages(self):
        from backend.modules.collaboration import progress
        import threading
        ctx = SimpleNamespace(state_lock=threading.Lock(), agent_progress={}, db=Mock())
        ctx.db.collaboration.return_value = None
        stages = [{'id': 'custom-stage', 'label': 'Custom plugin stage'}]
        with patch.object(progress, 'context', ctx):
            progress.start('custom-progress', stages)
        stages[0]['label'] = 'Changed by caller'
        self.assertEqual(ctx.agent_progress['custom-progress']['stages'], [
            {'id': 'custom-stage', 'label': 'Custom plugin stage', 'status': 'pending', 'message': ''}])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = Database(self.root / 'test.sqlite')
        self.db.initialize({})
        self.ctx = SimpleNamespace(db=self.db, jobs={}, library_cache={},
            paths=SimpleNamespace(projects=self.root / 'projects'),
            generation_idempotency_lock=asyncio.Lock(), collaboration_submission_lock=asyncio.Lock())
        self.project = ProjectService(self.ctx).create('Project A')['id']

    async def submit(self, request, **kwargs):
        await asyncio.sleep(0.001)
        identifier = f'job-{len(self.db.jobs(limit=None))}'
        self.db.insert_job({'id': identifier, 'kind': 'image', 'status': 'queued',
            'created_at': 1, 'request': {}, 'project_id': request.project_id})
        return {'job_id': identifier, 'kind': 'image', 'status': 'queued'}

    def request(self, **kwargs):
        return CreateRequest(capability_id='example.create', prompt='A scene',
            project_id=self.project, **kwargs)

    async def test_concurrent_generation_retries_submit_once_and_survive_reopen(self):
        results = await asyncio.gather(*(submit_idempotent(self.ctx, self.db,
            self.request(), 'shot-001', self.submit) for _ in range(6)))
        self.assertEqual(len({result['job_id'] for result in results}), 1)
        self.assertEqual(len(self.db.jobs(limit=None)), 1)
        reopened = Database(self.db.path)
        result = await submit_idempotent(self.ctx, reopened, self.request(), 'shot-001', self.submit)
        self.assertTrue(result['reused'])

    async def test_generation_keys_are_project_scoped(self):
        first = await submit_idempotent(self.ctx, self.db, self.request(), 'shot-001', self.submit)
        other = ProjectService(self.ctx).create('Project B')['id']
        request = self.request().model_copy(update={'project_id': other})
        second = await submit_idempotent(self.ctx, self.db, request, 'shot-001', self.submit)
        self.assertEqual(len({first['job_id'], second['job_id']}), 2)

    async def test_changed_payload_conflicts_without_new_generation(self):
        await submit_idempotent(self.ctx, self.db, self.request(), 'shot-001', self.submit)
        with self.assertRaises(ValueError):
            await submit_idempotent(self.ctx, self.db,
                self.request().model_copy(update={'prompt': 'Different scene'}), 'shot-001', self.submit)
        self.assertEqual(len(self.db.jobs(limit=None)), 1)

    async def test_omitted_project_uses_current_project_for_key(self):
        ProjectService(self.ctx).select(self.project)
        request = self.request().model_copy(update={'project_id': None})
        first = await submit_idempotent(self.ctx, self.db, request, 'shot-001', self.submit)
        second = await submit_idempotent(self.ctx, self.db, self.request(), 'shot-001', self.submit)
        self.assertEqual(first['job_id'], second['job_id'])

    def router(self, config=None, submit=None, enqueue=None, hydrate=None):
        return build_router(context=self.ctx, db=self.db, auth=lambda: None,
            workflow_registry=lambda: {'example.create': config or {'executor': 'fake', 'kind': 'image', 'mode': 'create', 'model_family': 'example'}},
            workflows_path=self.root, submit=submit or AsyncMock(), generate_model=GenerateRequest,
            tts_model=TTSRequest, jobs=lambda: {}, public_job=lambda item: item,
            hydrate_job=hydrate or Mock(), upload_cache=self.root,
            upload_handler=AsyncMock(), style_items=Mock(), cancel_handler=AsyncMock(),
            agent_handler=AsyncMock(), agent_model=AgentChatRequest,
            library_handler=AsyncMock(), agent_enqueue_handler=enqueue)

    def collaboration_config(self):
        return {'executor': 'fake', 'kind': 'image', 'mode': 'create', 'model_family': 'example',
            'plugin_id': 'example', 'plugin_version': '1', 'plugin_revision': 'revision-1',
            'processing_modes': [{'id': 'direct', 'name': 'Direct'},
                {'id': 'compile', 'name': 'Compile'}, {'id': 'director', 'name': 'Director'}]}

    async def test_failed_enqueue_can_retry_same_key_without_ghost_queue(self):
        config = self.collaboration_config()
        queued = AsyncMock(side_effect=HTTPException(429, 'Queue full'))
        router = self.router(config, enqueue=queued)
        create = next(r.endpoint for r in router.routes if r.path == '/api/v2/generations')
        request = self.request(prompt_processing='compile')
        with self.assertRaises(HTTPException):
            await create(request, idempotency_key='retry-me')
        failed = self.db.collaborations()[0]
        self.assertEqual(failed['status'], 'failed')
        self.assertTrue(failed['result']['enqueue_failed'])
        queued.side_effect = lambda identifier, body: self.db.update_collaboration(
            identifier, {'status': 'queued', 'result': {}})
        results = await asyncio.gather(*(create(request, idempotency_key='retry-me') for _ in range(3)))
        self.assertEqual(queued.await_count, 2)
        self.assertEqual(len(self.db.collaborations()), 1)
        self.assertEqual(len(self.db.collaboration_messages(failed['id'])), 1)
        self.assertTrue(all(item['id'] == failed['id'] for item in results))
        self.assertEqual(results[0]['status'], 'queued')

    async def test_collaboration_submission_failures_never_leave_queued_rows(self):
        for failure in (HTTPException(422, 'Not configured'), HTTPException(429, 'Queue full'),
                        asyncio.CancelledError(), None):
            enqueue = AsyncMock(side_effect=failure) if failure is not None else None
            router = self.router(self.collaboration_config(), enqueue=enqueue)
            create = next(r.endpoint for r in router.routes
                if r.path == '/api/v2/collaborations' and 'POST' in r.methods)
            with self.assertRaises(asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else HTTPException):
                await create(CollaborationCreateRequest(capability_id='example.create',
                    project_id=self.project, model_id='example', mode_id='create',
                    collaboration_mode='quick', message='A scene'))
            self.assertTrue(all(item['status'] == 'failed' and item['result']['enqueue_failed']
                for item in self.db.collaborations()))

    async def test_quick_collaboration_pins_plugin_and_dispatches_compile(self):
        config = self.collaboration_config()
        queued = AsyncMock(side_effect=lambda identifier, body: self.db.collaboration(identifier))
        router = self.router(config, enqueue=queued)
        create = next(r.endpoint for r in router.routes
            if r.path == '/api/v2/collaborations' and 'POST' in r.methods)
        confirm = next(r.endpoint for r in router.routes if r.path.endswith('/{collaboration_id}/confirm'))
        for mode, expected in [('quick', 'compile'), ('director', 'director')]:
            result = await create(CollaborationCreateRequest(capability_id='example.create',
                project_id=self.project, model_id='example', mode_id='create',
                collaboration_mode=mode, message='A scene'))
            sent = queued.call_args.args[1]
            self.assertEqual(sent.params['processing_mode'], expected)
            self.assertEqual(sent.params['_plugin_revision'], 'revision-1')
            source = self.db.collaboration(result['id'])['request']
            self.assertEqual(source['plugin_revision'], 'revision-1')
        self.db.update_collaboration(result['id'], {'status': 'awaiting_confirmation',
            'revision': 1, 'result': {'optimized_prompt': 'A scene', 'optimized_prompt_zh': 'Scene'}})
        config['plugin_revision'] = 'revision-2'
        with self.assertRaises(HTTPException) as error:
            await confirm(result['id'], CollaborationConfirmRequest(revision=1))
        self.assertEqual(error.exception.status_code, 409)

    async def test_busy_or_cancelled_messages_do_not_pollute_history(self):
        router = self.router(self.collaboration_config())
        send = next(r.endpoint for r in router.routes if r.path.endswith('/{collaboration_id}/messages'))
        for status in ('queued', 'running', 'cancelled', 'submitted'):
            self.db.create_collaboration({'id': status, 'capability_id': 'example.create',
                'model_id': 'example', 'mode_id': 'create', 'status': status,
                'project_id': self.project, 'request': {}})
            with self.assertRaises(HTTPException) as error:
                await send(status, CollaborationMessageRequest(message='Rejected message'))
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(self.db.collaboration_messages(status), [])

    async def test_concurrent_answers_use_real_queue_once(self):
        from backend.interfaces.http import v1_collaboration
        self.ctx.submission_lock = asyncio.Lock()
        self.ctx.agent_queue = asyncio.Queue(maxsize=3)
        self.db.create_collaboration({'id': 'answer-session', 'capability_id': 'example.create',
            'model_id': 'example', 'mode_id': 'create', 'status': 'needs_input',
            'project_id': self.project, 'request': {'kind': 'image', 'capability_id': 'example.create'}})
        router = self.router(self.collaboration_config(), enqueue=v1_collaboration.enqueue_existing_agent_collaboration)
        send = next(r.endpoint for r in router.routes if r.path.endswith('/{collaboration_id}/messages'))
        with patch.object(v1_collaboration, 'context', self.ctx), \
             patch.object(v1_collaboration, 'ai_is_configured', return_value=True), \
             patch.object(v1_collaboration, 'persist_agent_references', side_effect=lambda _, payload: payload):
            results = await asyncio.gather(*(send('answer-session', CollaborationMessageRequest(message='Answer'))
                                            for _ in range(2)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        rejected = next(result for result in results if isinstance(result, HTTPException))
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(self.ctx.agent_queue.qsize(), 1)
        self.assertEqual(len(self.db.collaboration_messages('answer-session')), 1)

    async def test_enqueue_rechecks_busy_session_under_lock(self):
        from backend.interfaces.http import v1_collaboration
        self.ctx.submission_lock = asyncio.Lock()
        self.ctx.agent_queue = asyncio.Queue(maxsize=3)
        self.db.create_collaboration({'id': 'queue-session', 'capability_id': 'example.create',
            'model_id': 'example', 'mode_id': 'create', 'status': 'needs_input',
            'project_id': self.project, 'request': {}})
        with patch.object(v1_collaboration, 'context', self.ctx), \
             patch.object(v1_collaboration, 'ai_is_configured', return_value=True), \
             patch.object(v1_collaboration, 'persist_agent_references', side_effect=lambda _, payload: payload):
            results = await asyncio.gather(*(v1_collaboration.enqueue_existing_agent_collaboration(
                'queue-session', AgentChatRequest(message='Answer', model='example', mode='create'))
                for _ in range(2)), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(self.ctx.agent_queue.qsize(), 1)
        self.assertEqual(self.db.collaboration('queue-session')['status'], 'queued')

    async def test_regeneration_never_guesses_missing_capability(self):
        self.db.insert_job({'id': 'old', 'kind': 'image', 'status': 'completed',
            'created_at': 1, 'request': {}, 'project_id': self.project})
        submit = AsyncMock()
        router = self.router(submit=submit, hydrate=Mock(return_value={'mode': 'create', 'params': {}}))
        regenerate = next(r.endpoint for r in router.routes if r.path.endswith('/{job_id}/regenerate'))
        with self.assertRaises(HTTPException) as error:
            await regenerate('old', RegenerateRequest())
        self.assertEqual(error.exception.status_code, 422)
        submit.assert_not_awaited()

    async def test_startup_recovers_plugin_sessions_and_interrupts_unrecoverable_ones(self):
        from backend import lifecycle
        for identifier, capability, status in (
            ('running', 'example.create', 'running'), ('removed', 'removed.create', 'queued'),
            ('queued-a', 'example.create', 'queued'), ('queued-b', 'example.create', 'queued')):
            self.db.create_collaboration({'id': identifier, 'capability_id': capability,
                'model_id': 'example', 'mode_id': 'create', 'status': status, 'request': {}})
        ctx = SimpleNamespace(db=self.db, paths=SimpleNamespace(plugins=self.root, projects=self.root / 'projects'),
            config=SimpleNamespace(max_agent_queue_size=1, generation_concurrency=0))
        catalog = Mock()
        catalog.start_applications = AsyncMock()
        catalog.capabilities.return_value = {'example.create': self.collaboration_config()}
        settings = Mock()
        settings.read.return_value = {'comfyui_url': 'http://unused:8189'}
        with ExitStack() as stack:
            for name, value in {'context': ctx, 'PluginCatalog': Mock(return_value=catalog),
                'PluginSettings': Mock(),
                'ProjectService': Mock(), 'settings_service': settings, 'comfyui_client': Mock(),
                'clean_upload_cache': Mock(), 'clean_collaborations': Mock(),
                'supervise_generation_workers': AsyncMock(), 'agent_worker': AsyncMock()}.items():
                stack.enter_context(patch.object(lifecycle, name, value))
            try:
                await lifecycle.start()
                self.assertEqual(ctx.agent_queue.qsize(), 1)
                restored = ctx.agent_queue.get_nowait()
                self.assertIn(restored, {'queued-a', 'queued-b'})
                self.assertEqual(self.db.collaboration(restored)['status'], 'queued')
                for identifier in {'running', 'removed', 'queued-a', 'queued-b'} - {restored}:
                    self.assertEqual(self.db.collaboration(identifier)['status'], 'interrupted')
            finally:
                tasks = [*getattr(ctx, 'agent_worker_tasks', []),
                    *([ctx.worker_supervisor_task] if getattr(ctx, 'worker_supervisor_task', None) else [])]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def test_jobs_pagination_includes_entries_older_than_500(self):
        ProjectService(self.ctx).select(self.project)
        with self.db.connect() as connection:
            connection.executemany('INSERT INTO jobs(id,kind,status,request_json,created_at,updated_at,project_id) VALUES(?,?,?,?,?,?,?)',
                [(f'job-{i}', 'image', 'completed', '{}', i, i, self.project) for i in range(505)])
        endpoint = next(r.endpoint for r in self.router().routes if r.path == '/api/v2/jobs')
        result = await endpoint(limit=50, offset=500, kind=None, status=None)
        self.assertEqual(result['total'], 505)
        self.assertEqual(len(result['items']), 5)
        self.assertIsNone(result['next_offset'])

    async def test_declared_plugin_settings_are_validated_and_forwarded(self):
        config = {'executor': 'fake', 'kind': 'image', 'mode': 'create', 'model_family': 'example',
            'ui': {'version': 1, 'fields': [{'bind': 'settings.example_strength',
                'component': 'number', 'label': 'Strength', 'minimum': 0, 'maximum': 1, 'default': 0.7}]}}
        submit = AsyncMock(return_value={'job_id': 'new', 'kind': 'image', 'status': 'queued'})
        create = next(r.endpoint for r in self.router(config, submit).routes if r.path == '/api/v2/generations')
        await create(self.request(), idempotency_key=None)
        self.assertEqual(submit.call_args.args[1].params['example_strength'], 0.7)
        with self.assertRaises(HTTPException) as error:
            await create(self.request(settings={'example_strength': 2}), idempotency_key=None)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(submit.await_count, 1)

    async def test_missing_build_returns_actionable_error_not_old_ui(self):
        from backend.interfaces.http import v1_system
        with patch.object(v1_system, 'DIST', self.root):
            with self.assertRaises(HTTPException) as error:
                await v1_system.index()
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn('npm run build', error.exception.detail)

    async def test_tts_preserves_explicit_capability_and_plugin_settings(self):
        (self.root / 'speech.json').write_text('{}', encoding='utf-8')
        config = {'executor': 'comfyui', 'file': 'speech.json', 'compiler': 'builtin', 'kind': 'tts',
            'mode': 'describe', 'model_family': 'example',
            'parameters': {'emotion': {'type': 'string', 'default': 'calm'}},
            'ui': {'version': 1, 'fields': [{'bind': 'settings.example_strength',
                'component': 'number', 'label': 'Strength', 'default': 0.7}]}}
        submit = AsyncMock(return_value={'job_id': 'new', 'kind': 'tts', 'status': 'queued'})
        create = next(r.endpoint for r in self.router(config, submit).routes if r.path == '/api/v2/generations')
        await create(self.request(settings={'voice_speed': 1.2}, parameters={'emotion': 'happy'}), idempotency_key=None)
        body = submit.call_args.args[1]
        self.assertIsInstance(body, TTSRequest)
        self.assertEqual(body.params['capability_id'], 'example.create')
        self.assertEqual(body.params['example_strength'], 0.7)
        self.assertEqual(body.params['plugin_parameters']['emotion'], 'happy')
        self.assertEqual(body.params['api_settings']['voice_speed'], 1.2)
        self.assertEqual(body.speed, 1.2)

    def test_dimensions_accept_new_plugin_options_and_preserve_roundtrip(self):
        from backend.interfaces.http.v2_capabilities import dimensions, named_dimensions
        for resolution, ratio, kind, expected in (
            ('900P', '32:9', 'image', (900, 253)),
            ('900P', '32:9', 'video', (3200, 900)),
            ('4K', '16:9', 'video', (4096, 2304)),
            ('1.5K', '1:1', 'image', (1536, 1536)),
        ):
            with self.subTest(resolution=resolution, kind=kind):
                size = dimensions(resolution, ratio, kind)
                self.assertEqual(size, expected)
                restored_ratio, restored_resolution = named_dimensions(*size, kind)
                self.assertEqual(dimensions(restored_resolution, restored_ratio, kind), size)
        for resolution, ratio in (('auto', '16:9'), ('0P', '1:1'), ('720P', '0:9'), ('720P', '-1:9')):
            with self.subTest(resolution=resolution, ratio=ratio), self.assertRaises(HTTPException):
                dimensions(resolution, ratio, 'image')

    def test_release_check_detects_missing_assets_and_invalid_plugins(self):
        from backend.bootstrap import check_installation
        dist = self.root / 'static' / 'dist'
        dist.mkdir(parents=True)
        with patch('backend.modules.generation.plugins.PluginCatalog.scan', return_value=([], [])):
            with self.assertRaisesRegex(RuntimeError, 'Frontend build missing'):
                check_installation(self.root)
            (dist / 'index.html').write_text('<script src="/assets/app.js"></script>', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'Frontend asset missing'):
                check_installation(self.root)
            (dist / 'assets').mkdir()
            (dist / 'assets' / 'app.js').write_text('', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'manifest missing'):
                check_installation(self.root)
            (dist / '.vite').mkdir()
            manifest = {'index.html': {'file': 'assets/app.js', 'dynamicImports': ['film.vue']},
                'film.vue': {'file': 'assets/film.js', 'css': ['assets/film.css']}}
            (dist / '.vite' / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'film.js'):
                check_installation(self.root)
            (dist / 'assets' / 'film.js').write_text('', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'film.css'):
                check_installation(self.root)
            (dist / 'assets' / 'film.css').write_text('', encoding='utf-8')
            check_installation(self.root)
            manifest.pop('film.vue')
            (dist / '.vite' / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'chunk missing'):
                check_installation(self.root)
        manifest['index.html'].pop('dynamicImports')
        (dist / '.vite' / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with patch('backend.modules.generation.plugins.PluginCatalog.scan', return_value=([
            {'id':'sample','_plugin_folder':'sample','application':{'entry':'ui/App.vue'}}], [])):
            with self.assertRaisesRegex(RuntimeError, 'Plugin application not built'):
                check_installation(self.root)
        with patch('backend.modules.generation.plugins.PluginCatalog.scan', return_value=([], [{'plugin': 'broken'}])):
            with self.assertRaisesRegex(RuntimeError, 'Invalid plugins'):
                check_installation(self.root)


if __name__ == '__main__':
    unittest.main()
