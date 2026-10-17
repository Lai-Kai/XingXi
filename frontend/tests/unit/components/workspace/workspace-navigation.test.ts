import { describe, expect, it } from "@rstest/core";

import {
  isWorkspaceRouteActive,
  navigationGroupsForUser,
  workspacePageTitle,
} from "@/components/workspace/workspace-navigation";

describe("workspace navigation", () => {
  it("retains public routes without granting management capabilities", () => {
    const groups = navigationGroupsForUser(null);
    expect(groups.map((group) => group.label)).toEqual([
      "核心研究",
      "时空人文",
      "文献与治理",
    ]);
    const paths = groups.flatMap((group) =>
      group.items.map((item) => item.href),
    );
    expect(paths).toContain("/workspace/scheduled-tasks");
    expect(paths).toContain("/workspace/agent");
    expect(paths).toContain("/workspace/chats");
    expect(paths).not.toContain("/workspace/library");
    expect(paths).not.toContain("/workspace/evaluations");
    expect(paths).not.toContain("/workspace/agents");
  });

  it("matches nested links at path segment boundaries", () => {
    expect(
      isWorkspaceRouteActive(
        "/workspace/projects/project-1",
        "/workspace/projects",
      ),
    ).toBe(true);
    expect(
      isWorkspaceRouteActive("/workspace/chats/thread-1", "/workspace/chats"),
    ).toBe(true);
    expect(
      isWorkspaceRouteActive("/workspace/agents/new", "/workspace/agent"),
    ).toBe(false);
    expect(
      isWorkspaceRouteActive("/workspace/map-extra", "/workspace/map"),
    ).toBe(false);
    expect(isWorkspaceRouteActive("/workspace/map", "/workspace")).toBe(false);
  });

  it("gives mobile headers the correct title on deep links", () => {
    expect(workspacePageTitle("/workspace/scheduled-tasks")).toBe(
      "定时研究任务",
    );
    expect(workspacePageTitle("/workspace/library/document-1")).toBe("文献库");
    expect(workspacePageTitle("/workspace/chats/new")).toBe("最近研究");
  });
});
