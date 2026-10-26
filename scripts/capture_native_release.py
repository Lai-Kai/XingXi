"""Capture a private, verifiable public-source baseline without changing Git.

This deliberately records a dirty checkout as a source snapshot, not a clean
commit. Runtime configuration, credentials, databases and build payloads remain
outside the archive. No service is started or stopped.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import uuid


EXCLUDED_PARTS = {
    ".git",
    ".cache",
    ".scratch",
    ".runtime",
    ".deer-flow",
    ".ssh",
    ".venv",
    "venv",
    "node_modules",
    ".pnpm-store",
    "__pycache__",
    ".next",
    ".next-production",
    ".next-releases",
    "test-results",
    "playwright-report",
    "outputs",
    "logs",
    "secrets",
    "credentials",
    ".claude",
    ".omc",
}
PRIVATE_NAMES = {
    "config.yaml",
    "extensions_config.json",
    "mcp_config.json",
    "connection.json",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "known_hosts",
    "authorized_keys",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
PRIVATE_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".ppk",
    ".der",
    ".jks",
    ".keystore",
    ".secret",
    ".secrets",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pid",
    ".log",
    ".pyc",
    ".pyo",
    ".bak",
    ".orig",
    ".rej",
}
PUBLIC_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".css",
    ".scss",
    ".html",
    ".json",
    ".jsonc",
    ".jsonl",
    ".md",
    ".mdx",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".lock",
    ".sh",
    ".bash",
    ".ps1",
    ".bat",
    ".cmd",
    ".sql",
    ".ini",
    ".cfg",
    ".conf",
    ".template",
    ".xml",
    ".csv",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".glb",
    ".gltf",
    ".ply",
    ".pdf",
    ".proto",
    ".graphql",
    ".gitattributes",
    ".gitignore",
    ".dockerignore",
    ".nvmrc",
    ".npmrc",
    ".prettierignore",
    ".editorconfig",
}
PUBLIC_NAMES = {
    "Makefile",
    "Dockerfile",
    "LICENSE",
    "NOTICE",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".nvmrc",
    ".npmrc",
    ".prettierignore",
    ".editorconfig",
    ".env.example",
}
TEXT_SUFFIXES = PUBLIC_SUFFIXES - {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".glb",
    ".pdf",
}
LOCK_FILES = {
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "requirements.txt",
}
BUILD_MANIFESTS = (
    "BUILD_ID",
    "build-manifest.json",
    "app-build-manifest.json",
    "routes-manifest.json",
    "prerender-manifest.json",
    "server/app-paths-manifest.json",
)
PRIVATE_KEY = re.compile(rb"(?m)^-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----\r?$")
KNOWN_TOKEN = re.compile(
    rb"(?<![A-Za-z0-9])(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{28,}|"
    rb"gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})(?![A-Za-z0-9])"
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def safe_relative(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe archive/source path")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError("Unsafe archive/source path")
    if ":" in path.parts[0]:
        raise ValueError("Unsafe archive/source path")
    return path


def reject_symlinks(path):
    """Check the spelling as supplied, before resolve() can hide a link."""
    absolute = Path(os.path.abspath(str(path)))
    for item in (absolute, *absolute.parents):
        if item.is_symlink():
            raise ValueError("Symlink boundary refused: " + str(item))
    return absolute


def excluded_reason(name):
    path = safe_relative(name)
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return "runtime, private or generated directory"
    if path.parts[0] in {"reports", ".agent", ".vscode", ".idea", ".worktrees"}:
        return "local reports or agent state"
    leaf = path.name.lower()
    example_env = leaf == ".env.example" or (
        leaf.startswith(".env.") and leaf.endswith(".example")
    )
    if leaf.startswith(".env") and not example_env:
        return "real environment configuration"
    if leaf in PRIVATE_NAMES or leaf.startswith(
        ("config.yaml.", "id_rsa.", "id_ed25519.")
    ):
        return "private host configuration or key"
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        return "private or runtime file type"
    if not (
        path.name in PUBLIC_NAMES
        or example_env
        or path.suffix.lower() in PUBLIC_SUFFIXES
    ):
        return "outside public-source extension allowlist"
    return None


def scan_public_content(name, data):
    """Fail closed on recognizable secrets; never put matched bytes in errors."""
    if PRIVATE_KEY.search(data):
        raise ValueError("Potential private credential in public source: " + name)
    fixture = "tests" in PurePosixPath(name).parts
    for match in KNOWN_TOKEN.finditer(data):
        token = match.group()
        words = set(token.split(b"-"))
        placeholder = (
            fixture
            and re.fullmatch(rb"sk-[a-z-]+", token)
            and token.count(b"-") >= 4
            and words & {b"test", b"tests", b"fake", b"dummy", b"example", b"testing"}
        )
        if fixture and token == b"AKIA" + b"IOSFODNN7EXAMPLE":
            placeholder = True
        if not placeholder:
            raise ValueError("Potential private credential in public source: " + name)
    # Generic variable names such as password/api_key frequently occur in public
    # tests and examples. Do not mistake their placeholders for live credentials.
    # This bounded detector is not a general-purpose secret classification proof.


def git(root, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, env=env, check=False
    )
    if result.returncode:
        # Git errors may include external URLs or configuration; do not echo them.
        raise ValueError("Git inspection failed: " + args[0])
    return result.stdout


def git_inventory(root):
    top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != root:
        raise ValueError("--root must be the Git checkout root")
    paths = set()
    for args in (
        ("ls-tree", "-r", "--name-only", "-z", "HEAD"),
        ("ls-files", "--cached", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        paths.update(
            os.fsdecode(item) for item in git(root, *args).split(b"\0") if item
        )
    raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    parts = raw.split(b"\0")
    changes = []
    index = 0
    while index < len(parts) and parts[index]:
        item = parts[index]
        entry = {"status": item[:2].decode("ascii"), "path": os.fsdecode(item[3:])}
        if b"R" in item[:2] or b"C" in item[:2]:
            index += 1
            entry["original_path"] = os.fsdecode(parts[index])
        changes.append(entry)
        index += 1
    return {
        "head": git(root, "rev-parse", "HEAD").decode("ascii").strip(),
        "branch": os.fsdecode(git(root, "rev-parse", "--abbrev-ref", "HEAD")).strip(),
        "dirty": bool(changes),
        "status": changes,
    }, sorted(paths)


def read_regular(path, label):
    reject_symlinks(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Only regular public source files are supported: " + label)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("Source changed while being captured: " + label)
        data = stream.read()
        after = os.fstat(stream.fileno())
    if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed while being captured: " + label)
    scan_public_content(label, data)
    return data, bool(before.st_mode & 0o111)


def record(path, archive_name, source_kind):
    data, executable = read_regular(path, archive_name)
    return {
        "path": archive_name,
        "sha256": digest(data),
        "size": len(data),
        "executable": executable,
        "kind": source_kind,
    }, data


def migration_versions(database):
    database = reject_symlinks(database)
    if not database.is_file():
        raise ValueError("Migration metadata database does not exist")
    try:
        with closing(
            sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=3)
        ) as connection:
            values = [
                row[0]
                for row in connection.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num"
                )
            ]
    except sqlite3.Error:
        raise ValueError("Cannot read SQLite Alembic migration metadata") from None
    if not all(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
        for value in values
    ):
        raise ValueError("Unexpected migration version format")
    return values


def write_private(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def make_private_parents(path):
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    reject_symlinks(current)
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)


def capture_release(
    root,
    host_dir=None,
    output=None,
    release_id=None,
    dist_dir=None,
    database=None,
    check=False,
):
    root = reject_symlinks(root).resolve()
    host = reject_symlinks(host_dir).resolve() if host_dir else None
    if host is None and output is None:
        raise ValueError(
            "Supply --host-dir for the private default location, or --output"
        )
    release_id = release_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", release_id):
        raise ValueError("Invalid release ID")
    output = reject_symlinks(
        output if output else host / ".runtime/releases" / release_id
    )
    if output.exists():
        raise ValueError("Release output already exists; choose a new release ID")
    # Never place the archive among files selected by git ls-files.
    if output == root or root in output.parents:
        raise ValueError("Release output must be outside the source checkout")
    git_state, candidates = git_inventory(root)
    manifest = {
        "format_version": 1,
        "release_id": release_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Filtered public working-tree snapshot; not a clean commit or complete runtime backup",
        "excluded_runtime_prerequisites": [
            "Real config.yaml, .env and host connection/authentication secrets (back up privately)",
            "Database contents and model/source assets in private runtime directories (back up separately)",
            "Complete frontend build payload and installed Python/Node dependencies (rebuild from locks)",
            "OS/runtime versions, remote engines, external services and GPU environment",
        ],
        "secret_screening": "Private paths excluded; recognizable provider tokens and private-key blocks rejected; not a complete secret audit",
        "git": git_state,
        "files": [],
        "deleted_files": [],
        "excluded_files": [],
        "dependency_locks": [],
        "build": None,
        "migration_versions": None,
    }
    selected = []
    for name in candidates:
        reason = excluded_reason(name)
        if reason:
            manifest["excluded_files"].append({"path": name, "reason": reason})
            continue
        source = root.joinpath(*safe_relative(name).parts)
        if not source.exists() and not source.is_symlink():
            manifest["deleted_files"].append(name)
            continue
        selected.append((source, "source/" + name, "source"))
    if host:
        for name in ("launch.py", "nginx.conf.template"):
            selected.append((host / name, "native/" + name, "native"))
    if dist_dir:
        build = reject_symlinks(
            dist_dir if Path(dist_dir).is_absolute() else root / dist_dir
        ).resolve()
        try:
            build.relative_to(root / "frontend")
        except ValueError:
            raise ValueError(
                "--dist-dir must be inside this checkout's frontend"
            ) from None
        build_id, _ = read_regular(build / "BUILD_ID", "build/BUILD_ID")
        identifier = build_id.decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
            raise ValueError("Unexpected frontend BUILD_ID")
        manifest["build"] = {
            "directory": build.relative_to(root).as_posix(),
            "build_id": identifier,
            "hashes": [],
        }
        selected.append((build / "BUILD_ID", "build/BUILD_ID", "build-identity"))
        for name in BUILD_MANIFESTS:
            if (build / name).exists():
                data, _ = read_regular(build / name, "build/" + name)
                manifest["build"]["hashes"].append(
                    {"path": name, "sha256": digest(data), "size": len(data)}
                )
    if database:
        manifest["migration_versions"] = migration_versions(database)
    # Preflight all content before creating an output directory. Do not retain
    # the full checkout in memory; bytes are reread and checked when archived.
    for path, name, kind in selected:
        entry, _ = record(path, name, kind)
        manifest["files"].append(entry)
        if kind == "source" and path.name in LOCK_FILES:
            manifest["dependency_locks"].append(
                {"path": name[7:], "sha256": entry["sha256"]}
            )
    if check:
        return {
            "check_only": True,
            "source_files": sum(item["kind"] == "source" for item in manifest["files"]),
            "excluded_files": len(manifest["excluded_files"]),
            "deleted_files": len(manifest["deleted_files"]),
            "bytes": sum(item["size"] for item in manifest["files"]),
            "output": str(output),
        }
    created = False
    try:
        # Parent directories are owner-only when newly created. Existing parent
        # permissions/ownership are not silently rewritten.
        make_private_parents(output.parent)
        reject_symlinks(output.parent)
        output.mkdir(mode=0o700)
        created = True
        archive = output / "source.tar.gz"
        write_private(archive, b"")
        with tarfile.open(archive, "w:gz") as tar:
            for (path, name, kind), expected in zip(selected, manifest["files"]):
                entry, data = record(path, name, kind)
                if entry != expected:
                    raise ValueError("Source changed while being captured: " + name)
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o700 if entry["executable"] else 0o600
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
        # Detect edits made after any earlier file was read, including untracked
        # content (git status alone cannot detect such edits).
        for (path, name, kind), expected in zip(selected, manifest["files"]):
            current, _ = record(path, name, kind)
            if current != expected:
                raise ValueError("Source changed while being captured: " + name)
        if git_inventory(root) != (git_state, candidates):
            raise ValueError("Git checkout changed while being captured; retry")
        if any((root / name).exists() for name in manifest["deleted_files"]):
            raise ValueError("A deleted source file reappeared during capture")
        write_private(
            output / "manifest.json",
            (json.dumps(manifest, ensure_ascii=True, indent=2) + "\n").encode("utf-8"),
        )
        write_private(output / "RESTORE.md", RESTORE.encode("utf-8"))
        checksums = "".join(
            file_digest(output / name) + "  " + name + "\n"
            for name in ("manifest.json", "source.tar.gz", "RESTORE.md")
        )
        write_private(output / "SHA256SUMS", checksums.encode("ascii"))
        result = verify_release(output)
        return dict(result, output=str(output), check_only=False)
    except Exception:
        if created:
            # Only remove the exact, newly-created output; never source files.
            shutil.rmtree(output)
        raise


def verify_release(directory):
    directory = reject_symlinks(directory).resolve()
    checksum_file = directory / "SHA256SUMS"
    reject_symlinks(checksum_file)
    checksum_lines = checksum_file.read_text(encoding="ascii").splitlines()
    checksums = {}
    for line in checksum_lines:
        match = re.fullmatch(
            r"([a-f0-9]{64})  (manifest\.json|source\.tar\.gz|RESTORE\.md)", line
        )
        if not match or match[2] in checksums:
            raise ValueError("Invalid checksum inventory")
        checksums[match[2]] = match[1]
    if set(checksums) != {"manifest.json", "source.tar.gz", "RESTORE.md"}:
        raise ValueError("Incomplete checksum inventory")
    for name, expected in checksums.items():
        path = reject_symlinks(directory / name)
        if not path.is_file() or file_digest(path) != expected:
            raise ValueError("Release checksum mismatch: " + name)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported release manifest version")
    expected = {}
    for entry in manifest["files"]:
        name = entry["path"]
        parts = safe_relative(name).parts
        if (
            parts[0] not in {"source", "native", "build"}
            or len(parts) < 2
            or name in expected
        ):
            raise ValueError("Invalid release file inventory")
        if parts[0] == "source" and excluded_reason("/".join(parts[1:])):
            raise ValueError("Private or generated source included in manifest")
        if parts[0] == "native" and name not in {
            "native/launch.py",
            "native/nginx.conf.template",
        }:
            raise ValueError("Unexpected native host file in manifest")
        if parts[0] == "build" and name != "build/BUILD_ID":
            raise ValueError("Unexpected build payload in manifest")
        if (
            not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
            or type(entry["size"]) is not int
            or entry["size"] < 0
        ):
            raise ValueError("Invalid file hash or size in manifest")
        expected[name] = entry
    for name in manifest["deleted_files"]:
        safe_relative(name)
        if "source/" + name in expected or excluded_reason(name):
            raise ValueError("Invalid deleted-source inventory")
    found = set()
    with tarfile.open(directory / "source.tar.gz", "r:gz") as tar:
        for member in tar:
            name = member.name
            safe_relative(name)
            if (
                not member.isfile()
                or member.issym()
                or member.islnk()
                or name in found
                or name not in expected
            ):
                raise ValueError("Unsafe or unexpected archive member")
            entry = expected[name]
            if member.size != entry["size"]:
                raise ValueError("Archive member size mismatch: " + name)
            stream = tar.extractfile(member)
            data = stream.read()
            if digest(data) != entry["sha256"]:
                raise ValueError("Archive member hash mismatch: " + name)
            scan_public_content(name, data)
            found.add(name)
    if found != set(expected):
        raise ValueError("Archive is missing manifest files")
    return {
        "verified_files": len(found),
        "head": manifest["git"]["head"],
        "dirty": manifest["git"]["dirty"],
        "release_id": manifest["release_id"],
    }


RESTORE = """# Restore a filtered working-tree release\n
1. Run `python scripts/capture_native_release.py --verify /private/release` before
   using the archive. SHA256 checks establish integrity, not authorship; keep the
   receipt in a trusted owner-only location.
