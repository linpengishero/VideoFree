import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from backend.persistence.database import Database
from backend.modules.projects.service import ProjectService
from backend.modules.shared.application_runtime import ApplicationRuntime
from backend.modules.generation.plugins import PluginCatalog

CATALOG = PluginCatalog(Path(__file__).resolve().parents[1] / 'plugins')
ACTION = CATALOG.actions()['film.save']
CompositionService = CATALOG._load_handler(ACTION, 'service.py:CompositionService')
FilmWrite = CATALOG._load_handler(ACTION, 'schemas.py:FilmWrite')
ComfyWhisper = CATALOG._load_handler(ACTION, 'asr.py:ComfyWhisper')
film_render = __import__('sys').modules[CompositionService.__module__].render


class FilmCompositionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = Database(self.root / 'test.sqlite')
        self.db.initialize({})
        self.context = SimpleNamespace(db=self.db, jobs={}, library_cache={}, application_tasks={},
            application_semaphores={}, paths=SimpleNamespace(
                root=Path(__file__).resolve().parents[1], projects=self.root / 'projects'))
        self.projects = ProjectService(self.context)
        self.project = self.projects.create('Film project')['id']
        self.other = self.projects.create('Other project')['id']
        self.runtime = ApplicationRuntime(self.context, 'film-studio')
        self.service = CompositionService(self.runtime)
        self.job = self.add_job('video-one')

    def add_job(self, job_id, project=None, kind='video'):
        project = project or self.project
        directory = self.projects.ensure_directory(self.db.project(project))
        path = directory / ('videos' if kind == 'video' else 'audio') / f'{job_id}.mp4'
        path.write_bytes(b'fixture')
        job = {'id': job_id, 'kind': kind, 'status': 'completed', 'created_at': 1,
               'request': {}, 'project_id': project}
        self.db.insert_job(job)
        artifacts = [{'name': path.name, 'project_path': path.relative_to(self.context.paths.projects).as_posix()}]
        self.db.update_job(job_id, {'artifacts_json': json.dumps(artifacts)})
        self.context.jobs[job_id] = self.db.job(job_id)
        return self.db.job(job_id)

    def body(self, job_id='video-one'):
        return {'name': 'Episode one', 'clips': [{'job_id': job_id, 'artifact_index': 0, 'in': 0, 'out': 0.4, 'original': False}],
                'bgm_job_id': None, 'volume': 18, 'width': 1280, 'height': 720, 'fps': 24, 'fit': 'contain'}

    def test_explicit_selection_persisted_and_not_inherited(self):
        self.assertEqual(self.service.selected(self.project), [])
        self.service.save(self.project, self.body())
        self.assertEqual(self.service.selected(self.project)[0]['id'], 'video-one')
        self.assertIn('video-one', Database(self.db.path).plugin_job_marks('film-studio'))
        self.add_job('video-two')
        self.assertNotIn('video-two', self.runtime.selected())
        self.service.select('video-one', False)
        self.assertEqual(self.service.selected(self.project), [])

    def test_cross_project_and_path_escape_rejected(self):
        self.service.select('video-one', True)
        with self.assertRaises(ValueError):
            self.service.save(self.other, self.body())
        self.db.update_job('video-one', {'artifacts_json': '[{"project_path":"../secret.mp4"}]'})
        with self.assertRaises(ValueError):
            self.service.source(self.project, 'video-one')

    def test_add_clip_targets_film_and_is_idempotent(self):
        first = self.service.save(self.project, {**self.body(), 'clips': []})
        second = self.service.save(self.project, {**self.body(), 'clips': [], 'name': 'Other episode'})
        clip = self.body()['clips'][0]
        result = self.service.add_clip(self.project, second['id'], clip)
        self.assertEqual(result['clips'][0]['job_id'], clip['job_id'])
        self.assertEqual(result['clips'][0]['out'], clip['out'])
        self.assertEqual(self.service.get(self.project, first['id'])['clips'], [])
        self.assertIn('video-one', self.runtime.selected())
        self.assertEqual(len(self.service.add_clip(self.project, second['id'], clip)['clips']), 1)
        self.assertEqual(result['width'], second['width'])

    def test_partial_save_validates_against_stored_canvas_and_auto_selects_overlays(self):
        film = self.service.save(self.project, self.body())
        self.add_job('video-two')
        with self.assertRaises(ValueError):
            self.service.save(self.project, {
                'name': 'Bad overlay',
                'overlay_clips': [{'job_id': 'video-two', 'out': 0.2, 'start': 0,
                                   'rect': {'x': 900, 'y': 0, 'w': 500, 'h': 100}}],
            }, film['id'])
        self.assertNotIn('video-two', self.runtime.selected())
        updated = self.service.save(self.project, {
            'name': 'Good overlay',
            'overlay_clips': [{'job_id': 'video-two', 'out': 0.2, 'start': 0,
                               'rect': {'x': 900, 'y': 0, 'w': 300, 'h': 100}}],
        }, film['id'])
        self.assertEqual((updated['width'], updated['height']), (1280, 720))
        self.assertIn('video-two', self.runtime.selected())

    def test_add_clip_rejection_does_not_select_source(self):
        foreign = self.service.save(self.other, {**self.body(), 'clips': []})
        clip = self.body()['clips'][0]
        with self.assertRaises(ValueError):
            self.service.add_clip(self.other, foreign['id'], clip)
        own = self.service.save(self.project, {**self.body(), 'clips': []})
        with self.assertRaises(ValueError):
            self.service.add_clip(self.project, own['id'], {**clip, 'in': 1})
        own['render']['status'] = 'running'
        self.service.persist(own)
        with self.assertRaises(RuntimeError):
            self.service.add_clip(self.project, own['id'], clip)
        self.assertNotIn('video-one', self.runtime.selected())

    def test_progress_and_real_render_authority(self):
        film = self.service.save(self.project, {**self.body(), 'clips': []})
        self.service.progress(self.project, film['id'], 'writing', 'completed', 'Script approved')
        self.assertEqual(self.service.get(self.project, film['id'])['stages']['writing']['status'], 'completed')
        for stage in ('composition', 'acceptance'):
            with self.assertRaises(ValueError):
                self.service.progress(self.project, film['id'], stage, 'completed', '')
        with self.assertRaises(ValueError):
            self.service.get(self.other, film['id'])

    def test_deletion_and_recovery(self):
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body())
        film['render']['status'] = 'running'
        self.service.persist(film)
        with self.assertRaises(RuntimeError):
            self.service.select('video-one', False)
        with self.assertRaises(RuntimeError):
            self.projects.check_application_references(self.project, {'video-one'})
        with self.assertRaises(RuntimeError):
            self.projects.delete(self.project)
        self.service.recover()
        self.assertEqual(self.service.get(self.project, film['id'])['render']['status'], 'failed')
        self.db.delete_job('video-one')
        self.assertEqual(self.service.get(self.project, film['id'])['clips'], [])
        self.db.delete_project(self.project)
        self.assertEqual(self.db.plugin_documents('film-studio', self.project), [])

    def test_missing_ffmpeg_does_not_queue(self):
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body())
        with patch.object(__import__('sys').modules[CompositionService.__module__].shutil, 'which', return_value=None):
            with self.assertRaises(ValueError):
                asyncio.run(self.service.submit(self.project, film['id']))
        self.assertEqual(self.context.application_tasks, {})
        self.assertEqual(self.service.get(self.project, film['id'])['render']['status'], 'draft')

    def test_http_plan_validation(self):
        from pydantic import ValidationError
        self.assertEqual(FilmWrite(**self.body()).model_dump(by_alias=True)['clips'][0]['in'], 0)
        for body in ({**self.body(), 'name': '   '},
                     {**self.body(), 'clips': [{**self.body()['clips'][0], 'in': 1, 'out': 0.4}]}):
            with self.assertRaises(ValidationError):
                FilmWrite(**body)
        for body in ({**self.body(), 'fps': 120},
                     {**self.body(), 'clips': [{**self.body()['clips'][0], 'out': float('nan')}]}):
            with self.assertRaises(ValidationError):
                FilmWrite(**body)

    def test_transition_duration_controls_timeline_bounds(self):
        plan = self.body()
        plan['clips'] = [
            {**plan['clips'][0], 'out': 10, 'transition': {'type': 'fade', 'duration': 3}},
            {**plan['clips'][0], 'out': 10},
        ]
        with self.assertRaisesRegex(ValueError, '时间范围之外'):
            FilmWrite(**{**plan, 'overlay_clips': [{**plan['clips'][0], 'start': 18,
                'rect': {'x': 0, 'y': 0, 'w': 100, 'h': 100}}]})
        with self.assertRaisesRegex(ValueError, '不能使用黑场'):
            FilmWrite(**{**self.body(), 'audio_clips': [{'kind': 'blank', 'out': 0.2, 'start': 0}]})

    def test_preview_is_an_edit_lock_and_new_revision_invalidates_old_preview(self):
        film = self.service.save(self.project, self.body())
        film['preview'] = {'id': 'oldpreview', 'status': 'queued', 'progress': 0}
        self.service.persist(film)
        with self.assertRaisesRegex(RuntimeError, '进行中'):
            self.service.save(self.project, {'name': 'blocked'}, film['id'])
        with self.assertRaisesRegex(RuntimeError, '进行中'):
            self.service.delete(self.project, film['id'])
        film['preview']['status'] = 'completed'
        self.service.persist(film)
        old_preview = self.runtime.directory(self.project) / 'films' / film['id'] / 'oldpreview'
        old_preview.mkdir(parents=True)
        changed = self.service.save(self.project, {'name': 'changed'}, film['id'],
                                    expected_revision=film['revision'])
        self.assertNotIn('preview', changed)
        self.assertFalse(old_preview.exists())
        with self.assertRaisesRegex(RuntimeError, '刷新'):
            self.service.save(self.project, {'name': 'stale'}, film['id'],
                              expected_revision=film['revision'])

    def test_imported_asset_name_and_delete_lifecycle(self):
        uploads = self.root / 'uploads'
        uploads.mkdir()
        self.context.paths.uploads = uploads
        upload = uploads / ('a' * 32 + '.png')
        upload.write_bytes(b'png')
        item = self.service.import_asset(self.project, 'a' * 32, 'poster.png')
        self.assertEqual(item['name'], 'poster.png')
        self.assertTrue(item['managed'])
        film = self.service.save(self.project, {**self.body(), 'clips': [
            {'library_path': item['path'], 'out': 1, 'original': False}]})
        with self.assertRaisesRegex(RuntimeError, '正在被'):
            self.service.delete_asset(self.project, item['path'])
        self.service.save(self.project, {'clips': []}, film['id'])
        self.assertTrue(self.service.delete_asset(self.project, item['path'])['deleted'])
        self.assertFalse((self.context.paths.projects / item['path']).exists())

    def test_preview_overlay_coordinates_are_scaled(self):
        command = film_render._overlay_command(Path('ffmpeg'), Path('base.mp4'), [{
            'source': 'overlay.mp4', 'in': 0, 'out': 1, 'start': 0,
            'rect': {'x': 1500, 'y': 700, 'w': 400, 'h': 300, 'opacity': 100},
        }], {'quality': 'preview', 'width': 1920, 'height': 1080, 'fps': 30}, Path('out.mp4'))
        graph = command[command.index('-filter_complex') + 1]
        self.assertIn('scale=178:132', graph)
        self.assertIn('overlay=x=666:y=311', graph)

    def test_cancel_stops_the_managed_render_task(self):
        film = self.service.save(self.project, self.body())

        async def slow_compose(plan, report, log):
            await asyncio.sleep(60)

        async def run():
            with patch.object(self.service, 'preflight', new=AsyncMock()), \
                    patch.object(film_render, 'compose', side_effect=slow_compose):
                await self.service.submit(self.project, film['id'])
                task = next(iter(self.context.application_tasks.values()))
                await asyncio.sleep(0)
                self.service.cancel(self.project, film['id'])
                await task
                await asyncio.sleep(0)
        asyncio.run(run())
        self.assertEqual(self.service.get(self.project, film['id'])['render']['status'], 'cancelled')
        self.assertFalse(self.context.application_tasks)

    def test_whisper_workflow_has_output_and_reads_alignment(self):
        source = self.root / 'speech.wav'
        source.write_bytes(b'wave fixture')

        class Runtime:
            workflow = None

            def comfyui_upload(self, body, media_type, filename):
                return filename

            def comfyui_request(self, path, method='GET', body=None):
                if path == '/prompt':
                    self.workflow = json.loads(body)['prompt']
                    return {'prompt_id': 'prompt-one'}
                return {'prompt-one': {'status': {'completed': True}, 'outputs': {
                    '3': {'text': [json.dumps([{'value': '你好', 'start': 0.1, 'end': 0.8}])]}
                }}}

        runtime = Runtime()
        with patch(f'{ComfyWhisper.__module__}.asyncio.sleep', new=AsyncMock()):
            segments = asyncio.run(ComfyWhisper(runtime).transcribe(source))
        self.assertEqual(segments, [{'text': '你好', 'start': 0.1, 'end': 0.8}])
        self.assertEqual(set(runtime.workflow['1']['inputs']), {'audio'})
        self.assertEqual(runtime.workflow['3']['class_type'], 'Display Any (rgthree)')
        self.assertEqual(runtime.workflow['3']['inputs']['source'], ['2', 1])

    def test_transcription_does_not_overwrite_a_newer_edit(self):
        film = self.service.save(self.project, self.body())
        service = CompositionService(self.runtime, object())

        async def edit_during_asr(*args, **kwargs):
            service.save(self.project, {'name': 'Edited while recognizing'}, film['id'])
            return [{'text': '字幕', 'start': 0, 'end': 0.2}]

        with patch.object(film_render, 'dialogue_audio', new=AsyncMock(return_value=1.0)), \
                patch.object(ComfyWhisper, 'transcribe', side_effect=edit_during_asr):
            with self.assertRaisesRegex(RuntimeError, '重新识别'):
                asyncio.run(service.transcribe(self.project, film['id']))
        current = service.get(self.project, film['id'])
        self.assertEqual(current['name'], 'Edited while recognizing')
        self.assertEqual(current['captions'], [])

    def test_transcription_replaces_the_whole_caption_track(self):
        film = self.service.save(self.project, {**self.body(), 'captions': [
            {'text': '旧字幕', 'start': 0, 'end': 0.2},
        ]})
        service = CompositionService(self.runtime, object())
        recognized = [
            {'text': '第一句', 'start': 0.05, 'end': 0.3},
            {'text': '越界会被裁掉', 'start': 0.35, 'end': 9},
        ]
        with patch.object(film_render, 'dialogue_audio', new=AsyncMock(return_value=0.4)) as mix, \
                patch.object(ComfyWhisper, 'transcribe', new=AsyncMock(return_value=recognized)) as whisper:
            updated = asyncio.run(service.transcribe(self.project, film['id']))
        mix.assert_awaited_once()
        whisper.assert_awaited_once()
        self.assertEqual(updated['captions'], [
            {'text': '第一句', 'start': 0.05, 'end': 0.3},
            {'text': '越界会被裁掉', 'start': 0.35, 'end': 0.4},
        ])
        self.assertEqual(updated['revision'], film['revision'] + 1)
        self.assertFalse(list((self.runtime.directory(self.project) / 'films' / film['id']).glob('.asr-*.wav')))

    def test_positioned_text_is_validated_inside_canvas_and_timeline(self):
        valid = FilmWrite(**{**self.body(), 'texts': [
            {'text': '标题', 'start': 0, 'end': 0.4, 'x': 640, 'y': 360,
             'font_size': 64, 'color': '#F0E0D0'},
        ]})
        self.assertEqual(valid.texts[0].text, '标题')
        for text in (
            {'text': '越界', 'start': 0, 'end': 0.4, 'x': 1281, 'y': 360},
            {'text': '超时', 'start': 0, 'end': 0.5, 'x': 640, 'y': 360},
        ):
            with self.subTest(text=text['text']), self.assertRaises(ValueError):
                FilmWrite(**{**self.body(), 'texts': [text]})

    def test_legacy_migration_and_namespace_isolation(self):
        film = self.service.save(self.project, {**self.body(), 'clips': []})
        self.db.delete_plugin_document('film-studio', self.project, film['id'])
        with self.db.connect() as db:
            db.execute('CREATE TABLE films (id TEXT, project_id TEXT, document_json TEXT, updated_at REAL)')
            db.execute('INSERT INTO films VALUES (?, ?, ?, ?)', (film['id'], self.project, json.dumps(film), 1))
            db.execute('ALTER TABLE jobs ADD COLUMN film_selected INTEGER DEFAULT 0')
            db.execute('UPDATE jobs SET film_selected=1 WHERE id=?', ('video-one',))
        self.db.initialize({})
        self.db.initialize({})
        self.assertEqual(self.service.get(self.project, film['id'])['name'], film['name'])
        self.assertIn('video-one', self.db.plugin_job_marks('film-studio'))
        self.assertIn('film-studio', self.db.job('video-one')['application_marks'])
        self.assertIn('film-studio', self.db.jobs(project_id=self.project)[0]['application_marks'])
        self.assertFalse(ApplicationRuntime(self.context, 'other-plugin').documents(self.project))
        self.assertFalse(ApplicationRuntime(self.context, 'other-plugin').selected())
        with self.db.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='films'").fetchone())
        film['render']['status'] = 'running'
        self.service.persist(film)
        self.db.reset_application_activity()
        self.db.check_plugin_references(self.project)

    def test_generic_actions_use_explicit_project(self):
        from backend.modules.generation.actions import execute_action, discover_actions
        from backend.core.errors import GatewayError
        self.context.paths.plugins = CATALOG.directory
        async def run():
            async def unused_submit(*args):
                self.fail('Application actions must not submit ComfyUI jobs')
            async def call(action, inputs, project=self.project):
                return await execute_action(CATALOG, action, inputs, self.context, unused_submit, project_id=project)
            created = await call('film.save', {'plan': {'name': 'API film'}})
            film = created['result']
            self.assertEqual(film['project_id'], self.project)
            await call('film.add-clip', {'film_id': film['id'], 'clip': self.body()['clips'][0]})
            updated = await call('film.progress', {'film_id': film['id'], 'progress': {'stage': 'writing', 'status': 'completed'}})
            self.assertEqual(updated['result']['stages']['writing']['status'], 'completed')
            with self.assertRaises(GatewayError) as raised:
                await call('film.get', {'film_id': film['id']}, self.other)
            self.assertEqual(raised.exception.status_code, 422)
            with self.assertRaises(GatewayError):
                await call('film.select-source', {'job_id': 'video-one', 'selected': True}, self.other)
            visible = {a['id'] for a in discover_actions(CATALOG, automation_only=True)}
            self.assertIn('film.render', visible)
            self.assertIn('film.validate', visible)
            self.assertNotIn('film.delete', visible)
            self.assertNotIn('film.select-source', visible)
            self.assertNotIn('film.proxies', visible)
        asyncio.run(run())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
    def test_real_render_with_bundled_openmontage(self):
        source = self.context.paths.projects / self.job['artifacts'][0]['project_path']
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=24:d=0.6',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-shortest', str(source)], check=True, capture_output=True)
        self.service.select('video-one', True)
        film = self.service.save(self.project, self.body())
        async def render():
            await self.service.submit(self.project, film['id'])
            await next(iter(self.context.application_tasks.values()))
        asyncio.run(render())
        completed = self.service.get(self.project, film['id'])
        self.assertEqual(completed['render']['status'], 'completed', completed['render'].get('error'))
        final = next(self.context.paths.projects.rglob('final.mp4'))
        metadata = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(final)]))
        video = next(s for s in metadata['streams'] if s['codec_type']=='video')
        self.assertEqual((video['width'],video['height'],video['r_frame_rate']), (1280,720,'24/1'))
        self.assertEqual(len(completed['renders']), 1)
        self.assertEqual(completed['stages']['acceptance']['status'], 'pending')
        self.assertFalse(self.context.application_tasks)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
    def test_repeat_source_mute_is_per_clip_and_bgm_can_mix(self):
        source = self.context.paths.projects / self.job['artifacts'][0]['project_path']
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=24:d=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-shortest', str(source)], check=True, capture_output=True)
        self.service.select('video-one', True)
        body = self.body()
        body['clips'] = [{**body['clips'][0], 'out': 1, 'original': value} for value in (False, True)]
        film = self.service.save(self.project, body)
        async def render():
            await self.service.submit(self.project, film['id'])
            await next(iter(self.context.application_tasks.values()))
        asyncio.run(render())
        completed = self.service.get(self.project, film['id'])
        self.assertEqual(completed['render']['status'], 'completed', completed['render'].get('error'))
        final = next(self.context.paths.projects.rglob('final.mp4'))
        def amplitude(start):
            import array
            raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(final),
                '-t', '0.3', '-f', 's16le', '-ac', '1', '-ar', '8000', '-'])
            return max(abs(v) for v in array.array('h', raw))
        self.assertLess(amplitude(0.2), 10)
        self.assertGreater(amplitude(1.2), 100)
        audio = source.with_suffix('.wav')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'sine=frequency=220:duration=0.3', str(audio)], check=True, capture_output=True)
        self.add_job('bgm', kind='music')
        self.db.update_job('bgm', {'artifacts_json': json.dumps([{'project_path': audio.relative_to(self.context.paths.projects).as_posix()}])})
        body['bgm_job_id'] = 'bgm'
        self.service.save(self.project, body, film['id'])
        asyncio.run(render())
        completed = self.service.get(self.project, film['id'])
        self.assertEqual(completed['render']['status'], 'completed', completed['render'].get('error'))
        self.assertEqual(len(completed['renders']), 2)


if __name__ == '__main__':
    unittest.main()
