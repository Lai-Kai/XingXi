import { describe, expect, it } from "@rstest/core";

import { parseEvidenceIds } from "@/core/name-authority/types";

describe("parseEvidenceIds", () => {
  it("accepts Chinese punctuation and removes duplicates", () => {
    expect(parseEvidenceIds("ev-1， ev-2\nev-1,ev-3")).toEqual([
      "ev-1",
      "ev-2",
      "ev-3",
    ]);
  });
});
