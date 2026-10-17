"""Standalone remote supervisor, copied over SFTP. Python 3.8+, standard library only."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def validate_result(root):
    projects = list((root / "projects").glob("*/project.json"))
    if len(projects) != 1:
        raise ValueError("未找到唯一的重建项目记录")
    project = read_json(projects[0])
    if project.get("status") != "completed":
        raise ValueError("OOOSplat 未报告重建完成")
    output = project.get("output") or {}
    path = Path(output.get("finalPly") or projects[0].parent / "final.ply").resolve()
    path.relative_to((root / "projects").resolve())
    size = path.stat().st_size
    if size <= 0 or size > 8 * 1024**3:
        raise ValueError("结果文件大小无效或超过 8 GiB")
    with path.open("rb") as stream:
        header = b""
        while len(header) < 65536:
            line = stream.readline(1024)
            header += line
            if line.strip() == b"end_header":
                break
        if not header.startswith(b"ply\n") and not header.startswith(b"ply\r\n"):
            raise ValueError("结果不是 PLY 文件")
        properties, count, element, encoding = set(), 0, None, None
        if not header.rstrip().endswith(b"end_header"):
            raise ValueError("PLY 文件头不完整")
        for line in header.decode("ascii").splitlines():
            parts = line.split()
            if parts[:1] == ["format"]:
                encoding = parts[1]
            elif parts[:1] == ["element"]:
                element = parts[1]
                if element == "vertex":
                    count = int(parts[2])
            elif parts[:1] == ["property"] and element == "vertex" and len(parts) == 3:
                properties.add(parts[2])
        gaussian = {"opacity", "scale_0", "rot_0"}.issubset(properties)
        rgb = any(set(names).issubset(properties) for names in [("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue"), ("diffuse_r", "diffuse_g", "diffuse_b")])
        if encoding not in {"ascii", "binary_little_endian", "binary_big_endian"} or not {"x", "y", "z"}.issubset(properties) or not (gaussian or rgb):
            raise ValueError("结果缺少有效的 XYZ、Gaussian Splat 或 RGB 属性")
        if count <= 0 or size <= len(header):
            raise ValueError("结果中没有 PLY 点数据")
        digest = hashlib.sha256(header)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"relative_path": str(path.relative_to(root.resolve())), "size": size, "sha256": digest.hexdigest(), "kind": "gaussian" if gaussian else "point_cloud", "splat_count" if gaussian else "point_count": count}


def run(root):
    root = Path(root).resolve()
    # A persistent claim prevents a disconnected SSH request from starting the same job twice.
    try:
        (root / ".started").mkdir()
    except FileExistsError:
        return
    status = root / "status.json"
    if (root / "cancel.request").exists():
        write_json(status, {"status": "cancelled", "stage": "cancelled"})
        return
    config = read_json(root / "config.json")
    try:
        arguments = [config["executable"], "generate", "--projects-root", str(root / "projects"), "--quality", config["quality"], str(root / "source" / config["input"])]
        with (root / "runner.log").open("ab", buffering=0) as log:
            process = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            write_json(status, {"status": "running", "stage": "starting", "pid": process.pid})
            cancelled = False
            while process.poll() is None:
                if (root / "cancel.request").exists():
                    cancelled = True
                    # Only the process group created for this exact job is signalled.
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                time.sleep(1)
            code = process.wait()
        if cancelled:
            write_json(status, {"status": "cancelled", "stage": "cancelled"})
        elif code != 0:
            write_json(status, {"status": "failed", "stage": "failed", "error": "OOOSplat 运行失败，退出码 " + str(code)})
        else:
            artifact = validate_result(root)
            write_json(status, {"status": "completed", "stage": "completed", "artifact": artifact})
    except Exception as error:
        write_json(status, {"status": "failed", "stage": "failed", "error": str(error)[:500]})


if __name__ == "__main__":
    run(sys.argv[1])
