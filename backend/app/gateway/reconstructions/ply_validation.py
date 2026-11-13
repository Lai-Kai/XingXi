"""Bounded, read-only PLY format validation shared with the Python 3.8 SSH runner.

This checks declared records and scalar values, never geometry, camera alignment,
visual quality or reconstruction structure. No third-party package is required.
"""

import hashlib
import math
import os
import re
import struct

HEADER_BYTES = 64 * 1024
ROW_BYTES = 1024 * 1024
BLOCK_BYTES = 1024 * 1024
TYPES = {}
for aliases, code, lower, upper in (
    (("char", "int8"), "b", -128, 127),
    (("uchar", "uint8"), "B", 0, 255),
    (("short", "int16"), "h", -32768, 32767),
    (("ushort", "uint16"), "H", 0, 65535),
    (("int", "int32"), "i", -2147483648, 2147483647),
    (("uint", "uint32"), "I", 0, 4294967295),
    (("float", "float32"), "f", -3.4028234663852886e38, 3.4028234663852886e38),
    (("double", "float64"), "d", -1.7976931348623157e308, 1.7976931348623157e308),
):
    for alias in aliases:
        TYPES[alias] = (code, struct.calcsize(code), lower, upper, code in "fd")

RGB_ALIASES = (("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue"), ("diffuse_r", "diffuse_g", "diffuse_b"))
ALPHA_ALIASES = ("alpha", "a", "diffuse_alpha")
GAUSSIAN_PROPERTIES = frozenset(("f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"))
INTEGER = re.compile(rb"[+-]?[0-9]+\Z")
NUMBER = re.compile(rb"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class Reader:
    def __init__(self, stream, size, digest):
        self.stream, self.size, self.position, self.digest = stream, size, 0, digest

    def record(self, block):
        self.position += len(block)
        if self.position > self.size:
            raise ValueError("PLY 文件大小与记录不一致")
        if self.digest is not None:
            self.digest.update(block)
        return block

    def read(self, count):
        # All callers keep even large list properties within a fixed I/O budget.
        if not 0 <= count <= BLOCK_BYTES:
            raise ValueError("PLY 单次读取超过限制")
        block = self.record(self.stream.read(count))
        if len(block) != count:
            raise ValueError("PLY 点数据或附加元素被截断")
        return block

    def line(self, limit):
        block = self.record(self.stream.readline(limit + 1))
        if len(block) > limit:
            raise ValueError("PLY 单行过长")
        return block


def read_header(reader):
    lines, length = [], 0
    while length < HEADER_BYTES:
        line = reader.line(HEADER_BYTES - length)
        if not line:
            break
        length += len(line)
        lines.append(line)
        if line.strip() == b"end_header":
            break
    if not lines or lines[0] not in (b"ply\n", b"ply\r\n") or lines[-1].strip() != b"end_header":
        raise ValueError("PLY 文件头无效或不完整")
    try:
        # Names/types remain explicit PLY tokens; UTF-8 comments are common in
        # uploaded files and were already accepted by the RGB import route.
        text = b"".join(lines).decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("PLY 文件头编码无效") from None
    encoding, elements, current = None, [], None
    for line in text.splitlines()[1:-1]:
        parts = line.split()
        if not parts or parts[0] in ("comment", "obj_info"):
            continue
        if parts[0] == "format" and len(parts) == 3 and encoding is None and not elements:
            encoding = parts[1]
            if parts[2] != "1.0" or encoding not in ("ascii", "binary_little_endian", "binary_big_endian"):
                raise ValueError("PLY 编码或版本无效")
        elif parts[0] == "element" and len(parts) == 3 and encoding is not None:
            if not parts[2].isdigit() or any(element["name"] == parts[1] for element in elements) or len(elements) >= 128:
                raise ValueError("PLY 元素声明无效或重复")
            count = int(parts[2])
            if count > reader.size:
                raise ValueError("PLY 元素数量与文件大小不符")
            current = {"name": parts[1], "count": count, "properties": []}
            elements.append(current)
        elif parts[0] == "property" and current is not None:
            if len(parts) == 3 and parts[1] in TYPES:
                item = (parts[2], parts[1], None)
            elif len(parts) == 5 and parts[1] == "list" and parts[2] in TYPES and parts[3] in TYPES and not TYPES[parts[2]][4]:
                item = (parts[4], parts[3], parts[2])
            else:
                raise ValueError("PLY 属性类型无效")
            if len(current["properties"]) >= 256 or any(prop[0] == item[0] for prop in current["properties"]):
                raise ValueError("PLY 属性过多或名称重复")
            current["properties"].append(item)
        else:
            raise ValueError("PLY 文件头声明无效")
    if not encoding or any(element["count"] and not element["properties"] for element in elements):
        raise ValueError("PLY 元素缺少属性")
    vertices = next((element for element in elements if element["name"] == "vertex"), None)
    if not vertices or vertices["count"] <= 0 or any(prop[2] is not None for prop in vertices["properties"]):
        raise ValueError("PLY 需要有效的标量 vertex 点数据")
    properties = {name: kind for name, kind, _ in vertices["properties"]}
    gaussian = GAUSSIAN_PROPERTIES.issubset(properties)
    gaussian_marker = any(name == "opacity" or name.startswith(("scale_", "rot_", "f_dc_", "f_rest_")) for name in properties)
    if gaussian_marker and not gaussian:
        raise ValueError("PLY Gaussian 属性不完整：需要 f_dc_0..2、opacity、scale_0..2 与 rot_0..3")
    rgb = next((names for names in RGB_ALIASES if set(names).issubset(properties)), None)
    if not {"x", "y", "z"}.issubset(properties) or not (gaussian or rgb):
        raise ValueError("PLY 需要 XYZ 和 RGB 颜色或完整 Gaussian 属性")
    colors = {name for names in RGB_ALIASES for name in names if name in properties}
    colors.update(name for name in ALPHA_ALIASES if name in properties)
    return encoding, elements, vertices["count"], gaussian, colors


def ascii_scalar(token, kind, color=False):
    _, _, lower, upper, floating = TYPES[kind]
    if len(token) > 128 or not (NUMBER if floating else INTEGER).fullmatch(token):
        raise ValueError("PLY 含非数值、非有限或类型不匹配的数据")
    value = float(token) if floating else int(token)
    if not lower <= value <= upper or (floating and not math.isfinite(value)):
        raise ValueError("PLY 数值超出声明类型范围或不是有限数值")
    if color and not 0 <= value <= (255 if floating else upper):
        raise ValueError("PLY RGB 或 Alpha 数值超出可读取范围")
    return value


def validate_ascii(reader, elements, colors):
    for element in elements:
        for _ in range(element["count"]):
            line = reader.line(ROW_BYTES)
            # Blank lines are permitted, but do not satisfy a declared record.
            while line and not line.strip():
                line = reader.line(ROW_BYTES)
            tokens, offset = line.split(), 0
            for name, kind, count_kind in element["properties"]:
                if offset >= len(tokens):
                    raise ValueError("PLY 点数据或附加元素被截断")
                if count_kind is None:
                    ascii_scalar(tokens[offset], kind, element["name"] == "vertex" and name in colors)
                    offset += 1
                else:
                    count = ascii_scalar(tokens[offset], count_kind)
                    offset += 1
                    if count < 0 or count > len(tokens) - offset:
                        raise ValueError("PLY 列表数量无效或数据被截断")
                    for token in tokens[offset : offset + count]:
                        ascii_scalar(token, kind)
                    offset += count
            if offset != len(tokens):
                raise ValueError("PLY 记录列数与属性声明不一致")
    while reader.position < reader.size:
        if reader.read(min(BLOCK_BYTES, reader.size - reader.position)).strip():
            raise ValueError("PLY 数据多于声明的元素数量")


def check_binary_rows(rows, properties, colors):
    floats = [index for index, (_, kind, _) in enumerate(properties) if TYPES[kind][4]]
    color_ranges = [(index, 255 if TYPES[kind][4] else TYPES[kind][3]) for index, (name, kind, _) in enumerate(properties) if name in colors]
    for row in rows:
        if any(not math.isfinite(row[index]) for index in floats):
            raise ValueError("PLY 含 NaN 或 Infinity 点数据")
        if any(not 0 <= row[index] <= upper for index, upper in color_ranges):
            raise ValueError("PLY RGB 或 Alpha 数值超出可读取范围")


def validate_binary(reader, elements, colors, endian):
    for element in elements:
        properties = element["properties"]
        if all(count_kind is None for _, _, count_kind in properties):
            shape = struct.Struct(endian + "".join(TYPES[kind][0] for _, kind, _ in properties))
            remaining = element["count"]
            if remaining * shape.size > reader.size - reader.position:
                raise ValueError("PLY 点数据或附加元素被截断")
            per_block = max(1, BLOCK_BYTES // max(1, shape.size))
            while remaining:
                count = min(remaining, per_block)
                block = reader.read(count * shape.size)
                check_binary_rows(shape.iter_unpack(block), properties, colors if element["name"] == "vertex" else set())
                remaining -= count
        else:
            for _ in range(element["count"]):
                for name, kind, count_kind in properties:
                    shape = struct.Struct(endian + TYPES[kind][0])
                    count = 1
                    if count_kind is not None:
                        count_shape = struct.Struct(endian + TYPES[count_kind][0])
                        count = count_shape.unpack(reader.read(count_shape.size))[0]
                        if count < 0 or count * shape.size > reader.size - reader.position:
                            raise ValueError("PLY 列表数量无效或数据被截断")
                    remaining = count
                    while remaining:
                        take = min(remaining, BLOCK_BYTES // shape.size)
                        check_binary_rows(shape.iter_unpack(reader.read(take * shape.size)), [(name, kind, None)], set())
                        remaining -= take
    if reader.position != reader.size:
        raise ValueError("PLY 数据多于声明的元素数量")


def inspect_ply(path, size, include_digest=False):
    """Validate all declared records in one bounded pass without changing bytes."""
    digest = hashlib.sha256() if include_digest else None
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size != size:
            raise ValueError("PLY 文件大小与记录不一致")
        reader = Reader(stream, size, digest)
        encoding, elements, count, gaussian, colors = read_header(reader)
        if encoding == "ascii":
            validate_ascii(reader, elements, colors)
        else:
            validate_binary(reader, elements, colors, "<" if encoding == "binary_little_endian" else ">")
        # Detect a concurrently growing file as well as a truncated declaration.
        if stream.read(1) or os.fstat(stream.fileno()).st_size != size:
            raise ValueError("PLY 文件在读取期间发生变化")
    result = {"format": "ply", "kind": "gaussian" if gaussian else "point_cloud", "splat_count" if gaussian else "point_count": count}
    if digest is not None:
        result["sha256"] = digest.hexdigest()
    return result
