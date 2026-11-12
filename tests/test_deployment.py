import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import download, extract_source, mirror_url, settings  # noqa: E402
from download_model_ranges import download_ranges  # noqa: E402
from download_models import public_candidates, select_public  # noqa: E402
from preflight import validate_graph  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "guard", ROOT / "custom_nodes/h3_control_guard/__init__.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class DownloadTests(unittest.TestCase):
    def test_fresh_download_checks_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            with patch("urllib.request.urlopen", return_value=Response(b"good")):
                download(
                    "https://mirror.invalid/model", target, hashlib.sha256(b"good").hexdigest(), 4
                )
            self.assertEqual(target.read_bytes(), b"good")

    def test_resume_uses_correct_range(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            target.with_name("model.part").write_bytes(b"ab")
            with patch(
                "urllib.request.urlopen",
                return_value=Response(b"cd", 206, {"Content-Range": "bytes 2-3/4"}),
            ) as mock:
                download(
                    "https://mirror.invalid/model", target, hashlib.sha256(b"abcd").hexdigest(), 4
                )
                self.assertEqual(mock.call_args.args[0].get_header("Range"), "bytes=2-")
            self.assertEqual(target.read_bytes(), b"abcd")

    def test_server_ignoring_range_restarts_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            target.with_name("model.part").write_bytes(b"ab")
            with patch("urllib.request.urlopen", return_value=Response(b"abcd")):
                download(
                    "https://mirror.invalid/model", target, hashlib.sha256(b"abcd").hexdigest(), 4
                )
            self.assertEqual(target.read_bytes(), b"abcd")

    def test_incorrect_range_does_not_append(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            partial = target.with_name("model.part")
            partial.write_bytes(b"ab")
            with patch(
                "urllib.request.urlopen",
                return_value=Response(b"cd", 206, {"Content-Range": "bytes 0-1/4"}),
            ):
                with self.assertRaises(ValueError):
                    download("https://mirror.invalid/model", target, "0" * 64, 4)
            self.assertEqual(partial.read_bytes(), b"ab")

    def test_corrupt_bytes_never_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            with patch("urllib.request.urlopen", return_value=Response(b"evil")):
                with self.assertRaises(ValueError):
                    download(
                        "https://mirror.invalid/model",
                        target,
                        hashlib.sha256(b"good").hexdigest(),
                        4,
                    )
            self.assertFalse(target.exists())

    def test_existing_wrong_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            target.write_bytes(b"old")
            with self.assertRaises(ValueError):
                download("https://mirror.invalid/model", target, "0" * 64)
            self.assertEqual(target.read_bytes(), b"old")


class RangeTransferTests(unittest.TestCase):
    def test_range_chunks_assemble_in_byte_order(self):
        def response(request, **kwargs):
            value = request.get_header("Range")
            start, end = map(int, value.removeprefix("bytes=").split("-"))
            return Response(b"abcdef"[start:end + 1], 206,
                            {"Content-Range": f"bytes {start}-{end}/6"})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            with patch("urllib.request.urlopen", side_effect=response):
                download_ranges("https://mirror.invalid/model", target,
                                hashlib.sha256(b"abcdef").hexdigest(), 6, 3, 2)
            self.assertEqual(target.read_bytes(), b"abcdef")

    def test_ignored_range_is_rejected_without_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            with patch("urllib.request.urlopen", return_value=Response(b"evil", 200)):
                with self.assertRaisesRegex(ValueError, "exact byte range"):
                    download_ranges("https://mirror.invalid/model", target, "0" * 64, 4, 1, 4)
            self.assertFalse(target.exists())

    def test_wrong_assembled_hash_is_never_published(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model"
            with patch("urllib.request.urlopen", return_value=Response(
                    b"evil", 206, {"Content-Range": "bytes 0-3/4"})):
                with self.assertRaisesRegex(ValueError, "integrity"):
                    download_ranges("https://mirror.invalid/model", target, "0" * 64, 4, 1, 4)
            self.assertFalse(target.exists())
            self.assertTrue(target.with_name("model.assembled.part").exists())


class PublicModelTests(unittest.TestCase):
    def test_wrong_same_name_does_not_hide_valid_later_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in [("old", b"evil"), ("new", b"good")]:
                (root / name).mkdir()
                (root / name / "model.safetensors").write_bytes(content)
            item = {"path": "vae/model.safetensors", "bytes": 4,
                    "sha256": hashlib.sha256(b"good").hexdigest()}
            candidates = public_candidates(
                os.pathsep.join(str(root / name) for name in ("old", "new")),
                {"model.safetensors"},
            )
            self.assertEqual(select_public(item, candidates), root / "new/model.safetensors")

    def test_alias_still_requires_exact_locked_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "model-v2.safetensors"
            alias.write_bytes(b"evil")
            item = {"path": "vae/model.safetensors", "public_aliases": [alias.name],
                    "bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
            candidates = public_candidates(directory, {alias.name})
            self.assertIsNone(select_public(item, candidates))
            alias.write_bytes(b"good")
            self.assertEqual(select_public(item, candidates), alias)


class ArchiveTests(unittest.TestCase):
    def make_archive(self, path, name):
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            member.size = 2
            archive.addfile(member, io.BytesIO(b"ok"))

    def test_valid_archive_and_existing_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_archive(root / "a.tar.gz", "ComfyUI-abc/file.txt")
            extract_source(root / "a.tar.gz", root / "out", "abc")
            extract_source(root / "a.tar.gz", root / "out", "abc")
            self.assertEqual((root / "out/file.txt").read_bytes(), b"ok")

    def test_traversal_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_archive(root / "a.tar.gz", "ComfyUI-abc/../../outside")
            with self.assertRaises(ValueError):
                extract_source(root / "a.tar.gz", root / "out", "abc")
            self.assertFalse((root / "out").exists())


class ConfigurationTests(unittest.TestCase):
    def test_mirror_rejects_origin_and_credentials(self):
        for endpoint in [
            "http://mirror.invalid",
            "https://huggingface.co",
            "https://user:secret@mirror.invalid",
        ]:
            with self.assertRaises(ValueError):
                mirror_url(endpoint, "file")

    def test_path_environment_is_honored(self):
        with patch.dict(os.environ, {"COMFYUI_DIR": "/cloud/comfy"}):
            self.assertEqual(settings()["COMFYUI_DIR"], "/cloud/comfy")

    def test_all_weights_have_pins(self):
        data = json.loads((ROOT / "config/models.lock.json").read_text())
        self.assertEqual(len(data["models"]), 5)
        self.assertRegex(data["revision"], r"^[a-f0-9]{40}$")
        for model in data["models"]:
            self.assertRegex(model["sha256"], r"^[a-f0-9]{64}$")
            self.assertGreater(model["bytes"], 0)
            self.assertFalse(Path(model["path"]).is_absolute())
            self.assertNotIn("..", Path(model["path"]).parts)


class WorkflowTests(unittest.TestCase):
    def graph(self):
        return json.loads((ROOT / "workflows/h3-depth-ref2va-api.json").read_text())

    def test_patched_model_reaches_sampler(self):
        self.assertEqual(validate_graph(self.graph()), [])

    def test_bypassed_control_is_caught(self):
        graph = self.graph()
        graph["15"]["inputs"]["model"] = ["1", 0]
        self.assertTrue(validate_graph(graph))

    def test_reference_order_mismatch_is_caught(self):
        graph = self.graph()
        graph["13"]["inputs"]["ref_images.ref_image_0"] = ["10", 0]
        self.assertTrue(validate_graph(graph))

    def test_ui_links_are_consistent(self):
        graph = json.loads((ROOT / "workflows/h3-depth-ref2va.json").read_text())
        nodes = {node["id"]: node for node in graph["nodes"]}
        for ident, source, slot, dest, dest_slot, _ in graph["links"]:
            self.assertIn(ident, nodes[source]["outputs"][slot]["links"])
            self.assertEqual(nodes[dest]["inputs"][dest_slot]["link"], ident)

    def test_guard_rejects_slow_or_wrong_size_media(self):
        class Images:
            shape = (124, 576, 1024, 3)

        instance = guard.H3ControlVideoGuard()
        self.assertEqual(instance.check(Images(), 24, 124, 1024, 576)[0].shape, Images.shape)
        with self.assertRaises(ValueError):
            instance.check(Images(), 12, 124, 1024, 576)
        with self.assertRaises(ValueError):
            instance.check(Images(), 24, 124, 1024, 608)
        with self.assertRaises(ValueError):
            instance.check(Images(), 24, 120, 1024, 576)


if __name__ == "__main__":
    unittest.main()
