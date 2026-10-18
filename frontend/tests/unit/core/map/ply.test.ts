import { describe, expect, it } from "@rstest/core";

import { inspectPly, parseColoredPly } from "@/core/map/ply";

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
    expect(
      inspectPly(
        ascii(
          "property float opacity\nproperty float scale_0\nproperty float rot_0",
        ),
      ).kind,
    ).toBe("gaussian");
    expect(
      inspectPly(
        ascii(
          "property float opacity\nproperty float scale_0\nproperty float rot_0\nproperty uchar red\nproperty uchar green\nproperty uchar blue",
        ),
      ).kind,
    ).toBe("gaussian");
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
