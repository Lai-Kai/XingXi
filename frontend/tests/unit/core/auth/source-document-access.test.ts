import { describe, expect, it } from "@rstest/core";

import { canManageSourceDocuments } from "@/core/auth/permissions";

describe("source document access", () => {
  it("allows only authenticated administrators to manage sources", () => {
    expect(canManageSourceDocuments({ system_role: "admin" })).toBe(true);
    expect(canManageSourceDocuments({ system_role: "user" })).toBe(false);
    expect(canManageSourceDocuments(null)).toBe(false);
    expect(canManageSourceDocuments(undefined)).toBe(false);
  });
});
