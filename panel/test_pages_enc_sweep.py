"""SYNTHETIC sweep checks in a temp directory. Not a live Pages checkout."""

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path


def load_sweep(repo):
    path = Path("panel/box_publisher/pages_enc.py").resolve()
    spec = importlib.util.spec_from_file_location("pages_enc_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.R = str(repo)
    return mod


class SweepAllowlistTest(unittest.TestCase):
    def test_keeps_new_assets_and_old_panel_and_removes_plaintext(self):
        tmp = tempfile.mkdtemp(prefix="pages-sweep-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        repo = Path(tmp) / "repo"
        outside = Path(tmp) / "outside-secret.txt"
        outside.write_text("do-not-touch", encoding="utf-8")
        files = {
            "index.html": "OLD",
            ".nojekyll": "",
            "data/config.json": '{"ksalt":"public","iter":100000}',
            "data/check.enc.json": '{"v":2}',
            "data/hora_mac.enc.json": '{"v":2}',
            "data/nested/keep.enc.json": '{"v":2}',
            "data/secret-plain.json": '{"password":"not-a-real-secret"}',
            "data/random.txt": "plaintext",
            "data/pic.png": "png",
            "hora.html": "NEW",
            "panel/hora.js": "NEWJS",
            "panel/hora.css": "not-allowed",
            "panel/sub/hora.js": "not-the-runtime",
            "panel/hora_ingest.py": "source",
            "panel/HORA_CONTRACT.md": "doc",
            "panel/test_hora_ingest.py": "test",
            "notes/plain.json": "{}",
            ".git/config": "git",
        }
        for rel, text in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        removed = set(load_sweep(repo).sweep())
        kept = {
            "index.html", ".nojekyll", "data/config.json", "data/check.enc.json",
            "data/hora_mac.enc.json", "data/nested/keep.enc.json", "hora.html", "panel/hora.js",
            ".git/config",
        }
        gone = {
            "data/secret-plain.json", "data/random.txt", "data/pic.png",
            "panel/hora.css", "panel/sub/hora.js", "panel/hora_ingest.py",
            "panel/HORA_CONTRACT.md", "panel/test_hora_ingest.py", "notes/plain.json",
        }
        self.assertEqual(removed, gone)
        for rel in kept:
            self.assertTrue((repo / rel).is_file(), rel)
            self.assertEqual((repo / rel).read_text(encoding="utf-8"), files[rel])
        for rel in gone:
            self.assertFalse((repo / rel).exists(), rel)
        self.assertEqual(outside.read_text(encoding="utf-8"), "do-not-touch")
        self.assertNotIn("hora.html", removed)
        self.assertNotIn("panel/hora.js", removed)


if __name__ == "__main__":
    unittest.main()
