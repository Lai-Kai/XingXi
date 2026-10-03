import { describe, expect, it } from "@rstest/core";

import { getPointModelAsset, MAP_MODEL_ASSETS } from "@/core/map/model-assets";

describe("map model bindings", () => {
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
});
