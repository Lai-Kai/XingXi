import { expect, test } from "@rstest/core";

import {
  filterRelationsForScope,
  type GraphScope,
} from "@/core/knowledge-graph/filters";
import type { GraphEntity, GraphRelation } from "@/core/knowledge-graph/types";

const entity = (id: string, entityType: GraphEntity["entity_type"]) => ({
  id,
  entity_type: entityType,
});

const relation = (
  id: string,
  subjectId: string,
  relationType: GraphRelation["relation_type"],
  objectId: string,
) =>
  ({
    id,
    subject_id: subjectId,
    relation_type: relationType,
    object_id: objectId,
  }) as GraphRelation;

const entities = [
  entity("person-li", "person"),
  entity("person-wang", "person"),
  entity("place-mudu", "place"),
  entity("building-garden", "building"),
];

const relations = [
  relation("family", "person-li", "sibling_of", "person-wang"),
  relation("visit", "person-li", "visited", "place-mudu"),
  relation("poem", "person-wang", "composed_at", "building-garden"),
  relation("place-to-building", "place-mudu", "located_in", "building-garden"),
];

test("keeps all grounded relation shapes in the all scope", () => {
  expect(filterRelationsForScope(relations, "all", entities)).toEqual(
    relations,
  );
});

test("limits people scope to direct person-to-person relations", () => {
  expect(
    filterRelationsForScope(relations, "people" satisfies GraphScope, entities),
  ).toEqual([relations[0]]);
});
