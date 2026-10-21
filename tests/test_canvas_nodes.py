import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from backend.core.errors import GatewayError
from backend.modules.generation.canvas_nodes import CanvasNodeCatalog
from backend.modules.generation.plugins import PluginCatalog


class CanvasNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plugins = self.root / "plugins"
        self.package = self.plugins / "canvas-nodes" / "basic"
        self.package.mkdir(parents=True)
        (self.package / "INSTALL.md").write_text("# Basic canvas nodes\n\nNo external dependencies.\n", encoding="utf-8")
        (self.package / "handler.py").write_text(
            "def echo(inputs, config, runtime):\n"
            "    return {'text': config.get('prefix', '') + inputs['text']}\n",
            encoding="utf-8",
        )
        (self.package / "plugin.json").write_text(json.dumps({
            "schema_version": 1,
            "plugin_type": "canvas_node",
            "id": "basic",
            "version": "1.0.0",
            "name": "Canvas basics",
            "nodes": [{
                "id": "echo",
                "name": "Echo",
                "category": "core",
                "handler": "handler.py:echo",
                "inputs": [{"id": "text", "name": "Text", "type": "text", "required": True}],
                "outputs": [{"id": "text", "name": "Text", "type": "text"}],
                "config_schema": {"type": "object", "properties": {"prefix": {"type": "string"}},
                                  "additionalProperties": False},
            }],
        }), encoding="utf-8")
        self.context = SimpleNamespace(plugin_catalogs={}, plugin_catalog_lock=__import__("threading").RLock())
        self.catalog = CanvasNodeCatalog(self.plugins, self.context)

    def test_canvas_packages_are_isolated_from_regular_plugin_catalog(self):
        nodes, errors = self.catalog.scan()
        self.assertEqual(errors, [])
        self.assertEqual([node["type"] for node in nodes], ["basic.echo"])
        self.assertEqual(PluginCatalog(self.plugins, self.context).scan(), ([], []))
        public = self.catalog.public()
        self.assertEqual(public["items"][0]["type"], "basic.echo")
        self.assertNotIn("handler", public["items"][0])

    def test_node_schema_and_handler_are_validated(self):
        runtime = SimpleNamespace(project_id="project-1", application=SimpleNamespace())
        result = asyncio.run(self.catalog.execute(
            "basic.echo", {"text": "hello"}, {"prefix": "say: "}, runtime,
        ))
        self.assertEqual(result, {"text": "say: hello"})
        with self.assertRaises(GatewayError) as caught:
            asyncio.run(self.catalog.execute("basic.echo", {}, {}, runtime))
        self.assertEqual(caught.exception.status_code, 422)

    def test_project_category_asset_and_upload_inputs_are_scoped(self):
        manifest_path = self.package / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["nodes"][0]["inputs"].extend([
            {"id": "project", "name": "Project", "type": "project"},
            {"id": "category", "name": "Category", "type": "category"},
            {"id": "upload", "name": "Upload", "type": "upload"},
            {"id": "asset", "name": "Asset", "type": "asset"},
        ])
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        app = SimpleNamespace(
            categories=lambda project_id: [{"id": "", "name": "Default"}, {"id": "category-1"}],
            upload_exists=lambda upload_id: upload_id == "a" * 32,
            resolve_library_path=lambda project_id, path, allowed_suffixes=None: Path("/project") / path,
        )
        runtime = SimpleNamespace(project_id="project-1", application=app)

        valid = {"text": "hello", "project": "project-1", "category": "", "upload": {"upload_id": "a" * 32}}
        self.assertEqual(asyncio.run(self.catalog.execute("basic.echo", valid, {}, runtime)), {"text": "hello"})

        for invalid in (
            {**valid, "project": "project-2"},
            {**valid, "category": "other-category"},
            {**valid, "upload": {"upload_id": "b" * 32}},
            {**valid, "asset": {"project_id": "project-2", "path": "images/ref.png", "type": "image"}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(GatewayError) as caught:
                asyncio.run(self.catalog.execute("basic.echo", invalid, {}, runtime))
            self.assertEqual(caught.exception.status_code, 422)

    def test_node_file_change_requires_gateway_restart(self):
        node = self.catalog.nodes()["basic.echo"]
        (self.package / "handler.py").write_text(
            "def echo(inputs, config, runtime):\n    return {'text': 'changed'}\n", encoding="utf-8"
        )
        with self.assertRaises(GatewayError) as caught:
            asyncio.run(self.catalog.execute(
                node["type"], {"text": "hello"}, {}, SimpleNamespace(project_id="project-1", application=SimpleNamespace())
            ))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.headers.get("X-Plugin-Restart-Required"), "true")

    def test_library_asset_handle_with_metadata_is_accepted_and_internal_paths_rejected(self):
        asset_path = self.root / "project" / "images" / "reference.png"
        asset_path.parent.mkdir(parents=True)
        asset_path.write_bytes(b"image")
        runtime = SimpleNamespace(
            project_id="project-1",
            application=SimpleNamespace(
                resolve_library_path=lambda project_id, path, allowed_suffixes=None: asset_path,
            ),
        )
        asset = {
            "project_id": "project-1", "category_id": "", "name": "reference.png",
            "path": "Project/images/reference.png", "type": "image", "modified": 1.0,
            "size": 5, "url": "/v1/library/files/Project/images/reference.png",
        }
        result = asyncio.run(self.catalog.execute("basic.echo", {"text": "ok"}, {}, runtime))
        self.assertEqual(result, {"text": "ok"})
        self.catalog._validate_asset(asset, "image", runtime)
        with self.assertRaises(GatewayError) as caught:
            self.catalog._validate_asset({**asset, "path": "Project/.internal/files/state.png"}, "image", runtime)
        self.assertEqual(caught.exception.status_code, 422)

    def test_music_ports_validate_project_assets_on_input_and_output(self):
        manifest_path = self.package / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["nodes"][0]["inputs"].append({"id": "music", "name": "Music", "type": "music"})
        manifest["nodes"][0]["outputs"].append({"id": "music", "name": "Music", "type": "music"})
        manifest["nodes"][0]["config_schema"]["properties"]["music"] = {"type": "object"}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (self.package / "handler.py").write_text(
            "def echo(inputs, config, runtime):\n"
            "    return {'text': inputs['text'], 'music': config['music']}\n",
            encoding="utf-8",
        )
        music_path = self.root / "project" / "audio" / "track.mp3"
        music_path.parent.mkdir(parents=True)
        music_path.write_bytes(b"audio")
        runtime = SimpleNamespace(
            project_id="project-1",
            application=SimpleNamespace(
                resolve_library_path=lambda project_id, path, allowed_suffixes=None: music_path,
            ),
        )
        music = {"project_id": "project-1", "path": "Project/audio/track.mp3", "type": "music"}
        result = asyncio.run(self.catalog.execute(
            "basic.echo", {"text": "hello", "music": music}, {"music": music}, runtime,
        ))
        self.assertEqual(result["music"], music)

        with self.assertRaises(GatewayError) as caught:
            asyncio.run(self.catalog.execute(
                "basic.echo", {"text": "hello", "music": music},
                {"music": {**music, "project_id": "project-2"}}, runtime,
            ))
        self.assertEqual(caught.exception.status_code, 422)

        with self.assertRaises(GatewayError) as caught:
            asyncio.run(self.catalog.execute(
                "basic.echo", {"text": "hello", "music": {**music, "project_id": "project-2"}},
                {"music": music}, runtime,
            ))
        self.assertEqual(caught.exception.status_code, 422)

    def test_upload_import_result_matches_the_asset_port_contract(self):
        handler = self.package / "handler.py"
        handler.write_text(
            "def import_asset(inputs, config, runtime):\n"
            "    return {'asset': runtime.application.import_upload(inputs['upload']['upload_id'], name='ref.png')}\n",
            encoding="utf-8",
        )
        manifest = json.loads((self.package / "plugin.json").read_text(encoding="utf-8"))
        manifest["nodes"] = [{
            "id": "import", "name": "Import", "category": "resources", "handler": "handler.py:import_asset",
            "inputs": [{"id": "upload", "name": "Upload", "type": "upload", "required": True}],
            "outputs": [{"id": "asset", "name": "Asset", "type": "asset", "required": True}],
        }]
        (self.package / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        asset_path = self.root / "project" / "images" / "imports" / "_project" / "ref.png"
        asset_path.parent.mkdir(parents=True)
        asset_path.write_bytes(b"image")
        runtime = SimpleNamespace(
            project_id="project-1",
            application=SimpleNamespace(
                upload_exists=lambda upload_id: True,
                import_upload=lambda *args, **kwargs: {
                    "project_id": "project-1", "category_id": "", "name": asset_path.name,
                    "path": "Project/images/imports/_project/ref.png", "type": "image",
                    "media_type": "image/png", "size": 5, "url": "/v1/library/files/Project/images/imports/_project/ref.png",
                },
                resolve_library_path=lambda project_id, path, allowed_suffixes=None: asset_path,
            ),
        )
        result = asyncio.run(self.catalog.execute("basic.import", {"upload": {"upload_id": "a" * 32}}, {}, runtime))
        self.assertEqual(result["asset"]["path"], "Project/images/imports/_project/ref.png")

    def test_invalid_node_package_is_reported_without_disabling_other_packages(self):
        bad = self.plugins / "canvas-nodes" / "broken"
        bad.mkdir()
        (bad / "INSTALL.md").write_text("# Broken\n", encoding="utf-8")
        (bad / "plugin.json").write_text(json.dumps({
            "schema_version": 1, "plugin_type": "plugin", "id": "broken", "version": "1.0.0",
            "name": "Broken", "nodes": [],
        }), encoding="utf-8")
        nodes, errors = CanvasNodeCatalog(self.plugins).scan()
        self.assertEqual([node["type"] for node in nodes], ["basic.echo"])
        self.assertEqual(errors[0]["plugin"], "broken")

    def test_manifest_package_id_must_match_its_directory(self):
        package = self.plugins / "canvas-nodes" / "renamed-folder"
        package.mkdir()
        (package / "INSTALL.md").write_text("# Mismatched package\n", encoding="utf-8")
        (package / "handler.py").write_text(
            "def run(inputs, config, runtime):\n    return {}\n", encoding="utf-8"
        )
        (package / "plugin.json").write_text(json.dumps({
            "schema_version": 1, "plugin_type": "canvas_node", "id": "declared-id",
            "version": "1.0.0", "name": "Mismatched", "nodes": [{
                "id": "run", "name": "Run", "category": "core", "handler": "handler.py:run",
                "inputs": [], "outputs": [],
            }],
        }), encoding="utf-8")

        nodes, errors = CanvasNodeCatalog(self.plugins).scan()

        self.assertEqual([node["type"] for node in nodes], ["basic.echo"])
        self.assertEqual(errors[0]["plugin"], "renamed-folder")
        self.assertIn("match its directory name", errors[0]["error"])

    def test_package_symlink_is_rejected_even_when_it_points_inside_package(self):
        alias = self.package / "handler_alias.py"
        try:
            alias.symlink_to(self.package / "handler.py")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks are unavailable in this test environment: {exc}")
        manifest_path = self.package / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["nodes"][0]["handler"] = "handler_alias.py:echo"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        nodes, errors = CanvasNodeCatalog(self.plugins).scan()

        self.assertEqual(nodes, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("symbolic links or reparse points", errors[0]["error"])

    def test_canvas_node_directory_symlink_is_rejected(self):
        target = self.plugins / "canvas-target"
        target.mkdir()
        directory = self.plugins / "canvas-nodes"
        directory.rename(self.plugins / "canvas-nodes-real")
        try:
            directory.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            (self.plugins / "canvas-nodes-real").rename(directory)
            self.skipTest(f"Directory symlinks are unavailable in this test environment: {exc}")

        nodes, errors = CanvasNodeCatalog(self.plugins).scan()

        self.assertEqual(nodes, [])
        self.assertEqual(errors[0]["plugin"], "canvas-nodes")
        self.assertIn("directory cannot be a symbolic link", errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
