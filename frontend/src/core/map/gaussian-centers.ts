import type { PackedSplats } from "@sparkjsdev/spark";
import { Color } from "three";

/** Read every native center without mutating Spark's reused unpacking objects. */
export async function gaussianCenters(
  packed: Pick<PackedSplats, "numSplats" | "getSplat">,
  signal: AbortSignal,
) {
  signal.throwIfAborted();
  const positions = new Float32Array(packed.numSplats * 3);
  const colors = new Float32Array(packed.numSplats * 3);
  const linear = new Color();
  for (let start = 0; start < packed.numSplats; start += 8192) {
    signal.throwIfAborted();
    const end = Math.min(start + 8192, packed.numSplats);
    for (let index = start; index < end; index++) {
      const { center, color } = packed.getSplat(index);
      if (![center.x, center.y, center.z].every(Number.isFinite))
        throw new Error("模型含无效点坐标，无法显示离散点。");
      center.toArray(positions, index * 3);
      linear
        .copy(color)
        .convertSRGBToLinear()
        .toArray(colors, index * 3);
    }
    // Large models must yield to input and cancellation between bounded batches.
    if (end < packed.numSplats)
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }
  signal.throwIfAborted();
  return { positions, colors };
}
