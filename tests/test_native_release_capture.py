"""Offline release capture regressions; never touch a real deployment."""

from __future__ import annotations

import hashlib
from contextlib import closing
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/capture_native_release.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("capture_native_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeReleaseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.host = self.base / "host"
        self.host.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Capture test")
        self.git("config", "user.email", "capture@example.invalid")
        self.write("README.md", "original\n")
        self.write("scripts/old.py", "old = True\n")
        self.write("config.yaml", "private: keep outside snapshot\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.write("README.md", "dirty current source\n")
        self.write("scripts/new.py", "new = True\n")
        (self.root / "scripts/old.py").unlink()
        for name in ("launch.py", "nginx.conf.template"):
            (self.host / name).write_text("# public host source\n", encoding="utf-8")
        self.tool = load_tool()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args])

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def capture(self, **kwargs):
        return self.tool.capture_release(self.root, self.host, **kwargs)

    def test_captures_dirty_source_and_preserves_git_and_private_files(self):
        before = self.git("status", "--porcelain=v1", "-z")
        self.write(".cache/runtime.py", "never copy\n")
        self.write(".scratch/draft.md", "never copy\n")
        self.write(".env.example", "TOKEN=\n")
        self.write(".env", "private env contents\n")
        before = self.git("status", "--porcelain=v1", "-z")
        result = self.capture(release_id="test-release")
        output = Path(result["output"])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["git"]["dirty"])
        self.assertEqual(
            manifest["git"]["head"], self.git("rev-parse", "HEAD").decode().strip()
        )
        self.assertEqual(manifest["deleted_files"], ["scripts/old.py"])
        paths = {item["path"] for item in manifest["files"]}
        self.assertIn("source/scripts/new.py", paths)
        self.assertIn("source/.env.example", paths)
        self.assertIn("native/launch.py", paths)
        self.assertNotIn("source/config.yaml", paths)
        excluded = {item["path"] for item in manifest["excluded_files"]}
        self.assertTrue(
            {"config.yaml", ".env", ".cache/runtime.py", ".scratch/draft.md"}
            <= excluded
        )
        self.assertEqual(before, self.git("status", "--porcelain=v1", "-z"))
        self.assertEqual(self.git("diff", "--cached"), b"")
        self.assertEqual(self.tool.verify_release(output)["verified_files"], len(paths))
        if os.name != "nt":
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            for child in output.iterdir():
                self.assertEqual(child.stat().st_mode & 0o777, 0o600)

    def test_check_is_read_only_and_explicit_output_cannot_overwrite(self):
        output = self.base / "specified-release"
        result = self.capture(output=output, check=True)
        self.assertTrue(result["check_only"])
        self.assertFalse(output.exists())
        self.capture(output=output)
        with self.assertRaises(ValueError):
            self.capture(output=output)

    def test_staged_deletions_and_renames_restore_exact_current_source(self):
        self.git("rm", "scripts/old.py")
        self.git("mv", "README.md", "CURRENT.md")
        output = Path(self.capture()["output"])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["deleted_files"], ["README.md", "scripts/old.py"])
        self.assertIn("source/CURRENT.md", {item["path"] for item in manifest["files"]})

    def test_mid_capture_edits_abort_and_remove_only_the_new_archive(self):
        original = self.tool.record
        calls = []

        def changed(path, name, kind):
            result = original(path, name, kind)
            calls.append(name)
            if calls.count(name) == 2 and name == "source/scripts/new.py":
                self.write("README.md", "concurrent edit\n")
            return result

        output = self.base / "incomplete"
        with (
            patch.object(self.tool, "record", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            self.capture(output=output)
        self.assertFalse(output.exists())
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"), "concurrent edit\n"
        )

    def test_secret_in_public_source_fails_without_leaking_value(self):
        secret = "sk-proj-" + "A9b" * 25
        self.write("frontend/src/secret.ts", 'const api_key = "' + secret + '";\n')
        output = self.base / "refused"
        with self.assertRaises(ValueError) as caught:
            self.capture(output=output)
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(output.exists())

    def test_private_key_block_is_rejected_without_dumping_contents(self):
        self.write(
            "scripts/unsafe.py", "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-value\n"
        )
        with self.assertRaises(ValueError) as caught:
            self.capture(check=True)
        self.assertNotIn("private-value", str(caught.exception))

    def test_public_placeholder_config_is_allowed(self):
        self.write(
            "config.example.yaml",
            'api_key: "EXAMPLE_API_KEY"\npassword: "local-dev-secret"\n',
        )
        self.assertTrue(self.capture(check=True)["check_only"])

    def test_hyphenated_fake_key_allowed_only_in_test_fixtures(self):
        self.tool.scan_public_content(
            "source/backend/tests/test_example.py", b"AKIAIOSFODNN7EXAMPLE"
        )
        with self.assertRaises(ValueError):
            self.tool.scan_public_content(
                "source/backend/app/actual.py", b"AKIAIOSFODNN7EXAMPLE"
            )
        value = b"sk-fake-lowercase-key-for-unit-tests-only"
        self.tool.scan_public_content("source/backend/tests/test_example.py", value)
        with self.assertRaises(ValueError):
            self.tool.scan_public_content("source/backend/app/actual.py", value)
        with self.assertRaises(ValueError):
            self.tool.scan_public_content(
                "source/backend/tests/test_example.py", b"sk-" + b"z9AZ" * 12
            )

    def test_tool_can_capture_its_own_public_source(self):
        self.write(
            "scripts/capture_native_release.py",
            Path(self.tool.__file__).read_text(encoding="utf-8"),
        )
        self.assertTrue(self.capture(check=True)["check_only"])

    def test_archive_and_manifest_tampering_are_detected(self):
        output = Path(self.capture()["output"])
        archive = output / "source.tar.gz"
        original = archive.read_bytes()
        archive.write_bytes(original[:-8] + b"tampered")
        with self.assertRaises(ValueError):
            self.tool.verify_release(output)
        archive.write_bytes(original)
        manifest = output / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.tool.verify_release(output)

    def test_archive_traversal_and_links_rejected_even_with_matching_archive_hash(self):
        for name, link in (("../escape.py", False), ("source/link.py", True)):
            with self.subTest(name=name):
                output = Path(self.capture()["output"])
                archive = output / "source.tar.gz"
                with tarfile.open(archive, "w:gz") as tar:
                    item = tarfile.TarInfo(name)
                    if link:
                        item.type = tarfile.SYMTYPE
                        item.linkname = "../../outside"
                        tar.addfile(item)
                    else:
                        item.size = 1
                        tar.addfile(item, io.BytesIO(b"x"))
                self.rewrite_checksums(output)
                with self.assertRaises(ValueError):
                    self.tool.verify_release(output)

    def rewrite_checksums(self, output):
        (output / "SHA256SUMS").write_text(
            "".join(
                hashlib.sha256((output / name).read_bytes()).hexdigest()
                + "  "
                + name
                + "\n"
                for name in ("manifest.json", "source.tar.gz", "RESTORE.md")
            ),
            encoding="ascii",
        )

    def test_optional_build_and_readonly_migration_metadata(self):
        import sqlite3

        build = self.root / "frontend/.next-releases/test"
        build.mkdir(parents=True)
        (build / "BUILD_ID").write_text("build-123\n", encoding="utf-8")
        (build / "build-manifest.json").write_text("{}", encoding="utf-8")
        self.write("frontend/pnpm-lock.yaml", "lockfileVersion: 9\n")
        database = self.base / "runtime.db"
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
            conn.execute(
                "INSERT INTO alembic_version VALUES ('0047_merge_map_reconstruction')"
            )
        original = database.read_bytes()
        output = Path(self.capture(dist_dir=build, database=database)["output"])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["migration_versions"], ["0047_merge_map_reconstruction"]
        )
        self.assertEqual(manifest["build"]["build_id"], "build-123")
        self.assertTrue(manifest["dependency_locks"])
        self.assertEqual(database.read_bytes(), original)
        self.assertFalse(
            any(item["path"].endswith(".db") for item in manifest["files"])
        )

    @unittest.skipIf(os.name == "nt", "Symlink setup requires Unix permissions")
    def test_source_and_output_symlink_boundaries_are_rejected(self):
        outside = self.base / "outside.py"
        outside.write_text("not in repository", encoding="utf-8")
        (self.root / "scripts/link.py").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.capture(check=True)
        (self.root / "scripts/link.py").unlink()
        (self.base / "alias").symlink_to(self.host, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.capture(output=self.base / "alias/release")


if __name__ == "__main__":
    unittest.main()
