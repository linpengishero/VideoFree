import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from backend.persistence.database import Database
from backend.modules.generation.task_store import TaskStore
import hashlib
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import BaseModel

from backend.interfaces.http.api_v2 import build_router
from backend.interfaces.http.v2_schemas import CreateRequest
from backend.interfaces.http.v2_schemas import CollaborationConfirmRequest, CollaborationMessageRequest
from backend.core.schemas import AgentChatRequest, GenerateRequest, TTSRequest


class CollaborationIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / "test.sqlite")
        self.db.initialize({})

    def create(self, identifier, key="request-1", fingerprint="same"):
        return self.db.create_collaboration({"id": identifier, "capability_id": "video.reference",
            "model_id": "minimax-h3", "mode_id": "reference", "request": {}, "status": "queued"},
            idempotency_key=key, fingerprint=fingerprint)

    def test_retry_survives_database_reopen(self):
        first = self.create("c1")
        self.db = Database(self.db.path)
        self.assertEqual(self.create("c2")["id"], first["id"])
        self.assertEqual(len(self.db.collaborations()), 1)

    def test_conflict_and_project_independent_keys(self):
        self.create("c1")
        with self.assertRaises(ValueError):
            self.create("c2", fingerprint="different")
        self.assertEqual(self.create("c3", key="request-2")["id"], "c3")

    def test_concurrent_retries_claim_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.create, [f"c{i}" for i in range(8)]))
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.assertEqual(len(self.db.collaborations()), 1)

    def test_deleted_session_releases_claim(self):
        self.create("c1")
        with self.db.connect() as db:
            db.execute("DELETE FROM collaborations WHERE id='c1'")
        self.assertEqual(self.create("c2")["id"], "c2")

    def test_project_id_is_normalized_from_nested_legacy_request(self):
        item = self.db.create_collaboration({
            "id": "legacy-project-session",
            "capability_id": "video.reference",
            "model_id": "minimax-h3",
            "mode_id": "reference",
            "request": {"params": {"_source_request": {"project_id": "project-a"}}},
            "status": "awaiting_confirmation",
        })
        self.assertEqual(item["project_id"], "project-a")
        with self.db.connect() as db:
            db.execute("UPDATE collaborations SET project_id=NULL WHERE id=?", (item["id"],))
        self.db.initialize({})
        self.assertEqual(self.db.collaboration(item["id"])["project_id"], "project-a")

    def test_task_store_hashes_actual_saved_reference(self):
        root = Path(self.temp.name)
        uploads = root / "uploads"
        uploads.mkdir()
        upload_id = "a" * 32
        source = uploads / f"{upload_id}.png"
        source.write_bytes(b"actual uploaded image")
        store = TaskStore(root / "tasks", uploads)
        task = store.create({"id": "image-test", "kind": "image", "status": "queued", "created_at": 1,
                             "request": {"references": [f"upload:{upload_id}"], "prompt": "image"}})
        receipt = json.loads((task / "manifest.json").read_text(encoding="utf-8"))["inputs"][0]
        self.assertEqual(receipt["upload_id"], upload_id)
        self.assertEqual(receipt["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        source.write_bytes(b"changed later")
        self.assertEqual(receipt["sha256"], hashlib.sha256((task / receipt["path"]).read_bytes()).hexdigest())


class CompileSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_releases_waiting_sessions_and_preserves_submitted_jobs(self):
        from backend.interfaces.http.v1_collaboration import cancel_existing_agent_collaboration
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / 'test.sqlite')
            db.initialize({})
            db.create_project({'id': 'project-a', 'name': 'Project A', 'output_subdir': 'project-a'})
            context = type('Context', (), {'db': db})()
            with patch('backend.interfaces.http.v1_collaboration.context.db', db), \
                 patch('backend.interfaces.http.v1_collaboration.close_agent_connection') as close:
                for status in ('queued', 'running', 'needs_input', 'awaiting_confirmation', 'submitted'):
                    db.create_collaboration({'id': status, 'capability_id': 'video.reference',
                                             'model_id': 'minimax-h3', 'mode_id': 'reference',
                                             'request': {}, 'status': status,
                                             'project_id': 'project-a'})
                    result = await cancel_existing_agent_collaboration(status)
                    expected = 'submitted' if status == 'submitted' else 'cancelled'
                    self.assertEqual(result['status'], expected)
                    self.assertEqual(db.collaboration(status)['status'], expected)
                self.assertEqual(close.call_count, 4)

    async def test_regeneration_retains_declared_parameters_and_original_scope(self):
        from backend.interfaces.http.v2_schemas import RegenerateRequest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / 'test.sqlite')
            db.initialize({})
            db.create_project({'id': 'project-a', 'name': 'Project A', 'output_subdir': 'project-a'})
            context = type('Context', (), {
                'db': db,
            })()
            config = {'executor': 'fake', 'kind': 'image', 'mode': 'create', 'model_family': 'example',
                      'parameters': {'strength': {'type': 'number', 'minimum': 0, 'maximum': 1}}}
            parent = {'id': 'original', 'kind': 'image', 'project_id': 'project-a', 'category_id': 'episode-a'}
            original = {'prompt': 'Original', 'params': {'capability_id': 'example.create',
                        'api_settings': {'ratio': '16:9', 'resolution': '1K'}, 'plugin_parameters': {'strength': 0.7}}}
            submit = AsyncMock(return_value={'job_id': 'new', 'kind': 'image', 'status': 'queued'})
            router = build_router(
                context=context, db=db, auth=lambda: None, workflow_registry=lambda: {'example.create': config},
                workflows_path=root, submit=submit, generate_model=GenerateRequest,
                tts_model=BaseModel, jobs=lambda: {'original': parent}, public_job=Mock(), hydrate_job=Mock(return_value=original),
                upload_cache=root, upload_handler=AsyncMock(),
                style_items=Mock(), cancel_handler=AsyncMock(),
                agent_handler=AsyncMock(), agent_model=AgentChatRequest, library_handler=AsyncMock())
            regenerate = next(r.endpoint for r in router.routes if r.path == '/api/v2/jobs/{job_id}/regenerate')
            for parameters, expected in ((None, 0.7), ({'strength': 0}, 0)):
                result = await regenerate('original', RegenerateRequest(prompt='Edited', inputs=[], parameters=parameters))
                self.assertEqual(result['job_id'], 'new')
                sent = submit.call_args.args[1].params
                self.assertEqual(sent['plugin_parameters']['strength'], expected)
                self.assertEqual(sent['_project_id'], 'project-a')
                self.assertEqual(sent['_category_id'], 'episode-a')
                self.assertEqual(sent['parent_job_id'], 'original')

    async def test_tts_regeneration_handles_legacy_null_duration(self):
        from backend.interfaces.http.v2_schemas import RegenerateRequest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / 'test.sqlite')
            db.initialize({})
            db.create_project({'id': 'project-a', 'name': 'Project A', 'output_subdir': 'project-a'})
            context = type('Context', (), {'db': db})()
            config = {'executor': 'fake', 'kind': 'tts', 'mode': 'preset', 'model_family': 'cosyvoice3',
                      'compiler': 'builtin', 'references': {'audio': {'min': 0, 'max': 0}},
                      'ui': {'version': 1, 'fields': [
                          {'bind': 'prompt', 'component': 'textarea', 'label': 'Text', 'required': True},
                          {'bind': 'settings.voice_id', 'component': 'text', 'label': 'Voice', 'required': True},
                      ]}}
            parent = {'id': 'original', 'kind': 'tts', 'project_id': 'project-a',
                      'category_id': '', 'duration_seconds': None}
            original = {'text': 'Hello', 'character': 'warm_male', 'speed': 1.0,
                        'params': {'capability_id': 'tts.cosyvoice3.preset'}}
            submit = AsyncMock(return_value={'job_id': 'new', 'kind': 'tts', 'status': 'queued'})
            router = build_router(
                context=context, db=db, auth=lambda: None, workflow_registry=lambda: {'tts.cosyvoice3.preset': config},
                workflows_path=root, submit=submit, generate_model=GenerateRequest,
                tts_model=TTSRequest, jobs=lambda: {'original': parent}, public_job=Mock(),
                hydrate_job=Mock(return_value=original), upload_cache=root,
                upload_handler=AsyncMock(), style_items=Mock(), cancel_handler=AsyncMock(),
                agent_handler=AsyncMock(), agent_model=AgentChatRequest,
                library_handler=AsyncMock())
            regenerate = next(r.endpoint for r in router.routes if r.path == '/api/v2/jobs/{job_id}/regenerate')
            result = await regenerate('original', RegenerateRequest(inputs=[]))
            self.assertEqual(result['job_id'], 'new')
            body = submit.call_args.args[1]
            self.assertEqual(body.character, 'warm_male')
            self.assertEqual(body.params['api_settings']['duration'], 5)

    async def test_storyboard_single_prompt_and_explicit_shots_share_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / 'test.sqlite')
            db.initialize({})
            db.create_project({'id': 'project-a', 'name': 'Project A', 'output_subdir': 'project-a'})
            config = {'executor': 'fake', 'kind': 'image', 'mode': 'storyboard_4',
                      'model_family': 'krea2', 'shot_nodes': ['20', '21', '22', '23'],
                      'references': {'image': {'min': 0, 'max': 0}}}
            submit = AsyncMock(return_value={'job_id': 'job-test', 'kind': 'image', 'status': 'queued'})
            router = build_router(
                context=SimpleNamespace(db=db, collaboration_submission_lock=asyncio.Lock(),
                                        generation_idempotency_lock=asyncio.Lock()),
                db=db, auth=lambda: None, workflow_registry=lambda: {'image.krea2.storyboard_4': config},
                workflows_path=root, submit=submit, generate_model=GenerateRequest,
                tts_model=BaseModel, jobs=lambda: {}, public_job=Mock(), hydrate_job=Mock(),
                upload_cache=root, upload_handler=AsyncMock(),
                style_items=Mock(), cancel_handler=AsyncMock(),
                agent_handler=AsyncMock(), agent_model=AgentChatRequest, library_handler=AsyncMock(),
            )
            create = next(r.endpoint for r in router.routes if r.path == '/api/v2/generations' and 'POST' in r.methods)
            for shots in ([], ['enter', 'walk', 'sit', 'sleep']):
                request = CreateRequest(capability_id='image.krea2.storyboard_4', prompt='A person enters and rests.',
                                        project_id='project-a', settings={'shots': shots})
                result = await create(request, idempotency_key=None)
                self.assertEqual(result['job_id'], 'job-test')
                self.assertEqual(submit.call_args.args[1].params['shots'], shots)
            before = submit.await_count
            request.settings.shots = ['only one']
            with self.assertRaises(HTTPException) as raised:
                await create(request, idempotency_key=None)
            self.assertEqual(raised.exception.status_code, 422)
            self.assertEqual(submit.await_count, before)

    async def test_compile_retry_enqueues_once_and_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / "test.sqlite")
            db.initialize({})

            db.create_project({"id": "project-a", "name": "Project A", "output_subdir": "project-a"})
            db.create_project({"id": "other-project", "name": "Other Project", "output_subdir": "other-project"})
            async def enqueue(identifier, request):
                item = db.collaboration(identifier)
                source = item["request"].get("params", {}).get("_source_request", item["request"])
                payload = request.model_dump()
                payload.setdefault("params", {})["_source_request"] = source
                return db.update_collaboration(identifier, {
                    "status": "queued", "request": payload,
                })

            queued = AsyncMock(side_effect=enqueue)
            submit = AsyncMock(return_value={"job_id": "job-test", "kind": "video", "status": "queued"})
            router = build_router(
                context=SimpleNamespace(db=db, collaboration_submission_lock=asyncio.Lock(),
                                        generation_idempotency_lock=asyncio.Lock()), db=db, auth=lambda: None,
                workflow_registry=lambda: {"video.reference": {"executor": "fake", "kind": "video", "mode": "reference", "model_family": "minimax", "processing_modes": [{"id": "direct", "name": "Direct"}, {"id": "compile", "name": "Compile"}]}},
                workflows_path=root, submit=submit, generate_model=GenerateRequest,
                tts_model=BaseModel, jobs=lambda: {'original': {'id': 'original', 'project_id': 'project-a', 'category_id': ''}}, public_job=Mock(), hydrate_job=Mock(),
                upload_cache=root, upload_handler=AsyncMock(),
                style_items=Mock(), cancel_handler=AsyncMock(),
                agent_handler=AsyncMock(), agent_model=AgentChatRequest,
                library_handler=AsyncMock(), agent_enqueue_handler=queued,
            )
            create = next(r.endpoint for r in router.routes if r.path == "/api/v2/generations" and "POST" in r.methods)
            request = CreateRequest(capability_id="video.reference", prompt="Dialogue scene",
                                    prompt_processing="compile", project_id="project-a", parent_job_id="original")
            first = await create(request, idempotency_key="compile-shot-1")
            retry = await create(request, idempotency_key="compile-shot-1")
            self.assertEqual(first["id"], retry["id"])
            self.assertTrue(retry["reused"])
            self.assertEqual(first["collaboration_mode"], "quick")
            queued.assert_awaited_once()
            self.assertEqual(len(db.collaborations()), 1)
            self.assertEqual(len(db.collaboration_messages(first["id"])), 1)
            listing = next(r.endpoint for r in router.routes if r.path == '/api/v2/collaborations' and 'GET' in r.methods)
            self.assertEqual([item['id'] for item in (await listing('project-a'))['items']], [first['id']])
            self.assertEqual((await listing('other-project'))['items'], [])
            with self.assertRaises(HTTPException) as changed_project:
                await create(request.model_copy(update={'project_id': 'other-project'}), idempotency_key=None)
            self.assertEqual(changed_project.exception.status_code, 422)
            with self.assertRaises(HTTPException) as raised:
                await create(request.model_copy(update={"prompt": "Changed scene"}), idempotency_key="compile-shot-1")
            self.assertEqual(raised.exception.status_code, 409)
            queued.assert_awaited_once()

            db.update_collaboration(first["id"], {"status": "needs_input"})
            send_message = next(r.endpoint for r in router.routes if r.path == "/api/v2/collaborations/{collaboration_id}/messages")
            resumed = await send_message(first["id"], CollaborationMessageRequest(message="Audio 1 is the main character's voice"))
            self.assertEqual(resumed["status"], "queued")
            self.assertIn("Audio 1 is the main character's voice", queued.call_args.args[1].message)
            self.assertEqual(db.collaboration(first["id"])["project_id"], "project-a")

            db.update_collaboration(first["id"], {
                "status": "awaiting_confirmation", "revision": 1,
                "result": {"optimized_prompt": "A dialogue scene", "optimized_prompt_zh": "对白场景"},
            })
            confirm = next(r.endpoint for r in router.routes if r.path == "/api/v2/collaborations/{collaboration_id}/confirm")
            result = await confirm(first["id"], CollaborationConfirmRequest(revision=1))
            self.assertEqual(result["job_id"], "job-test")
            self.assertEqual(submit.call_args.args[1].params["_project_id"], "project-a")
            self.assertEqual(submit.call_args.args[1].params['parent_job_id'], 'original')
            with self.assertRaises(HTTPException) as stale:
                await confirm(first['id'], CollaborationConfirmRequest(revision=99))
            self.assertEqual(stale.exception.status_code, 409)

            db.create_collaboration({'id': 'missing-plugin', 'capability_id': 'removed.capability',
                'model_id': 'removed', 'mode_id': 'create', 'request': {},
                'status': 'failed', 'project_id': 'project-a'})
            listed = (await listing('project-a', active=False))['items']
            self.assertIn('missing-plugin', [item['id'] for item in listed])
            invalid = request.model_copy(update={'prompt_processing': 'nonexistent_mode'})
            with self.assertRaises(HTTPException) as unsupported:
                await create(invalid, idempotency_key=None)
            self.assertEqual(unsupported.exception.status_code, 422)
            self.assertIn('prompt_processing', unsupported.exception.detail)
