"""Technical file-format handling for uploaded map models; no geometry quality gates."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from fastapi import HTTPException

MAX_MODEL_BYTES = 256 * 1024**2


def inspect_ply(path: Path, size: int) -> dict:
    with path.open("rb") as stream:
        header = bytearray()
        while len(header) < 65536:
            line = stream.readline(1024)
            if not line:
                break
            header.extend(line)
            if line.strip() == b"end_header":
                break
        if not bytes(header).startswith((b"ply\n", b"ply\r\n")) or not header.rstrip().endswith(b"end_header"):
            raise ValueError("PLY 文件头无效")
        element, count, encoding, properties = "", 0, "", {}
        for line in header.decode("utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "format":
                encoding = parts[1]
            elif parts[0] == "element":
                element = parts[1]
                if element == "vertex":
                    count = int(parts[2])
            elif parts[0] == "property" and element == "vertex" and len(parts) == 3:
                properties[parts[2]] = parts[1]
        gaussian = {"opacity", "scale_0", "rot_0"}.issubset(properties)
        colored = any(set(keys).issubset(properties) for keys in [("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue"), ("diffuse_r", "diffuse_g", "diffuse_b")])
        if encoding not in {"ascii", "binary_little_endian", "binary_big_endian"} or not {"x", "y", "z"}.issubset(properties) or not (gaussian or colored):
            raise ValueError("PLY 需要 XYZ 和 RGB 颜色或 Gaussian 属性")
        if count <= 0 or size <= len(header):
            raise ValueError("PLY 没有点数据")
        widths = {"char": 1, "int8": 1, "uchar": 1, "uint8": 1, "short": 2, "int16": 2, "ushort": 2, "uint16": 2, "int": 4, "int32": 4, "uint": 4, "uint32": 4, "float": 4, "float32": 4, "double": 8, "float64": 8}
        if encoding != "ascii" and size < len(header) + count * sum(widths[value] for value in properties.values()):
            raise ValueError("PLY 点数据被截断")
        return {"format": "ply", "kind": "gaussian" if gaussian else "point_cloud", "splat_count" if gaussian else "point_count": count}


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
