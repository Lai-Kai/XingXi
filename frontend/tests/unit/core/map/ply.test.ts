import { describe, expect, it } from "@rstest/core";

import { inspectPly, parseColoredPly } from "@/core/map/ply";
import { coloredPlyGeometry } from "@/core/map/ply";
import { parseColoredPlyData } from "@/core/map/ply-data";

import {
  coloredPlyFixture,
  gaussianPlyFixture,
} from "../../../fixtures/map-ply";

function ascii(
  properties = "property uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar alpha",
  rows = "0 0 0 255 0 0 255\n1 1 1 0 128 255 128",
) {
  return new TextEncoder().encode(
    `ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\n${properties}\nend_header\n${rows}\n`,
  ).buffer;
}

describe("map PLY formats and colors", () => {
  it("preserves per-vertex sRGB and alpha in linear render attributes", () => {
    const bytes = ascii();
    expect(inspectPly(bytes).kind).toBe("point_cloud");
    const geometry = parseColoredPly(bytes);
    const color = geometry.getAttribute("color");
    expect(color.itemSize).toBe(4);
    expect(color.getX(0)).toBe(1);
    expect(color.getY(0)).toBe(0);
    expect(color.getY(1)).toBeCloseTo(0.21586, 4);
    expect(color.getZ(1)).toBe(1);
    expect(color.getW(1)).toBeCloseTo(128 / 255, 5);
    geometry.dispose();
  });

  it("supports normalized floating RGB and opacity without making colors dark", () => {
    const bytes = ascii(
      "property float r\nproperty float g\nproperty float b\nproperty float alpha",
      "0 0 0 1 0 0 1\n1 1 1 0 0.5 1 0.5",
    );
    const geometry = parseColoredPly(bytes);
    expect(geometry.getAttribute("color").getY(1)).toBeCloseTo(0.21404, 4);
    expect(geometry.getAttribute("color").getW(1)).toBe(0.5);
    geometry.dispose();
  });

  it.each([true, false])(
    "supports binary endian and diffuse colors (little=%s)",
    (little) => {
      const header = new TextEncoder().encode(
        `ply\r\nformat binary_${little ? "little" : "big"}_endian 1.0\r\nelement vertex 1\r\nproperty float x\r\nproperty float y\r\nproperty float z\r\nproperty uchar diffuse_red\r\nproperty uchar diffuse_green\r\nproperty uchar diffuse_blue\r\nend_header\r\n`,
      );
      const bytes = new Uint8Array(header.length + 15);
      bytes.set(header);
      new DataView(bytes.buffer).setFloat32(header.length, 12.5, little);
      bytes.set([255, 128, 0], header.length + 12);
      const geometry = parseColoredPly(bytes.buffer);
      expect(geometry.getAttribute("position").getX(0)).toBe(12.5);
      expect(geometry.getAttribute("color").getY(0)).toBeCloseTo(0.21586, 4);
      expect(geometry.getAttribute("color").getW(0)).toBe(1);
      geometry.dispose();
    },
  );

  it("routes Gaussian files to Spark even when they also carry RGB", () => {
    const gaussian = [
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
    ]
      .map((name) => `property float ${name}`)
      .join("\n");
    expect(inspectPly(ascii(gaussian)).kind).toBe("gaussian");
    expect(
      inspectPly(
        ascii(
          `${gaussian}\nproperty uchar red\nproperty uchar green\nproperty uchar blue`,
        ),
      ).kind,
    ).toBe("gaussian");
  });

  it("rejects partial Gaussian attributes even with RGB", () => {
    expect(() =>
      inspectPly(
        ascii(
          "property uchar red\nproperty uchar green\nproperty uchar blue\nproperty float opacity",
        ),
      ),
    ).toThrow(/Gaussian.*不完整/);
    expect(inspectPly(gaussianPlyFixture().buffer).kind).toBe("gaussian");
  });

  it("samples evenly with bounded typed arrays, preserves colors, and frames the complete bounds", () => {
    const bytes = coloredPlyFixture(100).buffer;
    const full = parseColoredPlyData(bytes),
      light = parseColoredPlyData(bytes, 10);
    expect(light.count).toBe(10);
    expect(light.totalCount).toBe(100);
    expect(light.positions.byteLength + light.colors.byteLength).toBe(
      10 * 7 * 4,
    );
    expect(light.min).toEqual(full.min);
    expect(light.max).toEqual(full.max);
    for (let index = 0; index < 10; index++) {
      expect(
        Array.from(light.positions.subarray(index * 3, index * 3 + 3)),
      ).toEqual(
        Array.from(full.positions.subarray(index * 30, index * 30 + 3)),
      );
      expect(
        Array.from(light.colors.subarray(index * 4, index * 4 + 4)),
      ).toEqual(Array.from(full.colors.subarray(index * 40, index * 40 + 4)));
    }
    const geometry = coloredPlyGeometry(light);
    expect(geometry.getAttribute("position").array).toBe(light.positions);
    expect(geometry.getAttribute("color").array).toBe(light.colors);
    geometry.dispose();
  });

  it("checks unsampled rows as well as sampled rows", () => {
    const bytes = coloredPlyFixture(100),
      offset = bytes.length - 100 * 16;
    new DataView(bytes.buffer).setFloat32(offset + 99 * 16, NaN, true);
    expect(() => parseColoredPlyData(bytes.buffer, 10)).toThrow(/无效/);
  });

  it("rejects undeclared trailing records instead of silently hiding them", () => {
    const bytes = coloredPlyFixture(2),
      extra = new Uint8Array(bytes.length + 1);
    extra.set(bytes);
    expect(() => parseColoredPlyData(extra.buffer)).toThrow(/多于/);
    expect(() =>
      parseColoredPlyData(
        ascii(undefined, "0 0 0 255 0 0 255\n1 1 1 0 0 0 255\n2 2 2 0 0 0 255"),
      ),
    ).toThrow(/多于/);
  });

  it("reads list elements before and after vertices without treating face colors as vertex colors", () => {
    const source =
      "ply\nformat ascii 1.0\ncomment 中文注释\nelement edge 1\nproperty list uchar int endpoints\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n2 0 1\n0 0 0 255 0 0\n1 1 1 0 255 0\n3 0 1 0\n";
    const parsed = parseColoredPlyData(new TextEncoder().encode(source).buffer);
    expect(Array.from(parsed.positions)).toEqual([0, 0, 0, 1, 1, 1]);
    expect(Array.from(parsed.colors)).toEqual([1, 0, 0, 1, 0, 1, 0, 1]);
  });

  it("rejects invalid scalar ranges, floats and coordinates not representable by WebGL", () => {
    expect(() =>
      parseColoredPlyData(
        ascii(undefined, "0 0 0 256 0 0 255\n1 1 1 0 0 0 255"),
      ),
    ).toThrow(/范围/);
    expect(() =>
      parseColoredPlyData(
        ascii(undefined, "1e39 0 0 255 0 0 255\n1 1 1 0 0 0 255"),
      ),
    ).toThrow(/范围/);
    const double = new TextDecoder()
      .decode(ascii())
      .replace("property float x", "property double x")
      .replace("0 0 0 255", "1e39 0 0 255");
    expect(() =>
      parseColoredPlyData(new TextEncoder().encode(double).buffer),
    ).toThrow(/浏览器预览范围/);
  });

  it("reports malformed, colorless and truncated files instead of silently showing a blank canvas", () => {
    expect(() =>
      inspectPly(new TextEncoder().encode("not a ply").buffer),
    ).toThrow();
    expect(() => inspectPly(ascii("", "0 0 0\n1 1 1"))).toThrow(/RGB|Gaussian/);
    expect(() =>
      parseColoredPly(ascii(undefined, "0 0 0 255 0 0 255")),
    ).toThrow();
    expect(() =>
      parseColoredPly(
        ascii(undefined, "0 0 0 255 0 0 255\nNaN 1 1 255 0 0 255"),
      ),
    ).toThrow();
  });
});
