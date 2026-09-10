import { describe, expect, it } from "@rstest/core";

import { navigationForUser } from "@/components/workspace/workspace-nav-chat-list";
import {
  businessRoleLabel,
  canManageSourceDocuments,
  hasCapability,
} from "@/core/auth/permissions";
import type { User } from "@/core/auth/types";

function user(
  businessRole: User["business_role"],
  capabilities: User["capabilities"],
): User {
  return {
    id: businessRole,
    email: `${businessRole}@example.com`,
    system_role: "user",
    business_role: businessRole,
    organization_name: null,
    capabilities,
    needs_setup: false,
  };
}

describe("business role access", () => {
  it("gives public visitors a read-only workspace", () => {
    const visitor = user("public", ["knowledge:read", "chat:use", "map:read"]);
    expect(navigationForUser(visitor).map((item) => item.label)).toEqual([
      "文史检索",
      "星羲智能体",
      "古舆地图",
      "古文展签",
      "知识图谱",
      "异名辨析",
      "最近研究",
    ]);
    expect(canManageSourceDocuments(visitor)).toBe(false);
  });

  it("shows role-specific work areas", () => {
    const researcher = user("researcher", ["project:manage"]);
    const institution = user("cultural_institution", ["source:manage"]);
    const studyTeam = user("study_team", ["project:manage", "study-route:use"]);

    expect(
      navigationForUser(researcher).some((item) => item.label === "研究项目"),
    ).toBe(true);
    expect(
      navigationForUser(institution).some((item) => item.label === "文献库"),
    ).toBe(true);
    expect(
      navigationForUser(studyTeam).some((item) => item.label === "研究项目"),
    ).toBe(true);
    expect(canManageSourceDocuments(institution)).toBe(true);
    expect(hasCapability(studyTeam, "study-route:use")).toBe(true);
  });

  it("uses clear Chinese role labels", () => {
    expect(businessRoleLabel("public")).toBe("游客 / 公众");
    expect(businessRoleLabel("cultural_institution")).toBe("文博机构");
    expect(businessRoleLabel("government")).toBe("管理部门");
  });

  it("separates quality queue visibility from review authority", () => {
    const reader = user("government", ["quality:read"]);
    const reviewer = user("government", ["quality:read", "quality:review"]);

    expect(
      navigationForUser(reader).some((item) => item.label === "质量中心"),
    ).toBe(true);
    expect(hasCapability(reader, "quality:review")).toBe(false);
    expect(hasCapability(reviewer, "quality:review")).toBe(true);
    expect(hasCapability(reviewer, "quality:admin")).toBe(false);
  });

  it("keeps every workspace entry for system administrators", () => {
    const admin = { ...user("government", []), system_role: "admin" as const };
    expect(navigationForUser(admin)).toHaveLength(11);
  });
});