2. In a separate NEW checkout of the same repository, check out `git.head` from
   manifest.json. Do not reset, clean, extract over, or delete the live checkout.
3. Review manifest.json's excluded_files and deleted_files. Required runtime
   configuration and credentials must come from the host's private configuration
   backup. The archive intentionally contains no raw git diff, credentials or DB.
4. After verification, extract source.tar.gz into an empty private staging folder.
   It contains only regular source/ files, native/ host sources and optional
   build/BUILD_ID. Overlay source/ onto the NEW checkout. Review deleted_files and
   remove those paths manually only from that NEW checkout. The capture tool does
   not execute deletions or restoration.
5. Install from dependency lockfiles, review the native launcher/nginx template
   separately, restore private configuration, and apply reviewed migrations.
   Build into a fresh release directory and validate before switching services.
   Build hashes/BUILD_ID describe the observed production build; they do not
   package its complete assets, prove source-to-build equivalence, or freeze the
   OS, Python/Node runtimes, model engines, external services or GPU environment.

This snapshot can reconstruct its captured public source including untracked
files. It is NOT a clean commit, full runtime backup or automatic rollback.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--host-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--release-id")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        help="Optional SQLite database; read migration IDs only",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate inputs/content without writing a release",
    )
    parser.add_argument(
        "--verify",
        type=Path,
        metavar="RELEASE",
        help="Verify a previously captured release only",
    )
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_release(args.verify)
        else:
            result = capture_release(
                args.root,
                args.host_dir,
                args.output,
                args.release_id,
                args.dist_dir,
                args.database,
                args.check,
            )
        print(json.dumps(result, ensure_ascii=True))
    except (
        ValueError,
        OSError,
        tarfile.TarError,
        UnicodeError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        # Input values or subprocess stderr are never printed. Controlled messages
        # identify a path/category only; unknown exceptions expose their type.
        message = (
            str(error)
            if isinstance(error, ValueError)
            and not isinstance(error, json.JSONDecodeError)
            else type(error).__name__
        )
        parser.exit(1, "Release capture failed: " + message + "\n")


if __name__ == "__main__":
    main()
