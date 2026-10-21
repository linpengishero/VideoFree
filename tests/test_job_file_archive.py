"""Single-user extension groundwork; no live ComfyUI or GPU required."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
from unittest.mock import Mock, patch

from backend.integrations.system_services.comfyui import load_provider
from backend.integrations.system_services.storage import LocalStorageProvider
from backend.modules.projects.job_files import delete_job_files
from backend.modules.projects.service import ProjectService
from backend.modules.shared.plugin_runtime import PluginRuntime
from backend.persistence import Database


class JobFileArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = Database(self.root / "test.db")
        self.db.initialize({})
        self.project = self.db.create_project(dict(id="p1", name="Project", output_subdir="Project"))
        self.db.create_project(dict(id="p2", name="Other", output_subdir="Other"))
        self.context = SimpleNamespace(db=self.db, state_lock=threading.RLock(), job_file_lock=threading.RLock(),
            storage_provider=LocalStorageProvider(self.root / "projects"),
            comfyui_provider=Mock(), jobs={}, library_cache={})
        self.runtime = PluginRuntime("model-a", {}, self.context, project_id="p1")
        for identity, project, plugin in (("video-a", "p1", "model-a"), ("video-b", "p1", "model-a"),
                                         ("video-other", "p2", "model-a"), ("video-foreign", "p1", "model-b")):
            self.db.insert_job(dict(id=identity, project_id=project, kind="video", status="completed",
                request={"generation": {"plugin_id": plugin}}, created_at=1))
        self.source = self.root / "latent.bin"
        self.source.write_bytes(b"opaque model data" * 100)

    def test_local_archive_is_independent_and_restorable(self):
        record = self.runtime.save_job_file("video-a", "native-latent", source=self.source,
                                           metadata={"format": "any-model", "version": 1})
        self.source.unlink()
        with self.runtime.materialize_job_file("video-a", "native-latent") as path:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            self.assertEqual(path.stat().st_size, record["size"])
        self.runtime.restore_job_file("video-a", "native-latent", "model/checkpoint.bin")
        self.assertEqual(self.context.comfyui_provider.upload_file.call_args.args[1], "model/checkpoint.bin")
        self.assertEqual(record["metadata"]["format"], "any-model")

    def test_link_survives_source_deletion_and_last_reference_cleans_blob(self):
        record = self.runtime.save_job_file("video-a", "cache", source=self.source)
        self.runtime.link_job_file("video-a", "cache", "video-b")
        delete_job_files(self.context, "video-a")
        self.assertIsNone(self.runtime.job_file("video-a", "cache"))
        with self.runtime.materialize_job_file("video-b", "cache") as path:
            self.assertTrue(path.is_file())
        delete_job_files(self.context, "video-b")
        self.assertFalse(self.context.storage_provider.list_files())
        self.assertFalse(self.db.job_file_referenced(record["object_key"]))

    def test_scope_and_names_are_checked(self):
        for job, name in (("video-other", "cache"), ("video-foreign", "cache"),
                          ("missing", "cache"), ("video-a", "../escape")):
            with self.subTest(job=job, name=name), self.assertRaises(ValueError):
                self.runtime.save_job_file(job, name, source=self.source)
        self.runtime.save_job_file("video-a", "cache", source=self.source)
        with self.assertRaises(ValueError):
            self.runtime.link_job_file("video-a", "cache", "video-other")

    def test_expected_checksum_rejects_before_publishing(self):
        for kwargs in ({"sha256": "0" * 64}, {"size": 1}):
            with self.assertRaises(ValueError):
                self.runtime.save_job_file("video-a", "cache", source=self.source, **kwargs)
        self.assertEqual(self.context.storage_provider.list_files(), [])
        self.assertIsNone(self.runtime.job_file("video-a", "cache"))

    def test_corrupt_archive_is_never_restored(self):
        record = self.runtime.save_job_file("video-a", "cache", source=self.source)
        self.context.storage_provider.local_path(record["object_key"]).write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.runtime.restore_job_file("video-a", "cache", "model/cache.bin")
        self.context.comfyui_provider.upload_file.assert_not_called()

    def test_remote_output_is_streamed_and_closed(self):
        stream = io.BytesIO(b"remote latent")
        @contextmanager
        def opened(descriptor):
            with stream:
                yield stream
        self.context.comfyui_provider.open_output.side_effect = opened
        record = self.runtime.save_job_file("video-a", "cache", output={"filename": "latent.bin"})
        self.assertEqual(record["size"], 13)
        self.assertTrue(stream.closed)

    def test_dependencies_are_immutable_and_not_public_media(self):
        self.runtime.save_job_file("video-a", "cache", source=self.source)
        self.source.write_bytes(b"different")
        with self.assertRaises(ValueError):
            self.runtime.save_job_file("video-a", "cache", source=self.source)
        with self.assertRaises(ValueError):
            ProjectService(self.context).authorize_library_path(Path("Project/.internal/files/x.png"))

    def test_archive_copy_does_not_hold_global_state_lock(self):
        original = self.context.storage_provider.put_stream
        acquired = []
        def probe():
            locked = self.context.state_lock.acquire(timeout=1)
            acquired.append(locked)
            if locked:
                self.context.state_lock.release()
        def copy(stream, key):
            thread = threading.Thread(target=probe)
            thread.start()
            thread.join(2)
            self.assertEqual(acquired, [True])
            return original(stream, key)
        with patch.object(self.context.storage_provider, 'put_stream', side_effect=copy):
            self.runtime.save_job_file('video-a', 'cache', source=self.source)

    def test_delete_waits_for_archive_publication_without_leaving_orphans(self):
        original = self.context.storage_provider.put_stream
        copying, release, deleting = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def copy(stream, key):
            copying.set()
            if not release.wait(3):
                raise TimeoutError('test copy was not released')
            return original(stream, key)
        def save():
            try:
                self.runtime.save_job_file('video-a', 'cache', source=self.source)
            except Exception as exc:
                errors.append(exc)
        def delete():
            deleting.set()
            try:
                delete_job_files(self.context, 'video-a')
            except Exception as exc:
                errors.append(exc)
        with patch.object(self.context.storage_provider, 'put_stream', side_effect=copy):
            writer = threading.Thread(target=save)
            writer.start()
            try:
                self.assertTrue(copying.wait(2))
                remover = threading.Thread(target=delete)
                remover.start()
                self.assertTrue(deleting.wait(2))
            finally:
                release.set()
                writer.join(4)
            remover.join(4)
        self.assertFalse(writer.is_alive() or remover.is_alive())
        self.assertEqual(errors, [])
        self.assertIsNone(self.runtime.job_file('video-a', 'cache'))
        self.assertEqual(self.context.storage_provider.list_files(), [])

    def test_internal_files_reject_windows_aliases_at_http_boundary(self):
        import asyncio
        from fastapi import HTTPException
        from backend.interfaces.http import v1_assets

        record = self.runtime.save_job_file('video-a', 'cache', source=self.source)
        with patch.object(v1_assets, 'context', self.context):
            for alias in ('.internal', '.INTERNAL', '.Internal', '.internal.', '.internal '):
                key = record['object_key'].replace('.internal', alias)
                with self.subTest(alias=alias), self.assertRaises(HTTPException) as raised:
                    asyncio.run(v1_assets.library_file(key))
                self.assertEqual(raised.exception.status_code, 404)

    def test_project_delete_cascades_file_metadata(self):
        self.runtime.save_job_file("video-a", "cache", source=self.source)
        self.db.delete_project("p1")
        self.assertEqual(self.db.job_files("video-a"), [])
        self.assertIsNotNone(self.db.project("p2"))

    def test_migration_defaults_and_internal_attribution(self):
        with self.db.connect() as connection:
            connection.execute("ALTER TABLE projects DROP COLUMN tenant_id")
            connection.execute("ALTER TABLE projects DROP COLUMN created_by")
            connection.execute("ALTER TABLE jobs DROP COLUMN created_by")
            connection.execute("ALTER TABLE jobs DROP COLUMN execution_node_id")
        self.db.initialize({})
        self.assertEqual(self.db.project("p1")["tenant_id"], "local")
        self.assertEqual(self.db.job("video-a")["created_by"], "local")
        self.assertEqual(self.db.job("video-a")["execution_node_id"], "")
        project = self.db.create_project(dict(id="p3", name="future", output_subdir="future",
                                              tenant_id="reserved", created_by="creator"))
        self.assertEqual(project["tenant_id"], "reserved")
        self.db.register_upload("upload1")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT tenant_id FROM upload_metadata").fetchone()[0], "local")
        self.db.delete_upload_metadata("upload1")


class ComfyUIExtensionTests(unittest.TestCase):
    def test_dependency_upload_reports_size_limit_with_recovery_instructions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'latent.bin'
            path.write_bytes(b'latent')
            error = urllib.error.HTTPError('http://localhost/upload/image', 413, 'Too large', {}, io.BytesIO())
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, r'HTTP 413.*--max-upload-size'):
                    load_provider('http://localhost').upload_file(path, 'model/latent.bin')

    def test_default_provider_and_legacy_alias_share_one_implementation(self):
        from backend.integrations.comfyui import ComfyUIClient
        provider = load_provider("http://localhost:8189/")
        self.assertIsInstance(provider, ComfyUIClient)
        self.assertEqual(provider.node_id, "default")
        self.assertEqual(provider.base_url, "http://localhost:8189")

    def test_manifest_rejects_version_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = dict(schema_version=1, contract_version=1, service_id="comfyui",
                            provider_id="default", entry="../outside.py:Provider")
            for changes in ({}, {"contract_version": 2}):
                (root / "provider.json").write_text(json.dumps({**manifest, **changes}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_provider("http://localhost", root)

    def test_opaque_upload_streams_multipart_and_validates_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "latent.bin"
            path.write_bytes(b"latent-data")
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b'{"name":"latent.bin","subfolder":"model","type":"output"}'
            def send(request, **kwargs):
                self.assertNotIsInstance(request.data, bytes)
                content = b"".join(request.data)
                self.assertEqual(len(content), int(request.headers["Content-length"]))
                self.assertIn(b"latent-data", content)
                return response
            provider = load_provider("http://localhost")
            with patch("urllib.request.urlopen", side_effect=send):
                provider.upload_file(path, "model/latent.bin")
            for target in ("../outside", "/outside", "model/../x", 'model/evil"', "model/a\r\nb"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    provider.upload_file(path, target)


if __name__ == "__main__":
    unittest.main()
