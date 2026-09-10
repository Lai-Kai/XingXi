import type { GraphEntity, GraphRelation } from "./types";

export type GraphScope = "all" | "people";

// These relation types describe a relationship between two people. A generic
// related_to edge is included only when both endpoints are people.
export const PERSON_TO_PERSON_RELATION_TYPES = new Set<
  GraphRelation["relation_type"]
>(["related_to", "sibling_of", "spouse_of", "parent_of"]);

type EntityScopeRecord = Pick<GraphEntity, "id" | "entity_type">;

export function filterRelationsForScope(
  relations: GraphRelation[],
  scope: GraphScope,
  entities: ReadonlyArray<EntityScopeRecord>,
): GraphRelation[] {
  if (scope === "all") return relations;

  const personIds = new Set(
    entities
      .filter((entity) => entity.entity_type === "person")
      .map((entity) => entity.id),
  );
  return relations.filter(
    (relation) =>
      PERSON_TO_PERSON_RELATION_TYPES.has(relation.relation_type) &&
      personIds.has(relation.subject_id) &&
      personIds.has(relation.object_id),
  );
}
