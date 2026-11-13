import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "@rstest/core";

import {
  formatModelAssetSize,
  getPointModelAsset,
  MAP_MODEL_ASSETS,
} from "@/core/map/model-assets";

describe("map model bindings", () => {
  it("ships smaller standalone preview GLBs while retaining original model URLs and sizes", () => {
    for (const asset of MAP_MODEL_ASSETS) {
      expect(asset.previewSrc).toMatch(
        /^\/models\/[a-z-]+\/v1\/preview\.[a-f0-9]{12}\.glb$/,
      );
      const bytes = readFileSync(resolve("public", asset.previewSrc!.slice(1)));
      expect(bytes.byteLength).toBe(asset.previewSizeBytes);
      expect(bytes.byteLength).toBeLessThan(asset.sizeBytes! / 10);
      expect(bytes.readUInt32LE(0)).toBe(0x46546c67);
      expect(bytes.readUInt32LE(8)).toBe(bytes.byteLength);
      expect(asset.previewSrc).toContain(
        createHash("sha256").update(bytes).digest("hex").slice(0, 12),
      );
      expect(asset.src).toContain("/model.");
    }
  });
  it("binds the seven existing models to exact reference point/entity pairs", () => {
    expect(MAP_MODEL_ASSETS).toHaveLength(7);
    expect(new Set(MAP_MODEL_ASSETS.map((asset) => asset.pointId)).size).toBe(
      7,
    );
    for (const asset of MAP_MODEL_ASSETS) {
      expect(
        getPointModelAsset({
          id: asset.pointId,
          entityId: asset.entityId,
          recordKind: "reference",
        })?.id,
      ).toBe(asset.id);
      expect(asset.src).toMatch(
        /^\/models\/[a-z-]+\/v1\/model\.[a-f0-9]{12}\.glb$/,
      );
      expect(asset.provenance).toBe("speculative");
    }
  });

  it("does not assign modern assets to corpus records or mismatched entities", () => {
    const asset = MAP_MODEL_ASSETS[0]!;
    expect(
      getPointModelAsset({
        id: asset.pointId,
        entityId: asset.entityId,
        recordKind: "corpus",
      }),
    ).toBeNull();
    expect(
      getPointModelAsset({
        id: asset.pointId,
        entityId: "other",
        recordKind: "reference",
      }),
    ).toBeNull();
    expect(
      getPointModelAsset({
        id: "historical-copy",
        entityId: asset.entityId,
        recordKind: "reference",
      }),
    ).toBeNull();
    expect(getPointModelAsset(null)).toBeNull();
    expect(
      getPointModelAsset({
        id: "pt-yan-garden",
        entityId: "entity-garden-yan",
        recordKind: "reference",
      }),
    ).toBeNull();
    expect(
      getPointModelAsset({
        id: "pt-lingyan-mountain",
        entityId: "entity-landform-lingyan",
        recordKind: "reference",
      }),
    ).toBeNull();
  });

  it("labels a supplied GLB with its size in mebibytes for the model tab", () => {
    for (const asset of MAP_MODEL_ASSETS) {
      expect(formatModelAssetSize(asset.sizeBytes)).toBe(
        `${(asset.sizeBytes! / (1024 * 1024)).toFixed(1)}MB`,
      );
    }
    expect(formatModelAssetSize(71633044)).toBe("68.3MB");
    expect(formatModelAssetSize(75036744)).toBe("71.6MB");
    expect(formatModelAssetSize(undefined)).toBeNull();
    expect(formatModelAssetSize(Number.NaN)).toBeNull();
    expect(formatModelAssetSize(0)).toBeNull();
  });
});
