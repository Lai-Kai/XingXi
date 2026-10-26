export const MAX_PLY_PREVIEW_BYTES = 256 * 1024 ** 2;
export const LIGHT_PLY_POINT_BUDGET = 300_000;
export type PlyKind = "gaussian" | "point_cloud";
export type ColoredPlyData = {
  positions: Float32Array;
  colors: Float32Array;
  count: number;
  totalCount: number;
  min: [number, number, number];
  max: [number, number, number];
};

const scalarTypes: Record<
  string,
  { bytes: number; min: number; max: number; integer: boolean }
> = {};
for (const [aliases, bytes, min, max, integer] of [
  [["char", "int8"], 1, -128, 127, true],
  [["uchar", "uint8"], 1, 0, 255, true],
  [["short", "int16"], 2, -32768, 32767, true],
  [["ushort", "uint16"], 2, 0, 65535, true],
  [["int", "int32"], 4, -2147483648, 2147483647, true],
  [["uint", "uint32"], 4, 0, 4294967295, true],
  [
    ["float", "float32"],
    4,
    -3.4028234663852886e38,
    3.4028234663852886e38,
    false,
  ],
  [["double", "float64"], 8, -Number.MAX_VALUE, Number.MAX_VALUE, false],
] as const) {
  for (const alias of aliases)
    scalarTypes[alias] = { bytes, min, max, integer };
}
type Property = { name: string; type: string; countType?: string };
type Element = { name: string; count: number; properties: Property[] };

/** Header-only dispatch; complete body validation runs off the UI thread. */
export function inspectPly(bytes: ArrayBuffer) {
  if (bytes.byteLength > MAX_PLY_PREVIEW_BYTES)
    throw new Error("PLY 超过浏览器预览上限（256 MiB）");
  const header = new TextDecoder().decode(
    new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 65536)),
  );
  const end = /(?:\r\n|\n|\r)end_header(?:\r\n|\n|\r)/.exec(header);
  if (!/^ply(?:\r\n|\n|\r)/.test(header) || !end)
    throw new Error("无法读取 PLY 文件头");
  const elements: Element[] = [];
  let element: Element | undefined,
    format = "";
  for (const line of header.slice(0, end.index).split(/\r\n|\r|\n/)) {
    const p = line.trim().split(/\s+/);
    if (p[0] === "format") {
      format = p[1] ?? "";
      if (p[2] !== "1.0") throw new Error("不支持此 PLY 版本");
    }
    if (p[0] === "element") {
      const count = Number(p[2]);
      if (!Number.isSafeInteger(count) || count < 0)
        throw new Error("PLY 元素数量无效");
      element = { name: p[1]!, count, properties: [] };
      elements.push(element);
    }
    if (p[0] === "property") {
      if (!element) throw new Error("PLY 属性缺少元素");
      const property =
        p[1] === "list"
          ? { name: p[4]!, type: p[3]!, countType: p[2]! }
          : { name: p[2]!, type: p[1]! };
      if (
        !scalarTypes[property.type] ||
        (property.countType && !scalarTypes[property.countType]?.integer) ||
        !property.name ||
        element.properties.some((item) => item.name === property.name)
      )
        throw new Error("PLY 属性类型或名称无效");
      element.properties.push(property);
    }
  }
  const vertices = elements.filter((item) => item.name === "vertex");
  const vertex = vertices[0];
  const properties = Object.fromEntries(
    vertex?.properties.map((p) => [p.name, p.type]) ?? [],
  );
  if (
    !["ascii", "binary_little_endian", "binary_big_endian"].includes(format) ||
    vertices.length !== 1 ||
    !vertex?.count ||
    vertex.properties.some((p) => p.countType) ||
    !["x", "y", "z"].every((key) => key in properties)
  )
    throw new Error("PLY 缺少有效的 XYZ 点数据");
  if (vertex.count > 5_000_000)
    throw new Error("点数超过浏览器预览上限（500 万），请使用桌面查看器");
  const required = [
    "f_dc_0",
    "f_dc_1",
    "f_dc_2",
    "opacity",
    "scale_0",
    "scale_1",
    "scale_2",
    "rot_0",
    "rot_1",
    "rot_2",
    "rot_3",
  ];
  const gaussian = required.every((key) => key in properties);
  if (
    !gaussian &&
    Object.keys(properties).some((key) =>
      /^(opacity|scale_\d+|rot_\d+|f_dc_\d+|f_rest_\d+)$/.test(key),
    )
  )
    throw new Error("Gaussian PLY 属性不完整");
  const colors = [
    ["red", "green", "blue"],
    ["r", "g", "b"],
    ["diffuse_red", "diffuse_green", "diffuse_blue"],
    ["diffuse_r", "diffuse_g", "diffuse_b"],
  ].find((keys) => keys.every((key) => key in properties));
  if (!gaussian && !colors)
    throw new Error("PLY 缺少 RGB 颜色或 Gaussian 属性");
  const bodyOffset = new TextEncoder().encode(
    header.slice(0, end.index + end[0].length),
  ).byteLength;
  return {
    kind: (gaussian ? "gaussian" : "point_cloud") as PlyKind,
    count: vertex.count,
    properties,
    colors,
    alpha: ["alpha", "a", "diffuse_alpha"].find((key) => key in properties),
    elements,
    format,
    bodyOffset,
  };
}

