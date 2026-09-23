import { describe, expect, it, rs } from "@rstest/core";

import { fetchOverview, mergeOverview, overviewPositions, type OverviewPage } from "@/core/knowledge-graph/overview";
import type { GraphEntity, GraphRelation } from "@/core/knowledge-graph/types";

const { fetchMock } = rs.hoisted(() => ({ fetchMock: rs.fn() }));
rs.mock("@/core/api/fetcher", () => ({ fetch: fetchMock }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "" }));

const nodes = ["a", "b", "c", "d", "isolated"].map(id => ({ id, canonical_name: id, entity_type: "person", evidence_ids: ["ev"], review_status: "reviewed" }) as GraphEntity);
const edges = [{ id: "ab", subject_id: "a", object_id: "b" }, { id: "cd", subject_id: "c", object_id: "d" }] as GraphRelation[];
const page = (index: number): OverviewPage => ({ release_id: "r", nodes: nodes.slice(index * 2, index * 2 + 2), edges: [edges[index]!], total_nodes: 4, total_edges: 2, returned_nodes: 2, returned_edges: 1, truncated: index === 0, next_cursor: index === 0 ? "cursor" : null, components: [], evidence: [] });

describe("global graph contract", () => {
  it("merges actual identities, preserves totals and rejects cross-release pages", () => {
    const merged = mergeOverview(page(0), page(1));
    expect(merged.returned_nodes).toBe(4);
    expect(merged.returned_edges).toBe(2);
    expect(merged.total_edges).toBe(2);
    expect(merged.truncated).toBe(false);
    expect(mergeOverview(merged, page(1)).edges).toHaveLength(2);
    expect(() => mergeOverview(page(0), { ...page(1), release_id: "other" })).toThrow("知识版本");
  });
  it("packs every disconnected group without isolated nodes or overlapping positions", () => {
    const positions = overviewPositions(nodes, edges);
    expect([...positions.keys()].sort()).toEqual(["a", "b", "c", "d"]);
    expect(new Set([...positions.values()].map(p => `${p.x}:${p.y}`)).size).toBe(4);
    expect(positions.get("c")!.x - positions.get("b")!.x).toBeGreaterThan(170);
  });
  it("forwards release, cursor and filters and disables shared authorization caching", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => page(0) });
    const signal = new AbortController().signal;
    await fetchOverview({ release_id: "r", cursor: "next", scope: "people", review_status: "pending" }, signal);
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(String(url)).toContain("review_status=pending");
    expect(String(url)).toContain("cursor=next");
    expect(init).toMatchObject({ signal, cache: "no-store", credentials: "include" });
    await fetchOverview({ name: "木渎", entity_type: "place", dynasty: "清" }, signal, true);
    expect(String(fetchMock.mock.calls.at(-1)![0])).toContain("/directory?");
  });
});
