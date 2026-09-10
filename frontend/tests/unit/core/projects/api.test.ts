import { beforeEach, expect, test, rs } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({
  fetch: rs.fn(),
}));

rs.mock("@/core/config", () => ({
  getBackendBaseURL: () => "/backend",
}));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  createResearchProject,
  getResearchProject,
  listResearchProjects,
  renameResearchProject,
  setResearchProjectArchived,
} from "@/core/projects/api";

const mockedFetch = rs.mocked(fetcher);

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function projectResponse(archived: 0 | 1): Response {
  return jsonResponse({
    id: "project-1",
    name: "木渎古桥研究",
    archived,
    created_at: "2026-08-15T09:00:00+08:00",
    updated_at: "2026-08-15T09:00:00+08:00",
    document_count: 0,
  });
}

beforeEach(() => {
  mockedFetch.mockReset();
});

test("normalizes SQLite archive flags in the project list", async () => {
  mockedFetch.mockResolvedValueOnce(
    jsonResponse([
      {
        id: "project-active",
        name: "木渎古桥研究",
        archived: 0,
        created_at: "2026-08-15T09:00:00+08:00",
        updated_at: "2026-08-15T09:00:00+08:00",
        document_count: 0,
      },
      {
        id: "project-archived",
        name: "吴郡人物研究",
        archived: 1,
        created_at: "2026-08-14T09:00:00+08:00",
        updated_at: "2026-08-14T09:00:00+08:00",
        document_count: 0,
      },
    ]),
  );

  const projects = await listResearchProjects();

  expect(projects.map((project) => project.archived)).toEqual([false, true]);
});

test("normalizes SQLite archive flags in single-project responses", async () => {
  mockedFetch
    .mockResolvedValueOnce(projectResponse(0))
    .mockResolvedValueOnce(projectResponse(0))
    .mockResolvedValueOnce(projectResponse(0))
    .mockResolvedValueOnce(projectResponse(1));

  expect((await createResearchProject("木渎古桥研究")).archived).toBe(false);
  expect((await getResearchProject("project-1")).archived).toBe(false);
  expect(
    (await renameResearchProject("project-1", "木渎古桥沿革研究")).archived,
  ).toBe(false);
  expect((await setResearchProjectArchived("project-1", true)).archived).toBe(
    true,
  );
});