/** Sequential parser: no text split, all-point Geometry, or duplicate color array. */
export function parseColoredPlyData(
  bytes: ArrayBuffer,
  maxPoints = 5_000_000,
): ColoredPlyData {
  const info = inspectPly(bytes);
  if (info.kind !== "point_cloud" || !info.colors)
    throw new Error("请使用高斯查看器打开此 PLY");
  if (!Number.isSafeInteger(maxPoints) || maxPoints < 1)
    throw new Error("预览点数预算无效");
  const count = Math.min(info.count, maxPoints);
  const positions = new Float32Array(count * 3),
    colors = new Float32Array(count * 4);
  const min: [number, number, number] = [Infinity, Infinity, Infinity],
    max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  const bytesView = new Uint8Array(bytes),
    view = new DataView(bytes),
    decoder = new TextDecoder();
  let offset = info.bodyOffset,
    selected = 0,
    maxRgb = 0,
    maxAlpha = 0;
  const read = (type: string) => {
    const spec = scalarTypes[type]!;
    let value: number;
    if (info.format === "ascii") {
      while (offset < bytesView.length && bytesView[offset]! <= 32) offset++;
      const start = offset;
      while (offset < bytesView.length && bytesView[offset]! > 32) offset++;
      if (start === offset || offset - start > 128)
        throw new Error("PLY 点数据不完整");
      const token = decoder.decode(bytesView.subarray(start, offset));
      if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(token))
        throw new Error("PLY 含无效数值");
      value = Number(token);
    } else {
      if (offset + spec.bytes > bytes.byteLength)
        throw new Error("PLY 点数据被截断");
      const little = info.format === "binary_little_endian";
      if (spec.integer) {
        if (spec.bytes === 1)
          value = spec.min < 0 ? view.getInt8(offset) : view.getUint8(offset);
        else if (spec.bytes === 2)
          value =
            spec.min < 0
              ? view.getInt16(offset, little)
              : view.getUint16(offset, little);
        else
          value =
            spec.min < 0
              ? view.getInt32(offset, little)
              : view.getUint32(offset, little);
      } else
        value =
          spec.bytes === 4
            ? view.getFloat32(offset, little)
            : view.getFloat64(offset, little);
      offset += spec.bytes;
    }
    if (
      !Number.isFinite(value) ||
      value < spec.min ||
      value > spec.max ||
      (spec.integer && !Number.isInteger(value))
    )
      throw new Error("PLY 含无效或超出类型范围的点数据");
    return value;
  };
  const colorNames = [...info.colors, ...(info.alpha ? [info.alpha] : [])];
  const row = new Float64Array(7);
  const axes = ["x", "y", "z"];
  for (const element of info.elements) {
    for (let index = 0; index < element.count; index++) {
      const vertex = element.name === "vertex";
      const sample =
        vertex &&
        selected < count &&
        index === Math.floor((selected * info.count) / count);
      row[6] = 1;
      for (const property of element.properties) {
        if (property.countType) {
          const length = read(property.countType);
          if (length < 0 || length > bytes.byteLength)
            throw new Error("PLY 列表长度无效");
          for (let item = 0; item < length; item++) read(property.type);
          continue;
        }
        const value = read(property.type);
        if (!vertex) continue;
        const axis = axes.indexOf(property.name);
        if (axis >= 0) {
          if (Math.abs(value) > 3.4028234663852886e38)
            throw new Error("模型坐标超出浏览器预览范围，请下载查看");
          min[axis] = Math.min(min[axis]!, value);
          max[axis] = Math.max(max[axis]!, value);
          if (sample) row[axis] = value;
        }
        const channel = colorNames.indexOf(property.name);
        if (channel >= 0) {
          const spec = scalarTypes[property.type]!;
          if (value < 0 || (!spec.integer && value > 255))
            throw new Error("PLY RGB 或透明度范围无效");
          if (channel < 3) maxRgb = Math.max(maxRgb, value);
          else maxAlpha = Math.max(maxAlpha, value);
          if (sample) row[channel + 3] = value;
        }
      }
      if (sample) {
        positions.set(row.subarray(0, 3), selected * 3);
        colors.set(row.subarray(3, 7), selected * 4);
        selected++;
      }
    }
  }
  if (info.format === "ascii") {
    while (offset < bytesView.length && bytesView[offset]! <= 32) offset++;
  }
  if (offset !== bytesView.length)
    throw new Error("PLY 数据多于声明的元素数量");
  const divisors = colorNames.map((name, channel) => {
    const type = scalarTypes[info.properties[name]!]!;
    return type.integer
      ? type.max
      : (channel < 3 ? maxRgb : maxAlpha) > 1
        ? 255
        : 1;
  });
  const toLinear = (value: number) =>
    value < 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  for (let index = 0; index < count; index++) {
    for (let channel = 0; channel < 3; channel++)
      colors[index * 4 + channel] = toLinear(
        colors[index * 4 + channel]! / divisors[channel]!,
      );
    if (info.alpha)
      colors[index * 4 + 3] = colors[index * 4 + 3]! / divisors[3]!;
  }
  return { positions, colors, count, totalCount: info.count, min, max };
}
