import { describe, expect, it } from "@rstest/core";
import { Color, Quaternion, Vector3 } from "three";

import { gaussianCenters } from "@/core/map/gaussian-centers";

describe("native Gaussian center display", () => {
  it("copies every center and base color without mutating reused decoder objects or filtering opacity", async () => {
    const color = new Color(1, 0.5, 0);
    const shared = {
      center: new Vector3(),
      color,
      scales: new Vector3(1, 1, 1),
      quaternion: new Quaternion(),
      opacity: 0,
    };
    const data = await gaussianCenters(
      {
        numSplats: 2,
        getSplat: (index) => {
          shared.center.set(index, -index, index + 2);
          return shared;
        },
      },
      new AbortController().signal,
    );
    expect(Array.from(data.positions)).toEqual([0, -0, 2, 1, -1, 3]);
    expect(data.colors[0]).toBe(1);
    expect(data.colors[1]).toBeCloseTo(0.214041, 5);
    expect(data.colors[4]).toBeCloseTo(0.214041, 5);
    expect(color.g).toBe(0.5);
    expect(shared.opacity).toBe(0);
  });

  it("yields and stops decoding a large model after cancellation", async () => {
    const controller = new AbortController();
    let read = 0;
    const pending = gaussianCenters(
      {
        numSplats: 9000,
        getSplat: () => {
          read++;
          return {
            center: new Vector3(),
            color: new Color(),
            scales: new Vector3(),
            quaternion: new Quaternion(),
            opacity: 1,
          };
        },
      },
      controller.signal,
    );
    controller.abort();
    await expect(pending).rejects.toThrow();
    expect(read).toBe(8192);
  });

  it("rejects invalid centers instead of presenting a corrupt point view", async () => {
    await expect(
      gaussianCenters(
        {
          numSplats: 1,
          getSplat: () => ({
            center: new Vector3(NaN, 0, 0),
            color: new Color(),
            scales: new Vector3(),
            quaternion: new Quaternion(),
            opacity: 1,
          }),
        },
        new AbortController().signal,
      ),
    ).rejects.toThrow("无效点坐标");
  });
});
