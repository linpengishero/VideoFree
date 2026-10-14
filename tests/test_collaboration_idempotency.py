import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.persistence.database import Database
from backend.modules.generation.task_store import TaskStore
import hashlib
import json
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from pydantic import BaseModel

from backend.interfaces.http.api_v2 import build_router
from backend.interfaces.http.v2_schemas import CreateRequest


class CollaborationIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / "test.sqlite")
        self.db.initialize({})

    def create(self, identifier, key="workspace-a:request-1", fingerprint="same"):
        return self.db.create_collaboration({"id": identifier, "capability_id": "video.reference",
            "model_id": "minimax-h3", "mode_id": "reference", "request": {}, "status": "queued"},
            idempotency_key=key, fingerprint=fingerprint)

    def test_retry_survives_database_reopen(self):
        first = self.create("c1")
        self.db = Database(self.db.path)
        self.assertEqual(self.create("c2")["id"], first["id"])
        self.assertEqual(len(self.db.collaborations()), 1)

    def test_conflict_and_workspace_isolation(self):
        self.create("c1")
        with self.assertRaises(ValueError):
            self.create("c2", fingerprint="different")
        self.assertEqual(self.create("c3", key="workspace-b:request-1")["id"], "c3")

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
    async def test_compile_retry_enqueues_once_and_rejects_changed_payload(self):
        class AgentRequest(BaseModel):
            client_request_id: str = ""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / "test.sqlite")
            db.initialize({})

            async def enqueue(identifier, request):
                return db.collaboration(identifier)

            queued = AsyncMock(side_effect=enqueue)
            router = build_router(
                db=db, auth=lambda: None,
                workflow_registry=lambda: {"video.reference": {"executor": "fake", "kind": "video", "mode": "reference"}},
                workflows_path=root, submit=AsyncMock(), generate_model=BaseModel,
                tts_model=BaseModel, jobs=lambda: {}, public_job=Mock(), hydrate_job=Mock(),
                artifacts_path=root, upload_cache=root, upload_handler=AsyncMock(),
                style_items=Mock(), cancel_handler=AsyncMock(), delete_handler=AsyncMock(),
                voice_sample_handler=AsyncMock(), agent_handler=AsyncMock(), agent_model=AgentRequest,
                library_handler=AsyncMock(), agent_enqueue_handler=queued,
            )
            create = next(r.endpoint for r in router.routes if r.path == "/api/v2/generations" and "POST" in r.methods)
            request = CreateRequest(capability_id="video.reference", prompt="Dialogue scene",
                                    prompt_processing="compile", project_id="project-a")
            first = await create(request, idempotency_key="compile-shot-1")
            retry = await create(request, idempotency_key="compile-shot-1")
            self.assertEqual(first["id"], retry["id"])
            self.assertTrue(retry["reused"])
            self.assertEqual(first["collaboration_mode"], "quick")
            queued.assert_awaited_once()
            self.assertEqual(len(db.collaborations()), 1)
            self.assertEqual(len(db.collaboration_messages(first["id"])), 1)
            with self.assertRaises(HTTPException) as raised:
                await create(request.model_copy(update={"prompt": "Changed scene"}), idempotency_key="compile-shot-1")
            self.assertEqual(raised.exception.status_code, 409)
            queued.assert_awaited_once()
