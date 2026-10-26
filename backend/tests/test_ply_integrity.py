"""PLY admission validates bytes and scalar values, never reconstruction geometry."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_map_model_assets import setup as setup
from test_map_model_assets import upload

from app.gateway.reconstructions import runner
from app.gateway.reconstructions.model_files import inspect_ply
from app.gateway.reconstructions.ssh import SSHRemote

RGB = [("float", name) for name in ("x", "y", "z")] + [("uchar", name) for name in ("red", "green", "blue")]
GAUSSIAN = [("float", name) for name in ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")]


def document(properties=RGB, *, encoding="ascii", count=1, body=b"0 0 0 255 0 128\n", before="", after=""):
    header = f"ply\nformat {encoding} 1.0\n{before}element vertex {count}\n"
    header += "".join(f"property {kind} {name}\n" for kind, name in properties)
    return (header + after + "end_header\n").encode() + body


def inspect(tmp_path, content):
    path = tmp_path / "model.ply"
    path.write_bytes(content)
    return inspect_ply(path, len(content))


@pytest.mark.parametrize(
    "content",
    [
        document(count=2),
        document(body=b"0 0 0 255 0\n"),
        document(body=b"0 0 0 255 0 128 extra\n"),
        document(body=b"0 0 0 255 0 128\n1 1 1 0 0 0\n"),
        document(body=b"nan 0 0 255 0 128\n"),
        document(body=b"0 -inf 0 255 0 128\n"),
        document(body=b"0 0 1e39 255 0 128\n"),
        document(body=b"0 0 0 256 0 128\n"),
        document(body=b"0 0 0 -1 0 128\n"),
        document(body=b"0 0 0 1.5 0 128\n"),
        document(properties=RGB + [("float", "nx")], body=b"0 0 0 255 0 128 nan\n"),
        document(properties=RGB[:3] + [("float", name) for name in ("red", "green", "blue")], body=b"0 0 0 256 0 128\n"),
        document(properties=RGB + [("float", "alpha")], body=b"0 0 0 255 0 128 -1\n"),
        document(properties=RGB + [("float", "alpha")], body=b"0 0 0 255 0 128 inf\n"),
        document(properties=RGB + [("float", "opacity")], body=b"0 0 0 255 0 128 1\n"),
        document(properties=GAUSSIAN[:-1], body=b" ".join([b"1"] * 13) + b"\n"),
        document(properties=RGB + [("float", "x")], body=b"0 0 0 255 0 128 0\n"),
        document(properties=RGB + [("list uchar int", "indices")], body=b"0 0 0 255 0 128 1 0\n"),
        document(properties=RGB + [("half", "confidence")], body=b"0 0 0 255 0 128 1\n"),
        document(count=-1),
        document(after="element face 1\nproperty list uchar int vertex_indices\n", body=b"0 0 0 255 0 128\n3 0 0\n"),
        document(before="element edge 1\nproperty uchar intensity\n", body=b"256\n0 0 0 255 0 128\n"),
    ],
)
def test_rejects_truncated_malformed_or_unreadable_ascii(tmp_path, content):
    with pytest.raises(ValueError):
        inspect(tmp_path, content)


@pytest.mark.parametrize("encoding,endian", [("binary_little_endian", "<"), ("binary_big_endian", ">")])
@pytest.mark.parametrize("body", [b"short", struct.pack("<fffBBB", float("nan"), 0, 0, 255, 0, 128), struct.pack("<fffBBB", 0, float("inf"), 0, 255, 0, 128)])
def test_binary_rejects_truncation_and_nonfinite_values(tmp_path, encoding, endian, body):
    if len(body) == 15 and endian == ">":
        body = struct.pack(">fffBBB", *struct.unpack("<fffBBB", body))
    with pytest.raises(ValueError):
        inspect(tmp_path, document(encoding=encoding, body=body))


@pytest.mark.parametrize("encoding,endian", [("ascii", None), ("binary_little_endian", "<"), ("binary_big_endian", ">")])
@pytest.mark.parametrize("colors", [("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue"), ("diffuse_r", "diffuse_g", "diffuse_b")])
def test_rgb_alias_alpha_endian_and_original_bytes_are_preserved(tmp_path, encoding, endian, colors):
    properties = RGB[:3] + [("ushort", name) for name in colors] + [("uchar", "alpha")]
    body = b"-1 2 3 65535 32768 0 128\n" if endian is None else struct.pack(endian + "fffHHHB", -1, 2, 3, 65535, 32768, 0, 128)
    content = document(properties, encoding=encoding, body=body)
    digest = hashlib.sha256(content).hexdigest()
    assert inspect(tmp_path, content) == {"format": "ply", "kind": "point_cloud", "point_count": 1}
    assert hashlib.sha256((tmp_path / "model.ply").read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("encoding,endian", [("ascii", None), ("binary_little_endian", "<"), ("binary_big_endian", ">")])
def test_complete_gaussian_schema_accepts_signed_sh_scale_and_opacity(tmp_path, encoding, endian):
    values = [0, 1, 2, -0.5, 0, 0.5, -4, -3, -2, -1, 1, 0, 0, 0]
    body = (" ".join(map(str, values)) + "\n").encode() if endian is None else struct.pack(endian + "f" * len(values), *values)
    assert inspect(tmp_path, document(GAUSSIAN, encoding=encoding, body=body)) == {"format": "ply", "kind": "gaussian", "splat_count": 1}


def test_faces_and_elements_before_vertices_are_parsed_in_declared_order(tmp_path):
    content = document(before="element edge 1\nproperty int value\n", after="element face 1\nproperty list uchar int vertex_indices\n", body=b"5\n0 0 0 255 0 128\n3 0 0 0\n")
    assert inspect(tmp_path, content)["point_count"] == 1


def test_utf8_comment_metadata_does_not_change_rgb_admission(tmp_path):
    assert inspect(tmp_path, document(before="comment 星羲彩色模型\n"))["kind"] == "point_cloud"


def test_binary_face_body_is_checked_without_decoding_it_as_vertices(tmp_path):
    body = struct.pack(">fffBBBBiii", 0, 1, 2, 255, 0, 128, 3, 0, 0, 0)
    content = document(encoding="binary_big_endian", after="element face 1\nproperty list uchar int vertex_indices\n", body=body)
    assert inspect(tmp_path, content)["point_count"] == 1
    with pytest.raises(ValueError):
        inspect(tmp_path, content[:-1])


def test_declared_size_must_match_open_file(tmp_path):
    content = document()
    path = tmp_path / "model.ply"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        inspect_ply(path, len(content) + 1)


@pytest.mark.parametrize("value,valid", [(b"0.5 0 1", True), (b"255 127.5 0", True), (b"-0.5 0 1", False), (b"256 0 1", False)])
def test_float_rgb_supports_normalized_and_byte_ranges(tmp_path, value, valid):
    content = document(RGB[:3] + [("float", name) for name in ("r", "g", "b")], body=b"0 0 0 " + value + b"\n")
    if valid:
        assert inspect(tmp_path, content)["kind"] == "point_cloud"
    else:
        with pytest.raises(ValueError):
            inspect(tmp_path, content)


@pytest.mark.parametrize("kind,values", [("char", b"128 0 0"), ("short", b"32768 0 0"), ("uint", b"4294967296 0 0"), ("int", b"2147483648 0 0")])
def test_ascii_integer_values_must_fit_declared_type(tmp_path, kind, values):
    with pytest.raises(ValueError):
        inspect(tmp_path, document(RGB[:3] + [(kind, name) for name in ("red", "green", "blue")], body=b"0 0 0 " + values + b"\n"))


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [document(count=2), document(body=b"NaN 0 0 255 0 128\n"), document(GAUSSIAN[:-1], body=b" ".join([b"1"] * 13) + b"\n")])
async def test_invalid_ply_http_upload_is_400_and_leaves_no_records_or_files(setup, content):
    client, service, _ = setup
    response = await upload(client, body=content)
    assert response.status_code == 400
    assert await service.store.list() == []
    assert list(service.config.local_root.glob("*/model.*")) == []


def test_binary_validation_reads_in_bounded_blocks(tmp_path, monkeypatch):
    from app.gateway.reconstructions import ply_validation

    count = 150_000
    content = document(count=count, encoding="binary_little_endian", body=struct.pack("<fffBBB", 0, 1, 2, 255, 0, 128) * count)
    sizes = []
    original = ply_validation.Reader.read

    def track(reader, size):
        sizes.append(size)
        return original(reader, size)

    monkeypatch.setattr(ply_validation.Reader, "read", track)
    assert inspect(tmp_path, content)["point_count"] == count
    assert len(sizes) >= 3 and max(sizes) <= 1024 * 1024


def test_runner_applies_same_body_validation_and_preserves_sha(tmp_path):
    project = tmp_path / "projects" / "generated"
    project.mkdir(parents=True)
    path = project / "final.ply"
    path.write_bytes(document(body=b"0 0 0 255 0 128\n"))
    (project / "project.json").write_text(json.dumps({"status": "completed", "output": {"finalPly": str(path)}}))
    assert runner.validate_result(tmp_path)["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(document(count=2))
    with pytest.raises(ValueError):
        runner.validate_result(tmp_path)


def test_new_ssh_job_uploads_validation_helper_before_supervisor(monkeypatch, tmp_path):
    events = []
    remote = SSHRemote(SimpleNamespace(remote_root="/jobs", executable="splatstudio"))

    class Sftp:
        def put(self, source, target):
            events.append(("put", Path(source).name, target))

        def posix_rename(self, source, target):
            events.append(("rename", source, target))

    class Client:
        def exec_command(self, command, **kwargs):
            events.append(("exec", command))
            return None, SimpleNamespace(channel=SimpleNamespace(recv_exit_status=lambda: 0)), None

    @contextmanager
    def connection():
        yield Client(), Sftp()

    monkeypatch.setattr(remote, "connection", connection)
    monkeypatch.setattr(remote, "mkdir", lambda *args: None)
    monkeypatch.setattr(remote, "exists", lambda *args: False)
    monkeypatch.setattr(remote, "write_json", lambda *args: None)
    monkeypatch.setattr(remote, "inspect", lambda job_id: {"status": "running"})
    remote.submit({"id": str(uuid.uuid4()), "files": [], "quality": "balanced", "input_type": "images"}, tmp_path)
    uploaded = [event[1] for event in events if event[0] == "put"]
    assert "ply_validation.py" in uploaded
    assert uploaded.index("ply_validation.py") < uploaded.index("runner.py")
    assert events[-1][0] == "exec"


def test_inspection_of_legacy_job_needs_no_validation_helper(tmp_path):
    standalone = tmp_path / "runner.py"
    shutil.copyfile(Path(runner.__file__), standalone)
    root = tmp_path / "legacy"
    root.mkdir()
    output = subprocess.check_output([sys.executable, str(standalone), "--inspect", str(root)], text=True)
    assert json.loads(output)["status"] == "transferring"


def test_standalone_runner_loads_sibling_helper_without_gateway_packages(tmp_path):
    for name in ("runner.py", "ply_validation.py"):
        shutil.copyfile(Path(runner.__file__).with_name(name), tmp_path / name)
    project = tmp_path / "projects" / "generated"
    project.mkdir(parents=True)
    path = project / "final.ply"
    path.write_bytes(document())
    (project / "project.json").write_text(json.dumps({"status": "completed", "output": {"finalPly": str(path)}}))
    code = "import json,runner; from pathlib import Path; print(json.dumps(runner.validate_result(Path('.'))))"
    output = subprocess.check_output([sys.executable, "-c", code], cwd=tmp_path, text=True)
    assert json.loads(output)["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_remote_modules_use_python38_standard_library_syntax():
    for name in ("runner.py", "ply_validation.py"):
        source = Path(runner.__file__).with_name(name).read_text(encoding="utf-8")
        ast.parse(source, feature_version=(3, 8))
