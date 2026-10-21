import tempfile
import unittest
import asyncio
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.persistence.database import Database
from backend.modules.projects.service import ProjectService


class ProjectCategoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = Database(self.root / "test.sqlite")
        self.db.initialize({})
        self.context = SimpleNamespace(db=self.db, state_lock=threading.RLock(), jobs={}, executing_jobs=set(), library_cache={}, paths=SimpleNamespace(projects=self.root / "projects", uploads=self.root / "uploads", tasks=self.root / "tasks", artifacts=self.root / "artifacts"))
        self.context.paths.uploads.mkdir()
        self.context.paths.artifacts.mkdir()
        self.service = ProjectService(self.context)
        self.project = self.service.create("Project A")["id"]

    def job(self, category=""):
        value = {"id": "job-one", "kind": "image", "status": "completed", "created_at": 1,
                 "request": {}, "project_id": self.project, "category_id": category}
        self.db.insert_job(value)
        self.context.jobs[value["id"]] = value
        return value

    def test_project_update_preserves_omitted_fields_and_allows_explicit_clear(self):
        from backend.interfaces.http import v1_projects

        self.service.update(self.project, 'Project A', 'Original description', 'Original summary')
        with patch.object(v1_projects, 'service', self.service):
            result = asyncio.run(v1_projects.update_project(
                self.project, v1_projects.ProjectUpdate(name='Renamed')))
            self.assertEqual(result['description'], 'Original description')
            self.assertEqual(result['content_summary'], 'Original summary')
            result = asyncio.run(v1_projects.update_project(
                self.project, v1_projects.ProjectUpdate(name='Renamed', description='New description')))
            self.assertEqual(result['description'], 'New description')
            self.assertEqual(result['content_summary'], 'Original summary')
            result = asyncio.run(v1_projects.update_project(
                self.project, v1_projects.ProjectUpdate(name='Renamed', description='', content_summary='')))
            self.assertEqual(result['description'], '')
            self.assertEqual(result['content_summary'], '')

    def test_library_lists_stored_media_and_serves_files(self):
        from backend.interfaces.http import v1_assets

        self.context.library_lock = threading.Lock()
        self.context.library_cache = {'directory': '', 'created_at': 0, 'items': []}
        self.context.paths.plugins = self.root / 'plugins'
        with patch.object(v1_assets, 'context', self.context), patch('backend.modules.generation.plugins.PluginCatalog') as catalog:
            catalog.return_value.applications.return_value = []
            result = asyncio.run(v1_assets.library(project_id=self.project))
            self.assertEqual(result['total'], 0)
            project = self.db.project(self.project)
            for folder, filename, kind in [('audio', '\u58f0\u97f3.mp3', 'audio'), ('images', 'image.png', 'image'), ('video', 'clip.mp4', 'video')]:
                key = f"{project['output_subdir']}/{folder}/{filename}"
                self.service.storage.put_stream(BytesIO(b'media'), key)
                self.context.library_cache['created_at'] = 0
                result = asyncio.run(v1_assets.library(project_id=self.project, kind=kind))
                self.assertEqual(result['total'], 1)
                self.assertEqual(result['items'][0]['path'], key)
                response = asyncio.run(v1_assets.library_file(key))
                self.assertEqual(Path(response.path).read_bytes(), b'media')
            result = asyncio.run(v1_assets.library(project_id=self.project))
            self.assertEqual(result['total'], 3)

    def test_windows_reserved_project_names_do_not_insert_rows(self):
        count = len(self.db.projects(True))
        for name in ('CON', 'nul.txt', 'COM1', 'lpt9.mp4', 'AUX', 'PRN', 'CON .txt'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.service.create(name)
        self.assertEqual(len(self.db.projects(True)), count)
        self.assertTrue(self.service.list())

    def test_directory_failure_does_not_insert_project(self):
        count = len(self.db.projects(True))
        with patch.object(self.service, 'ensure_directory', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.service.create('Cannot write')
        self.assertEqual(len(self.db.projects(True)), count)

    def test_database_failure_cleans_empty_project_directory(self):
        with patch.object(self.db, 'create_project', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                self.service.create('Cannot insert')
        self.assertFalse((self.service.projects_root / 'Cannot insert').exists())

    def test_old_jobs_and_repeated_migration_remain_default(self):
        self.job()
        with self.db.connect() as connection:
            connection.execute("ALTER TABLE jobs DROP COLUMN category_id")
        self.db.initialize({})
        self.db.initialize({})
        self.assertEqual(self.db.job("job-one")["category_id"], "")
        self.assertEqual(self.service.validate_category(self.project, None), "")
        self.assertEqual(self.service.categories(self.project)[0]["name"], "默认分类")

    def test_names_and_project_isolation(self):
        category = self.service.save_category(self.project, "Episode 1")
        self.service.save_category(self.project, "Episode 2", category["id"])
        self.assertEqual(self.service.categories(self.project)[1]["name"], "Episode 2")
        for name in ("", "默认分类", "公共资产", "全部素材", "Episode 2", "a" * 81):
            with self.assertRaises(ValueError):
                self.service.save_category(self.project, name)
        other = self.service.create("Project B")["id"]
        with self.assertRaises(ValueError):
            self.service.validate_category(other, category["id"])
        with self.assertRaises(ValueError):
            self.service.save_category(self.project, "renamed", "")
        with self.assertRaises(ValueError):
            self.service.delete_category(self.project, "")

    def test_resource_directory_switch_uses_only_new_root(self):
        old_root = self.service.projects_root
        old_file = old_root / "Project A" / "images" / "old.png"
        old_file.parent.mkdir(parents=True, exist_ok=True)
        old_file.write_bytes(b"old")
        new_root = self.root / "new-library"
        self.db.save_settings({"resource_directory": str(new_root)})
        self.assertEqual(self.service.projects_root, new_root.resolve())
        new_project = self.service.ensure_directory(self.db.project(self.project))
        self.assertTrue(new_project.is_dir())
        self.assertFalse((new_project / "images" / "old.png").exists())
        self.assertTrue(old_file.exists())

    def test_waiting_collaboration_blocks_category_deletion(self):
        category = self.service.save_category(self.project, 'Waiting episode')['id']
        for status in ('queued', 'running', 'needs_input', 'awaiting_confirmation'):
            with self.subTest(status=status):
                self.db.create_collaboration({'id': status, 'capability_id': 'example.create',
                    'model_id': 'example', 'mode_id': 'create', 'status': status,
                    'project_id': self.project, 'request': {'category_id': category}})
                with self.assertRaises(RuntimeError):
                    self.service.delete_category(self.project, category)
                self.db.update_collaboration(status, {'status': 'cancelled'})
        self.service.delete_category(self.project, category)
        self.assertFalse(self.db.project_categories(self.project))

    def test_delete_category_removes_its_files_only(self):
        category = self.service.save_category(self.project, "Episode 1")["id"]
        self.job(category)
        self.assertEqual(self.db.job("job-one")["category_id"], category)
        self.assertEqual(self.context.jobs["job-one"]["category_id"], category)
        image = self.root / "keep.png"
        image.write_bytes(b"unchanged")
        self.db.update_job("job-one", {"artifacts_json": '[{"project_path":"Project A/images/job-one_0.png"}]'})
        self.assertEqual(self.service.library_categories(self.project)["Project A/images/job-one_0.png"], category)
        published = self.root / 'projects/Project A/images/job-one_0.png'
        published.write_bytes(b'generated')
        self.service.delete_category(self.project, category)
        self.assertIsNone(self.db.job("job-one"))
        self.assertNotIn("job-one", self.context.jobs)
        self.assertFalse(published.exists())
        self.assertEqual(image.read_bytes(), b"unchanged")

    def test_public_assets_independent_files_and_types(self):
        from backend.modules.projects.assets import PublicAssetService
        service = PublicAssetService(self.context)
        asset = service.save(self.project, 'Hero', 'character', 'Quiet and loyal')
        source = self.root / 'projects/Project A/images/role.png'
        source.write_bytes(b'roleboard')
        asset = service.attach(self.project, asset['id'], 'Project A/images/role.png')
        archived = self.root / 'projects' / asset['media'][0]['path']
        source.unlink()
        self.assertEqual(archived.read_bytes(), b'roleboard')
        service.attach(self.project, asset['id'], asset['media'][0]['path'])
        other = self.service.create('Other')['id']
        with self.assertRaises(ValueError):
            service.get(other, asset['id'])
        service.delete(self.project, asset['id'])
        self.assertFalse(archived.exists())
        self.assertEqual(service.list(self.project), [])

    def test_published_project_media_uses_storage_provider(self):
        job = self.job()
        source = self.root / "generated.png"
        source.write_bytes(b"generated")

        published = self.service.publish(job, [source])

        self.assertEqual(published[0]["relative_path"], "Project A/images/job-one_0.png")
        self.assertEqual(Path(published[0]["path"]).read_bytes(), b"generated")
        self.service.delete_published([{"project_path": published[0]["relative_path"]}])
        self.assertFalse(Path(published[0]["path"]).exists())

    def test_character_sheet_and_voice_are_independent(self):
        from backend.modules.projects.assets import PublicAssetService
        service = PublicAssetService(self.context)
        asset = service.save(self.project, 'Hero', 'character', 'Quiet')
        image = self.context.paths.uploads / ('e' * 32 + '.png')
        audio = self.context.paths.uploads / ('f' * 32 + '.wav')
        image.write_bytes(b'image')
        audio.write_bytes(b'audio')
        asset = service.attach(self.project, asset['id'], 'upload:' + 'e' * 32)
        asset = service.attach(self.project, asset['id'], 'upload:' + 'f' * 32, 'character_voice', 'Hello')
        self.assertEqual([m['role'] for m in asset['media']], ['character_sheet', 'character_voice'])
        self.assertEqual(asset['media'][1]['transcript'], 'Hello')
        service.attach(self.project, asset['id'], 'upload:' + 'f' * 32, 'character_voice')
        asset = service.save(self.project, 'Hero', 'character', 'Quiet', asset['id'], 'New words')
        self.assertEqual(service.get(self.project, asset['id'])['media'][1]['transcript'], 'New words')
        self.assertEqual(asset['media'][0]['type'], 'image')

    def test_public_audio_and_path_safety(self):
        from backend.modules.projects.assets import PublicAssetService
        service = PublicAssetService(self.context)
        asset = service.save(self.project, 'Theme', 'music', 'Opening theme')
        source = self.context.paths.uploads / ('a' * 32 + '.wav')
        source.write_bytes(b'audio')
        asset = service.attach(self.project, asset['id'], 'upload:' + 'a' * 32)
        self.assertEqual(asset['media'][0]['type'], 'music')
        for value in ('../../test.sqlite', 'upload:../bad'):
            with self.assertRaises(ValueError):
                service.attach(self.project, asset['id'], value)
        job = self.job()
        self.db.update_job_request(job['id'], {'url':asset['media'][0]['url']})
        with self.assertRaises(RuntimeError):
            service.delete(self.project, asset['id'])

    def test_category_deletion_does_not_remove_public_archive(self):
        from backend.modules.projects.assets import PublicAssetService
        assets = PublicAssetService(self.context)
        category = self.service.save_category(self.project, 'Episode')['id']
        self.job(category)
        source = self.root / 'projects/Project A/images/job-one_0.png'
        source.write_bytes(b'roleboard')
        asset = assets.save(self.project, 'Hero', 'character', 'Loyal')
        asset = assets.attach(self.project, asset['id'], 'Project A/images/job-one_0.png')
        self.service.delete_category(self.project, category)
        self.assertFalse(source.exists())
        self.assertEqual((self.root / 'projects' / asset['media'][0]['path']).read_bytes(), b'roleboard')
        self.assertEqual(len(assets.list(self.project)), 1)

    def test_public_asset_type_and_media_removal(self):
        from backend.modules.projects.assets import PublicAssetService
        assets = PublicAssetService(self.context)
        asset = assets.save(self.project, 'Mountain', 'scene', 'Cold morning')
        wav = self.context.paths.uploads / ('b' * 32 + '.wav')
        wav.write_bytes(b'audio')
        asset = assets.attach(self.project, asset['id'], 'upload:' + 'b' * 32)
        asset = assets.save(self.project, 'Mountain', 'character', '', asset['id'])
        img = self.context.paths.uploads / ('c' * 32 + '.png')
        img.write_bytes(b'image')
        asset = assets.attach(self.project, asset['id'], 'upload:' + 'c' * 32)
        target = self.root / 'projects' / asset['media'][0]['path']
        assets.remove_media(self.project, asset['id'], asset['media'][0]['id'])
        self.assertFalse(target.exists())
        self.assertEqual(len(assets.get(self.project, asset['id'])['media']), 1)

    def test_category_move_is_not_exposed(self):
        from backend.interfaces.http.v1_projects import router

        self.assertFalse(any(route.path.endswith("/jobs/{job_id}/category") for route in router.routes))
        self.assertFalse(hasattr(self.service, "move_job_category"))

    def test_public_assets_http_contract(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.interfaces.http import v1_projects
        from backend.modules.projects.assets import PublicAssetService

        app = FastAPI()
        app.include_router(v1_projects.router)
        app.dependency_overrides[v1_projects.auth] = lambda: None
        base = f"/v1/projects/{self.project}/public-assets"
        with patch.object(v1_projects, "context", self.context), patch.object(v1_projects, "service", self.service), patch.object(v1_projects, "assets", PublicAssetService(self.context)), TestClient(app) as client:
            response = client.post(base, json={"name": "Theme", "kind": "music", "description": "Opening"})
            self.assertEqual(response.status_code, 201)
            asset = response.json()
            self.assertEqual(client.get(base).json()["items"][0]["id"], asset["id"])
            detail = f"{base}/{asset['id']}"
            response = client.put(detail, json={"name": "New theme", "kind": "music", "description": "Closing"})
            self.assertEqual(response.json()["description"], "Closing")
            self.assertEqual(client.post(f"{detail}/media", json={"source": "../bad.wav"}).status_code, 422)
            self.assertEqual(client.delete(detail).status_code, 200)
            self.assertEqual(client.get(base).json()["items"], [])
            voice = self.context.paths.uploads / ('f' * 32 + '.wav')
            voice.write_bytes(b'voice')
            asset = client.post(base, json={"name":"Hero", "kind":"character"}).json()
            detail = f"{base}/{asset['id']}"
            response = client.post(f"{detail}/media", json={"source":"upload:" + 'f' * 32, "role":"character_voice", "transcript":"Hello"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['media'][0]['transcript'], 'Hello')
            response = client.put(detail, json={"name":"Hero", "kind":"character", "voice_text":"Updated"})
            self.assertEqual(response.json()['media'][0]['transcript'], 'Updated')

    def test_project_deletion_removes_public_files_and_records(self):
        from backend.modules.projects.assets import PublicAssetService
        assets = PublicAssetService(self.context)
        asset = assets.save(self.project, "Theme", "music", "Opening")
        source = self.context.paths.uploads / ("d" * 32 + ".wav")
        source.write_bytes(b"audio")
        asset = assets.attach(self.project, asset["id"], "upload:" + "d" * 32)
        target = self.root / "projects" / asset["media"][0]["path"]
        self.service.delete(self.project)
        self.assertFalse(target.exists())
        self.assertEqual(self.db.project_assets(self.project), [])

    def test_project_delete_http_maps_storage_os_error_to_recoverable_conflict(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.interfaces.http import v1_projects

        app = FastAPI()
        app.include_router(v1_projects.router)
        app.dependency_overrides[v1_projects.auth] = lambda: None
        with patch.object(v1_projects, "service", self.service), \
             TestClient(app) as client:
            with patch.object(self.service, "delete", side_effect=PermissionError("denied")):
                response = client.delete(f"/v1/projects/{self.project}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("目录权限", response.json()["detail"])

    def test_active_generation_blocks_category_deletion(self):
        category = self.service.save_category(self.project, "Episode 1")["id"]
        self.job(category)["status"] = "queued"
        with self.assertRaises(RuntimeError):
            self.service.delete_category(self.project, category)
        self.assertEqual(len(self.service.categories(self.project)), 2)

    def test_project_deletion_cascades_categories(self):
        self.service.save_category(self.project, "Episode 1")
        self.db.delete_project(self.project)
        self.assertEqual(self.db.project_categories(self.project), [])

    def test_scoped_clear_preserves_other_categories(self):
        from backend.interfaces.http import v1_generation

        self.job()
        category = self.service.save_category(self.project, "Episode 1")["id"]
        other = {"id": "job-two", "kind": "image", "status": "running", "created_at": 2,
                 "request": {}, "project_id": self.project, "category_id": category}
        self.db.insert_job(other)
        self.context.jobs[other["id"]] = other
        with patch.object(v1_generation, "context", self.context), \
             patch.object(ProjectService, "current", return_value={"id": self.project}), \
             patch.object(v1_generation, "delete_job_files") as remove:
            result = asyncio.run(v1_generation.clear_jobs(category_id=""))
        self.assertEqual(result["deleted"], 1)
        remove.assert_called_once()
        self.assertIsNone(self.db.job("job-one"))
        self.assertEqual(self.db.job("job-two")["category_id"], category)

    def test_hydration_uses_current_category_not_submission_snapshot(self):
        from backend.modules.generation.task_store import TaskStore

        job = self.job()
        job["request"] = {"category_id": "deleted-category"}
        store = TaskStore(self.root / "tasks", self.root / "uploads")
        self.assertEqual(store.hydrate(job)["category_id"], "")
