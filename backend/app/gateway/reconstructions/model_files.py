"""Technical file-format handling for uploaded map models; no geometry quality gates."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from fastapi import HTTPException

from .ply_validation import inspect_ply

MAX_MODEL_BYTES = 256 * 1024**2


def inspect_glb(path: Path, size: int) -> dict:
    with path.open("rb") as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError("GLB 文件头不完整")
        magic, version, length, chunk_size, chunk_type = struct.unpack("<4sIIII", header)
        if magic != b"glTF" or version != 2 or length != size or chunk_type != 0x4E4F534A or not 0 < chunk_size <= min(size - 20, 16 * 1024**2):
            raise ValueError("需要有效的 GLB 2.0 文件")
        document = json.loads(stream.read(chunk_size))
        if document.get("asset", {}).get("version") != "2.0":
            raise ValueError("需要 GLB 2.0 模型")
        for item in [*document.get("buffers", []), *document.get("images", [])]:
            if item.get("uri") and not str(item["uri"]).startswith("data:"):
                raise ValueError("请使用内嵌贴图与几何数据的 GLB 文件")
    return {"format": "glb", "kind": "mesh"}


def copy_model(stream, directory: Path, filename: str, max_bytes: int) -> dict:
    extension = Path(filename).suffix.lower()
    if extension not in {".ply", ".glb"} or "/" in filename or "\\" in filename or len(filename) > 240 or any(ord(char) < 32 for char in filename):
        raise HTTPException(400, "请选择有效的 PLY 或 GLB 文件名")
    directory.mkdir(parents=True)
    path = directory / ("model" + extension)
    size, digest = 0, hashlib.sha256()
    with path.open("wb") as destination:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > max_bytes:
                raise HTTPException(413, "模型超过上传大小限制（最多 256 MiB）")
            destination.write(block)
            digest.update(block)
    if not size:
        raise HTTPException(400, "不能上传空模型")
    try:
        info = inspect_ply(path, size) if extension == ".ply" else inspect_glb(path, size)
    except (ValueError, IndexError, KeyError, TypeError, AttributeError, UnicodeError, struct.error) as error:
        raise HTTPException(400, str(error)[:240] or "模型文件格式无效") from None
    return {**info, "size": size, "sha256": digest.hexdigest()}
