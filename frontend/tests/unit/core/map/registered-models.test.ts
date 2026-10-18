import { describe, expect, it } from "@rstest/core";

import {
  modelsForPoint,
  modelFileUrl,
  type RegisteredMapModel,
} from "@/core/map/registered-models";

const asset: RegisteredMapModel = {
  id: "asset-1",
  point_id: "point-1",
  entity_id: "entity-1",
  title: "三维模型",
  kind: "point_cloud",
  format: "ply",
  size_bytes: 100,
  sha256: "hash",
  source: "upload",
  created_at: "2026-10-17",
  preview_url: "https://untrusted.test/model",
  download_url: "https://untrusted.test/download",
};
describe("registered map model binding", () => {
  it("binds only exact point and entity pairs", () => {
    expect(
      modelsForPoint([asset], { id: "point-1", entityId: "entity-1" }),
    ).toEqual([asset]);
    expect(
      modelsForPoint([asset], { id: "other", entityId: "entity-1" }),
    ).toEqual([]);
    expect(
      modelsForPoint([asset], { id: "point-1", entityId: "other" }),
    ).toEqual([]);
  });
  it("builds authenticated same-service URLs rather than trusting arbitrary record URLs", () => {
    expect(modelFileUrl(asset)).toContain("/api/map/model-assets/asset-1/file");
    expect(modelFileUrl(asset, true)).toContain("/file?download=true");
    expect(modelFileUrl(asset)).not.toContain("untrusted.test");
  });
});
