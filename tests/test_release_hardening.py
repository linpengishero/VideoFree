"""Gateway auth and executor lifetime regressions using isolated runtime data."""

import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from backend.bootstrap import create_context
from backend.interfaces.http import dependencies, mcp, v1_generation, v1_system
from backend.modules.generation import service
from backend.modules.projects import ProjectService
from backend.modules.settings import SettingsService


class ReleaseHardeningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with patch.dict(os.environ, {}, clear=True):
            self.ctx = create_context(Path(directory.name))
        self.ctx.db.initialize({})
        self.settings = SettingsService(self.ctx, Mock())
        self.settings.effective_output_directory = Mock(return_value=self.ctx.paths.data / 'output')
        self.project = ProjectService(self.ctx).create('Test')['id']

    def job(self, status='running', **extra):
        job = {'id': 'job-a', 'status': status, 'kind': 'image', 'created_at': 1,
               'request': {}, 'project_id': self.project, **extra}
        self.ctx.jobs[job['id']] = job
        self.ctx.db.insert_job(job)
        return job

    def test_token_defaults_empty_and_stored_value_overrides_environment(self):
        self.assertEqual(self.settings.read()['gateway_token'], '')
        self.settings.apply({'gateway_token': 'shared-token'})
        self.assertEqual(SettingsService.access_token(self.ctx), 'shared-token')
        self.settings.apply({'gateway_token': ''})
        self.assertEqual(SettingsService.access_token(self.ctx), '')

    async def test_browser_cookie_media_rotation_and_shared_mcp_token(self):
        app = FastAPI()
        app.include_router(v1_system.router)
        app.include_router(mcp.build_router())

        @app.get('/media', dependencies=[Depends(dependencies.auth)])
        async def media():
            return {'ok': True}

        self.ctx.db.save_settings({'gateway_token': 'first-token'})
        with ExitStack() as stack:
            for module in (dependencies, mcp, v1_system):
                stack.enter_context(patch.object(module, 'context', self.ctx))
            stack.enter_context(patch.object(v1_system, 'settings_service', self.settings))
            stack.enter_context(patch.object(v1_system, 'SETTINGS_FILE', self.ctx.paths.legacy_settings))
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                self.assertEqual((await client.get('/media')).status_code, 401)
                for issued, signature in [(str(int(time.time())), '\u00e9'),
                                          (str(int(time.time()) - dependencies.SESSION_AGE - 1), ''),
                                          (str(int(time.time()) + 60), '')]:
                    signature = signature or dependencies.session_signature('first-token', issued)
                    invalid = {'Cookie': (dependencies.SESSION_COOKIE + '=' + issued + '.' + signature).encode('latin-1')}
                    self.assertEqual((await client.get('/media', headers=invalid)).status_code, 401)
                login = await client.post('/v1/auth/session', headers={'X-API-Token': 'first-token'})
                self.assertEqual(login.status_code, 200)
                self.assertIn('HttpOnly', login.headers['set-cookie'])
                self.assertIn('SameSite=strict', login.headers['set-cookie'])
                old_cookie = client.cookies.get(dependencies.SESSION_COOKIE)
                self.assertNotIn('first-token', old_cookie)
                self.assertEqual((await client.get('/media')).status_code, 200)
                self.assertEqual((await client.get('/mcp')).status_code, 200)
                denied = await client.put('/v1/settings', json={'gateway_token': 'bad'}, headers={'Origin': 'http://evil'})
                self.assertEqual(denied.status_code, 403)
                saved = await client.put('/v1/settings', json={'gateway_token': 'second-token'})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()['gateway_token'], '********')
                self.assertEqual((await client.get('/media')).status_code, 200)
                headers = {'Cookie': dependencies.SESSION_COOKIE + '=' + old_cookie}
                self.assertEqual((await client.get('/media', headers=headers)).status_code, 401)
                self.assertEqual((await client.get('/mcp', headers={'X-API-Token': 'first-token'})).status_code, 401)
                self.assertEqual((await client.get('/mcp', headers={'X-API-Token': 'second-token'})).status_code, 200)
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.read.return_value = b'{}'
                with patch.object(mcp.urllib.request, 'urlopen', return_value=response) as urlopen:
                    mcp._local_api_request('GET', '/v1/projects')
                    self.assertEqual(urlopen.call_args.args[0].get_header('X-api-token'), 'second-token')
                saved = await client.put('/v1/settings', json={'gateway_token': ''})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual((await client.get('/media', headers={'Cookie': ''})).status_code, 200)

    async def test_cancelled_executing_job_blocks_task_category_project_deletion(self):
        category = ProjectService(self.ctx).save_category(self.project, 'Category')['id']
        job = self.job(category_id=category)
        entered, finish = threading.Event(), threading.Event()

        def executing(_):
            entered.set()
            finish.wait(timeout=5)

        with patch.object(service, 'context', self.ctx), patch.object(service, '_process', side_effect=executing), \
             patch.object(service, 'update_task_manifest'), patch.object(v1_generation, 'context', self.ctx):
            task = asyncio.create_task(asyncio.to_thread(service.process, job['id']))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                service.cancel_generation(job['id'])
                with self.assertRaises(HTTPException) as error:
                    await v1_generation.delete_job(job['id'])
                self.assertEqual(error.exception.status_code, 409)
                with self.assertRaises(RuntimeError):
                    ProjectService(self.ctx).delete_category(self.project, category)
                with self.assertRaises(RuntimeError):
                    ProjectService(self.ctx).delete(self.project)
            finally:
                finish.set()
                await task
            self.assertFalse(self.ctx.executing_jobs)
            with patch.object(v1_generation, 'delete_job_files'):
                self.assertTrue((await v1_generation.delete_job(job['id']))['deleted'])
            service.process(job['id'])  # A stale cancelled queue entry is harmless after deletion.

    def test_cancellation_never_globally_interrupts_comfy(self):
        job = self.job(comfy_prompt_id='queued-behind-another-client')
        with patch.object(service, 'context', self.ctx), patch.object(service, 'update_task_manifest'), \
             patch.object(service, 'comfy') as comfy:
            service.cancel_generation(job['id'])
            self.assertEqual(comfy.call_args.args[0], '/queue')
            self.assertEqual(json.loads(comfy.call_args.args[2]), {'delete': [job['comfy_prompt_id']]})
            comfy.assert_called_once()
            with self.assertRaises(service.JobCancelled):
                service.set_status(job['id'], 'running')

    def test_finalizing_job_cannot_be_cancelled(self):
        job = self.job(_publishing=True)
        with patch.object(service, 'context', self.ctx):
            with self.assertRaises(RuntimeError):
                service.cancel_generation(job['id'])
        self.assertEqual(job['status'], 'running')

    async def test_cancellation_cannot_be_overwritten_by_inflight_status_persistence(self):
        job = self.job(status='queued')
        entered, finish = threading.Event(), threading.Event()
        update = self.ctx.db.update_job

        def persist(job_id, values):
            if values['status'] == 'running':
                entered.set()
                finish.wait(timeout=5)
            return update(job_id, values)

        with patch.object(service, 'context', self.ctx), patch.object(service, 'update_task_manifest'), \
             patch.object(self.ctx.db, 'update_job', side_effect=persist):
            running = asyncio.create_task(asyncio.to_thread(service.set_status, job['id'], 'running'))
            cancelling = None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                cancelling = asyncio.create_task(asyncio.to_thread(service.cancel_generation, job['id']))
                await asyncio.sleep(0.05)
                self.assertFalse(cancelling.done())
            finally:
                finish.set()
                await running
                if cancelling is not None:
                    await cancelling
        self.assertEqual(self.ctx.db.job(job['id'])['status'], 'cancelled')
        self.assertEqual(job['status'], 'cancelled')

    def test_upload_cache_protects_sessions_beyond_500(self):
        from backend import lifecycle
        uploads = self.ctx.paths.uploads
        protected = uploads / 'old-reference.png'
        expired = uploads / 'unused.png'
        for path in (protected, expired):
            path.write_bytes(b'image')
            os.utime(path, (1, 1))
        with self.ctx.db.connect() as connection:
            connection.executemany("INSERT INTO collaborations(id,status,request_json,created_at,updated_at,capability_id,model_id,mode_id) VALUES(?,?,?,?,?,'example','example','direct')",
                [(str(i), 'needs_input', json.dumps({'inputs': [{'upload_id': 'old-reference'}]}) if i == 0 else '{}', i, i)
                 for i in range(501)])
        with patch.object(lifecycle, 'context', self.ctx):
            lifecycle.clean_upload_cache()
        self.assertTrue(protected.exists())
        self.assertFalse(expired.exists())
