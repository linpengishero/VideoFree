from io import BytesIO
import tempfile
import unittest
from pathlib import Path

from backend.integrations.system_services import LocalStorageProvider


class LocalStorageProviderTests(unittest.TestCase):
    def test_put_read_list_and_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "library"
            provider = LocalStorageProvider(root)
            source = Path(temporary) / "source.bin"
            source.write_bytes(b"payload")

            stored = provider.put_file(source, "project-a/images/item.bin")

            self.assertEqual(stored.key, "project-a/images/item.bin")
            self.assertEqual(stored.size, 7)
            with provider.open(stored.key) as stream:
                self.assertEqual(stream.read(), b"payload")
            self.assertEqual([item.key for item in provider.list_files("project-a")], [stored.key])
            self.assertTrue(provider.delete(stored.key))
            self.assertFalse(provider.delete(stored.key))

    def test_rejects_path_traversal_and_absolute_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = LocalStorageProvider(Path(temporary) / "library")
            for key in ("../outside", "a/../../outside", "/outside"):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    provider.ensure_directory(key)

    def test_delete_prefix_is_scoped_to_requested_object_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = LocalStorageProvider(Path(temporary) / "library")
            source = Path(temporary) / "source.bin"
            source.write_bytes(b"x")
            provider.put_file(source, "project-a/images/one.bin")
            provider.put_file(source, "project-ab/images/keep.bin")

            self.assertEqual(provider.delete_prefix("project-a"), 1)
            self.assertEqual([item.key for item in provider.list_files()], ["project-ab/images/keep.bin"])

    def test_stream_write_and_local_materialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = LocalStorageProvider(Path(temporary) / "library")

            stored = provider.put_stream(BytesIO(b"streamed"), "project-a/audio/item.wav")

            with provider.materialize(stored.key) as path:
                self.assertEqual(path.read_bytes(), b"streamed")


if __name__ == "__main__":
    unittest.main()
