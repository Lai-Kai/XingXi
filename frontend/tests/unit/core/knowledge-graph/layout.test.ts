import { expect, test } from "@rstest/core";

import {
  connectedGraphComponents,
  layoutGraphEntities,
  layoutGraphOverview,
} from "@/core/knowledge-graph/layout";
import type { GraphEntity, GraphRelation } from "@/core/knowledge-graph/types";

function entity(id: string): GraphEntity {
  return {
    id,
    canonical_name: id,
    entity_type: "person",
    dynasty: null,
    extant_status: null,
    summary: null,
    review_status: "reviewed",
    release_id: null,
    evidence_ids: [],
  };
}

function relation(subject_id: string, object_id: string): GraphRelation {
  return {
    id: `${subject_id}-${object_id}`,
    subject_id,
    object_id,
    relation_type: "related_to",
    start_time: null,
    end_time: null,
    confidence: 1,
    evidence_ids: [],
    is_inferred: false,
    review_status: "reviewed",
    release_id: null,
  };
}

function minimumDistance(positions: Map<string, { x: number; y: number }>) {
  const points = [...positions.values()];
  let minimum = Number.POSITIVE_INFINITY;
  for (let leftIndex = 0; leftIndex < points.length; leftIndex += 1) {
    for (
      let rightIndex = leftIndex + 1;
      rightIndex < points.length;
      rightIndex += 1
    ) {
      minimum = Math.min(
        minimum,
        Math.hypot(
          points[leftIndex]!.x - points[rightIndex]!.x,
          points[leftIndex]!.y - points[rightIndex]!.y,
        ),
      );
    }
  }
  return minimum;
}

test("lays out graph nodes by relationship distance without overlap", () => {
  const positions = layoutGraphEntities(
    [entity("center"), entity("near"), entity("far")],
    [relation("center", "near"), relation("near", "far")],
    "center",
  );

  expect(positions.get("center")).toEqual({ x: 520, y: 260 });
  expect(positions.get("near")).not.toEqual(positions.get("far"));
  expect(
    new Set([...positions.values()].map(({ x, y }) => `${x}:${y}`)).size,
  ).toBe(3);
});

test("keeps disconnected entities visible in a separate layer", () => {
  const positions = layoutGraphEntities(
    [entity("center"), entity("disconnected")],
    [],
    "center",
  );

  expect(positions.has("disconnected")).toBe(true);
  expect(positions.get("disconnected")).not.toEqual({ x: 520, y: 260 });
});

test("keeps a crowded neighborhood sparse enough for map-style navigation", () => {
  const neighbors = Array.from(
    { length: 18 },
    (_, index) => `neighbor-${index}`,
  );
  const positions = layoutGraphEntities(
    ["center", ...neighbors].map(entity),
    neighbors.map((neighbor) => relation("center", neighbor)),
    "center",
  );

  expect(minimumDistance(positions)).toBeGreaterThanOrEqual(225);
});

test("separates disconnected networks into independently discoverable components", () => {
  const entities = ["a", "b", "c", "isolated"].map(entity);
  const relations = [relation("a", "b"), relation("b", "c")];

  expect(connectedGraphComponents(entities, relations)).toEqual([
    {
      id: "a",
      entityIds: ["a", "b", "c"],
      relationIds: ["a-b", "b-c"],
    },
    { id: "isolated", entityIds: ["isolated"], relationIds: [] },
  ]);

  const positions = layoutGraphOverview(entities, relations);
  expect(positions.size).toBe(4);
  expect(positions.get("a")).not.toEqual(positions.get("isolated"));
  expect(positions.get("b")).not.toEqual(positions.get("isolated"));
});
