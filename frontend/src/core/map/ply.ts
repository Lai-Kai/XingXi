import { Color, Float32BufferAttribute, SRGBColorSpace } from "three";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

export const MAX_PLY_PREVIEW_BYTES = 256 * 1024 ** 2;
export type PlyKind = "gaussian" | "point_cloud";

/** Inspect only vertex properties: face colors do not color a point cloud. */
export function inspectPly(bytes: ArrayBuffer) {
  const header = new TextDecoder().decode(bytes.slice(0, 65536));
  const end = /(?:\r\n|\n|\r)end_header(?:\r\n|\n|\r)/.exec(header);
  if (!/^ply(?:\r\n|\n|\r)/.test(header) || !end)
    throw new Error("无法读取 PLY 文件头");
  const properties: Record<string, string> = {};
  let count = 0,
    element = "",
    format = "";
  for (const line of header.slice(0, end.index).split(/\r\n|\r|\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts[0] === "format") format = parts[1] ?? "";
    if (parts[0] === "element") {
      element = parts[1] ?? "";
      if (element === "vertex") count = Number(parts[2]);
    }
    if (element === "vertex" && parts[0] === "property" && parts.length === 3)
      properties[parts[2]!] = parts[1]!;
  }
  if (
    !["ascii", "binary_little_endian", "binary_big_endian"].includes(format) ||
    !Number.isSafeInteger(count) ||
    count <= 0 ||
    !["x", "y", "z"].every((key) => key in properties)
  )
    throw new Error("PLY 缺少有效的 XYZ 点数据");
  if (count > 5_000_000)
    throw new Error("点数超过浏览器预览上限（500 万），请使用桌面查看器");
  const gaussian = ["opacity", "scale_0", "rot_0"].every(
    (key) => key in properties,
  );
  const colors = [
    ["red", "green", "blue"],
    ["r", "g", "b"],
    ["diffuse_red", "diffuse_green", "diffuse_blue"],
    ["diffuse_r", "diffuse_g", "diffuse_b"],
  ].find((keys) => keys.every((key) => key in properties));
  if (!gaussian && !colors)
    throw new Error("PLY 缺少 RGB 颜色或 Gaussian 属性");
  return {
    kind: (gaussian ? "gaussian" : "point_cloud") as PlyKind,
    count,
    properties,
    colors,
    alpha: ["alpha", "a", "diffuse_alpha"].find((key) => key in properties),
  };
}

function integerDivisor(type: string) {
  if (["uchar", "uint8", "char", "int8"].includes(type)) return 255;
  if (["ushort", "uint16", "short", "int16"].includes(type)) return 65535;
  if (["uint", "uint32", "int", "int32"].includes(type)) return 4294967295;
  return null;
}

/** PLY RGB is sRGB; Three renders in linear space. Keep Alpha independently. */
export function parseColoredPly(bytes: ArrayBuffer) {
  const info = inspectPly(bytes);
  if (info.kind !== "point_cloud" || !info.colors)
    throw new Error("请使用高斯查看器打开此 PLY");
  const loader = new PLYLoader();
  loader.setCustomPropertyNameMapping({
    rawRgb: info.colors,
    ...(info.alpha ? { rawAlpha: [info.alpha] } : {}),
  });
  const geometry = loader.parse(bytes);
  try {
    const positions = geometry.getAttribute("position");
    const rgb = geometry.getAttribute("rawRgb");
    const alpha = geometry.getAttribute("rawAlpha");
    if (positions.count !== info.count || rgb?.count !== info.count)
      throw new Error("PLY 点数据不完整");
    let maxRgb = 0,
      maxAlpha = 0;
    for (let i = 0; i < info.count; i++) {
      const values = [
        positions.getX(i),
        positions.getY(i),
        positions.getZ(i),
        rgb.getX(i),
        rgb.getY(i),
        rgb.getZ(i),
        alpha ? alpha.getX(i) : 1,
      ];
      if (!values.every(Number.isFinite))
        throw new Error("PLY 含无效或截断的点数据");
      maxRgb = Math.max(maxRgb, rgb.getX(i), rgb.getY(i), rgb.getZ(i));
      if (alpha) maxAlpha = Math.max(maxAlpha, alpha.getX(i));
    }
    const divisors = info.colors.map(
      (key) => integerDivisor(info.properties[key]!) ?? (maxRgb > 1 ? 255 : 1),
    );
    const alphaDivisor = info.alpha
      ? (integerDivisor(info.properties[info.alpha]!) ??
        (maxAlpha > 1 ? 255 : 1))
      : 1;
    const rgba = new Float32Array(info.count * 4),
      color = new Color();
    const clamp = (value: number) => Math.min(1, Math.max(0, value));
    for (let i = 0; i < info.count; i++) {
      color.setRGB(
        clamp(rgb.getX(i) / divisors[0]!),
        clamp(rgb.getY(i) / divisors[1]!),
        clamp(rgb.getZ(i) / divisors[2]!),
        SRGBColorSpace,
      );
      rgba.set(
        [
          color.r,
          color.g,
          color.b,
          alpha ? clamp(alpha.getX(i) / alphaDivisor) : 1,
        ],
        i * 4,
      );
    }
    geometry.setIndex(null);
    geometry.deleteAttribute("rawRgb");
    geometry.deleteAttribute("rawAlpha");
    geometry.setAttribute("color", new Float32BufferAttribute(rgba, 4));
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    return geometry;
  } catch (error) {
    geometry.dispose();
    throw error;
  }
}
