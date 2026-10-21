import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
import asyncio
import json

from backend.modules.projects.service import ProjectService
from backend.modules.shared.application_runtime import ApplicationRuntime
from backend.modules.shared.plugin_runtime import PluginRuntime, PluginError
from backend.persistence.database import Database


class CanvasResourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = Database(self.root / "test.sqlite")
        self.db.initialize({})
        plugins = self.root / "plugins"
        plugins.mkdir()
        uploads = self.root / "uploads"
        uploads.mkdir()
        self.context = SimpleNamespace(
            db=self.db,
            paths=SimpleNamespace(
                root=self.root, projects=self.root / "projects", uploads=uploads,
                tasks=self.root / "tasks", artifacts=self.root / "artifacts", plugins=plugins,
            ),
            jobs={}, executing_jobs=set(), library_cache={"directory": "", "created_at": 0, "items": []},
            library_lock=threading.Lock(), plugin_catalogs={}, plugin_catalog_lock=threading.RLock(),
        )
        self.service = ProjectService(self.context)
        self.project_id = self.service.create("Project One")["id"]
        self.category_id = self.service.save_category(self.project_id, "Episode 1")["id"]
        self.runtime = ApplicationRuntime(self.context, "infinite-canvas", self.project_id, self.category_id)

    def _upload(self, upload_id, suffix, content=b"test media"):
        path = self.context.paths.uploads / f"{upload_id}{suffix}"
        path.write_bytes(content)
        self.db.register_upload(upload_id)
        return path

    def test_import_upload_is_registered_project_scoped_and_category_filtered(self):
        upload_id = "a" * 32
        self._upload(upload_id, ".png")

        asset = self.runtime.import_upload(upload_id, name="reference.png")

        self.assertEqual(asset["project_id"], self.project_id)
        self.assertEqual(asset["category_id"], self.category_id)
        self.assertEqual(asset["type"], "image")
        self.assertNotIn("output_dir", self.runtime.library())
        self.assertEqual(self.runtime.library(kind="image")["total"], 1)
        self.assertEqual(self.runtime.library(category_id="")["total"], 0)
        self.assertEqual(self.runtime.library(category_id=self.category_id)["items"][0]["path"], asset["path"])

    def test_import_rejects_unregistered_or_mismatched_upload_and_cross_project(self):
        unregistered_id = "b" * 32
        (self.context.paths.uploads / f"{unregistered_id}.png").write_bytes(b"unregistered")
        with self.assertRaisesRegex(ValueError, "不存在或已过期"):
            self.runtime.import_upload(unregistered_id)

        audio_id = "c" * 32
        self._upload(audio_id, ".wav")
        with self.assertRaisesRegex(ValueError, "类型与文件格式不匹配"):
            self.runtime.import_upload(audio_id, kind="image")

        other_project_id = self.service.create("Project Two")["id"]
        with self.assertRaisesRegex(ValueError, "不属于当前调用"):
            self.runtime.import_upload(audio_id, project_id=other_project_id)
        with self.assertRaisesRegex(ValueError, "不属于当前调用"):
            self.runtime.categories(other_project_id)

    def test_upload_reference_requires_a_registered_live_file(self):
        upload_id = "d" * 32
        self._upload(upload_id, ".mp4")
        self.assertTrue(self.runtime.upload_exists(upload_id))
        self.context.paths.uploads.joinpath(f"{upload_id}.mp4").unlink()
        self.assertFalse(self.runtime.upload_exists(upload_id))
        self.assertFalse(self.runtime.upload_exists("../" + upload_id))

    def test_plugin_runtime_executes_canvas_package_without_regular_plugin_settings(self):
        package = self.context.paths.plugins / "canvas-nodes" / "runtime-nodes"
        package.mkdir(parents=True)
        (package / "INSTALL.md").write_text("# Runtime nodes\n\nNo dependencies.\n", encoding="utf-8")
        (package / "handler.py").write_text(
            "def echo(inputs, config, runtime):\n    return {'plugin': runtime.plugin_id, 'text': inputs['text']}\n",
            encoding="utf-8",
        )
        (package / "plugin.json").write_text(json.dumps({
            "schema_version": 1, "plugin_type": "canvas_node", "id": "runtime-nodes",
            "version": "1.0.0", "name": "Runtime nodes", "nodes": [{
                "id": "echo", "name": "Echo", "category": "core", "handler": "handler.py:echo",
                "inputs": [{"id": "text", "name": "Text", "type": "text", "required": True}],
                "outputs": [{"id": "plugin", "name": "Plugin", "type": "text"},
                            {"id": "text", "name": "Text", "type": "text"}],
            }],
        }), encoding="utf-8")
        caller = PluginRuntime("infinite-canvas", {}, self.context, project_id=self.project_id)

        result = asyncio.run(caller.execute_canvas_node("runtime-nodes.echo", {"text": "ok"}))

        self.assertEqual(result, {"plugin": "runtime-nodes", "text": "ok"})
        other_project = self.service.create("Project Other")["id"]
        with self.assertRaises(PluginError):
            asyncio.run(caller.execute_canvas_node("runtime-nodes.echo", {"text": "no"}, project_id=other_project))

    def test_canvas_http_contract_is_registered_separately(self):
        from backend.interfaces.http.api_v2 import build_router

        router = build_router(
            context=self.context, db=self.db, auth=lambda: None, workflow_registry=lambda: {},
            workflows_path=self.context.paths.plugins, submit=None, generate_model=None, tts_model=None,
            jobs=lambda: {}, public_job=None, hydrate_job=None, upload_cache=self.context.paths.uploads,
            upload_handler=None, style_items=None, cancel_handler=None, agent_handler=None,
            agent_model=None, library_handler=None,
        )

        routes = {(route.path, method) for route in router.routes for method in getattr(route, "methods", set())}
        self.assertIn(("/api/v2/canvas-nodes", "GET"), routes)
        self.assertIn(("/api/v2/canvas-nodes/{node_type}/execute", "POST"), routes)


if __name__ == "__main__":
    unittest.main()
