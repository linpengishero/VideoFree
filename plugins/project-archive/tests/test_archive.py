"""Archive contracts exercised against the real document runtime and SQLite."""
import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

from jsonschema import Draft202012Validator
from backend.persistence.database import Database
from backend.modules.projects.service import ProjectService
from backend.modules.shared.plugin_runtime import PluginRuntime, PluginError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archive_test_plugin', ROOT / 'actions.py', submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        db = Database(self.root / 'archive.sqlite')
        db.initialize({})
        self.context = SimpleNamespace(db=db, application_semaphores={}, jobs={}, executing_jobs=set(),
                                       paths=SimpleNamespace(projects=self.root / 'projects', uploads=self.root / 'uploads'))
        self.service = ProjectService(self.context)
        self.project = self.service.create('Archive')['id']
        self.category = self.service.save_category(self.project, 'Episode 1')['id']
        self.runtime = PluginRuntime('project-archive', {}, self.context, self.project, None)

    async def call(self, action, inputs=None, category=None, project=None):
        runtime = PluginRuntime('project-archive', {}, self.context, project or self.project, category)
        return await module.execute({'action': {'id': 'project-archive.' + action}, 'inputs': inputs or {}}, runtime)

    async def save(self, kind, content, revision=0, category=None, **extra):
        return await self.call('save_document', {'document_type': kind, 'content': content, 'expected_revision': revision, **extra}, category)

    async def test_context_scope_and_legacy_project_format(self):
        await self.save('profile', {'project_type': 'series', 'rules': 'Same character'})
        await self.save('script', 'Project script')
        await self.save('script', 'Default category', category='')
        await self.save('episode', {'number': '1'}, category=self.category)
        self.assertEqual((await self.call('get_document', {'document_type': 'script'}))['content'], 'Project script')
        self.assertEqual((await self.call('get_document', {'document_type': 'script'}, ''))['content'], 'Default category')
        context = await self.call('get_context', category=self.category)
        self.assertEqual(context['category_id'], self.category)
        self.assertEqual(len(context['documents']), 3)
        self.assertTrue(any(d['scope'] == 'project' and 'Same character' in d['content'] for d in context['documents']))
        self.assertIn('连续剧', (await self.call('get_document', {'document_type': 'profile'}))['content'])
        self.assertNotIn('episode', [d['document_type'] for d in (await self.call('list_documents'))['items']])
        self.assertEqual((await self.call('get_context', category=''))['category_id'], '')
        with self.assertRaises(PluginError) as caught:
            await self.save('episode', {'number': '1'})
        self.assertEqual(caught.exception.status_code, 422)

    async def test_revision_conflict_history_and_restore(self):
        await self.save('script', 'First', status='final')
        await self.save('script', 'Second', 1)
        versions = await self.call('list_versions', {'document_type': 'script'})
        self.assertEqual([d['revision'] for d in versions['items']], [2, 1])
        self.assertEqual(versions['items'][1]['status'], 'final')
        with self.assertRaises(PluginError) as caught:
            await self.save('script', 'Stale', 1)
        self.assertEqual(caught.exception.status_code, 409)
        restored = await self.call('restore_version', {'document_type': 'script', 'revision': 1, 'expected_revision': 2})
        self.assertEqual(restored['revision'], 3)
        self.assertEqual(restored['content'], 'First')
        self.assertEqual(restored['status'], 'draft')
        original = await self.call('get_version', {'document_type': 'script', 'revision': 1})
        self.assertEqual(original['status'], 'final')
        self.assertEqual(len((await self.call('list_documents'))['items']), 1)

    async def test_two_creators_cannot_overwrite(self):
        results = await asyncio.gather(self.save('script', 'A'), self.save('script', 'B'), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, PluginError) and r.status_code == 409 for r in results), 1)
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)

    async def test_structures_ids_and_shot_context(self):
        board = {'shots': [{'id': 'shot-1', 'visual': 'First'}, {'id': 'shot-2', 'visual': 'Second'}],
                 'groups': [{'id': 'board-1', 'shot_ids': ['shot-1', 'shot-2'], 'kind': 'sequence'}]}
        await self.save('storyboard', board)
        await self.save('prompts', {'items': [
            {'id': 'prompt-1', 'kind': 'image', 'purpose': 'planned', 'target_id': 'shot-1'},
            {'id': 'prompt-2', 'kind': 'video', 'purpose': 'planned', 'target_id': 'shot-2'},
            {'id': 'prompt-3', 'kind': 'image', 'purpose': 'planned', 'target_id': 'board-1'}]})
        context = await self.call('get_context', {'include': ['storyboard', 'prompts'], 'shot_id': 'shot-1'})
        import json
        prompts = json.loads(next(d['content'] for d in context['documents'] if d['document_type'] == 'prompts'))
        self.assertEqual([p['id'] for p in prompts['items']], ['prompt-1', 'prompt-3'])
        broken = deepcopy(board)
        broken['groups'][0]['shot_ids'] = ['missing']
        with self.assertRaises(PluginError):
            await self.save('storyboard', broken, 1)
        broken = deepcopy(board)
        broken['shots'][1]['id'] = 'shot-1'
        with self.assertRaises(PluginError):
            await self.save('storyboard', broken, 1)
        board['shots'].reverse()
        saved = await self.save('storyboard', board, 1)
        self.assertEqual(saved['content']['shots'][0]['id'], 'shot-2')
        self.assertEqual(saved['content']['groups'][0]['shot_ids'], ['shot-1', 'shot-2'])

    async def test_references_survive_finalizing(self):
        job = {'id': 'tts-one', 'kind': 'tts', 'status': 'completed', 'project_id': self.project, 'created_at': 1, 'request': {}}
        self.context.db.insert_job(job)
        await self.save('continuity', {'decisions': 'Chosen voice', 'references': [{'kind': 'job', 'id': 'tts-one', 'role': 'voice'}]})
        final = await self.call('finalize_document', {'document_type': 'continuity', 'expected_revision': 1})
        self.assertEqual(final['references'], ['tts-one'])
        with self.assertRaises(PluginError):
            await self.save('continuity', {'references': [{'kind': 'job', 'id': 'unknown'}]}, 2)
        cleared = await self.save('continuity', {'decisions': 'No longer use this task'}, 2)
        self.assertEqual(cleared['references'], [])
        await self.save('prompts', {'items': [{'id': 'p-1', 'kind': 'image', 'purpose': 'planned',
                                             'parameters': {'kind': 'job', 'job_id': 'provider-option'}}]})

    async def test_context_pagination_and_exact_truncation(self):
        await self.save('script', 'x' * 1000)
        await self.save('story', {'outline': 'Short'})
        result = await self.call('get_context', {'max_chars': 500})
        self.assertTrue(result['truncated'])
        self.assertTrue(result['partial_documents'])
        full = await self.call('get_context', {'max_chars': 5000})
        self.assertFalse(full['truncated'])
        page = await self.call('get_context', {'limit': 1, 'max_chars': 5000})
        self.assertEqual(page['next_offset'], 1)
        self.assertEqual(len((await self.call('get_context', {'offset': 1, 'limit': 1}))['documents']), 1)

    async def test_schema_and_legacy_content(self):
        for kind in module.TYPES:
            if kind == 'episode':
                continue
            schema = await self.call('get_schema', {'document_type': kind})
            Draft202012Validator.check_schema(schema['content_schema'])
            saved = await self.save(kind, 'Legacy notes')
            self.assertIn('Legacy notes', str(saved['content']))

    async def test_scope_delete_and_project_isolation(self):
        await self.save('script', 'Shared project')
        await self.save('script', 'Unit', category=self.category)
        await self.save('script', 'Unit v2', 1, category=self.category)
        other = self.service.create('Other')['id']
        self.assertEqual((await self.call('list_documents', project=other))['items'], [])
        self.service.delete_category(self.project, self.category)
        self.assertEqual(len((await self.call('list_documents'))['items']), 1)
        self.assertFalse(any(doc['category_id'] == self.category for doc in self.runtime.application.documents(self.project)))

    async def test_manuscripts_are_plain_text_and_prior_forms_are_readable(self):
        for kind in ('profile', 'story', 'episode', 'script'):
            category = self.category if kind == 'episode' else None
            schema = await self.call('get_schema', {'document_type': kind}, category)
            self.assertEqual(schema['content_schema']['type'], 'string')
            self.assertEqual(schema['schema_version'], 4)
            text = '第一行\n\n第二行，保留正文。'
            saved = await self.save(kind, text, category=category)
            self.assertEqual(saved['content'], text)
            old = {'text': text, 'scenes': [{'id': 'scene-1', 'dialogue': '你好', 'action': '走进房间'}]}
            converted = await self.save(kind, old, 1, category=category)
            self.assertIn(text, converted['content'])
            self.assertIn('对白：你好', converted['content'])
            self.assertIn('动作：走进房间', converted['content'])
            self.assertNotIn('{', converted['content'])

    async def test_episode_requires_named_category(self):
        for category in (None, ''):
            for action in ('get_document', 'save_document'):
                with self.assertRaises(PluginError) as caught:
                    await self.call(action, {'document_type': 'episode', 'content': 'Episode', 'expected_revision': 0}, category)
                self.assertEqual(caught.exception.status_code, 422)
        saved = await self.save('episode', 'Episode one', category=self.category)
        self.assertEqual(saved['content'], 'Episode one')

    async def test_groups_not_limited_to_four_and_source_script_version_is_preserved(self):
        shots = [{'id': f'shot-{i}', 'script_excerpt': 'Original dialogue', 'script_revision': 3, 'status': 'planned'} for i in range(6)]
        board = {'shots': shots, 'groups': [{'id': 'board-six', 'kind': 'sequence', 'shot_ids': [s['id'] for s in shots]}]}
        saved = await self.save('storyboard', board)
        self.assertEqual(len(saved['content']['groups'][0]['shot_ids']), 6)
        self.assertEqual(saved['content']['shots'][0]['script_revision'], 3)
        broken = deepcopy(board)
        broken['shots'][0]['script_revision'] = -1
        with self.assertRaises(PluginError):
            await self.save('storyboard', broken, 1)

    async def test_shots_can_preserve_dialogue_video_production_links(self):
        shot = {'id': 'shot-1', 'turn_id': 'turn-3', 'scene_id': 'scene-room', 'speaker': 'host-a',
                'listener': 'host-b', 'audio_mode': 'dialogue', 'action_start': '入场',
                'action_process': '走向桌边', 'action_end': '停下并看向对方',
                'storyboard_prompt': '静态构图：人物位于画面左侧', 'required_assets': ['host-a', 'scene-room']}
        saved = await self.save('storyboard', {'shots': [shot]})
        self.assertEqual(saved['content']['shots'][0], shot)

    async def test_selected_results_validate_project_and_hold_references(self):
        job = {'id': 'image-selected', 'kind': 'image', 'status': 'completed', 'project_id': self.project, 'created_at': 1, 'request': {}}
        self.context.db.insert_job(job)
        saved = await self.save('storyboard', {'shots': [{'id': 'shot-1', 'selected_job_id': job['id'], 'status': 'selected'}]})
        self.assertEqual(saved['references'], [job['id']])
        other = self.service.create('Other project')['id']
        self.context.db.insert_job(dict(job, id='image-other', project_id=other))
        with self.assertRaises(PluginError):
            await self.save('storyboard', {'shots': [{'id': 'shot-1', 'selected_job_id': 'image-other'}]}, 1)


if __name__ == '__main__':
    unittest.main()
