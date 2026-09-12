import type { GraphEntity, GraphRelation } from "./types";

export type GraphPosition = { x: number; y: number };

export const GRAPH_CENTER: GraphPosition = { x: 520, y: 260 };
const GRAPH_RING_START = 310;
const GRAPH_RING_STEP = 360;
const DISCONNECTED_RING_START = 1_200;
const MAX_NODES_PER_RING = 12;
const NODE_CLEARANCE = 238;
const OVERVIEW_PADDING = 160;
const OVERVIEW_COMPONENT_GAP = 180;
const OVERVIEW_MAX_ROW_WIDTH = 3_200;
const OVERVIEW_COMPONENT_MARGIN = 150;

export type GraphComponent = {
  id: string;
  entityIds: string[];
  relationIds: string[];
};

function stableNoise(value: string): number {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967296;
}

export function connectedGraphComponents(
  entities: GraphEntity[],
  relations: GraphRelation[],
): GraphComponent[] {
  const entityIds = new Set(entities.map((entity) => entity.id));
  const adjacency = new Map<string, Set<string>>();
  const relationIdsByEntity = new Map<string, Set<string>>();
  for (const entity of entities) {
    adjacency.set(entity.id, new Set());
    relationIdsByEntity.set(entity.id, new Set());
  }
  for (const relation of relations) {
    if (
      !entityIds.has(relation.subject_id) ||
      !entityIds.has(relation.object_id)
    ) {
      continue;
    }
    adjacency.get(relation.subject_id)?.add(relation.object_id);
    adjacency.get(relation.object_id)?.add(relation.subject_id);
    relationIdsByEntity.get(relation.subject_id)?.add(relation.id);
    relationIdsByEntity.get(relation.object_id)?.add(relation.id);
  }

  const visited = new Set<string>();
  const components: GraphComponent[] = [];
  for (const entity of [...entities].sort((left, right) =>
    left.id.localeCompare(right.id),
  )) {
    if (visited.has(entity.id)) continue;
    const entityIdsInComponent: string[] = [];
    const queue = [entity.id];
    visited.add(entity.id);
    for (const current of queue) {
      entityIdsInComponent.push(current);
      for (const neighbor of adjacency.get(current) ?? []) {
        if (visited.has(neighbor)) continue;
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
    entityIdsInComponent.sort((left, right) => left.localeCompare(right));
    const relationIdsInComponent = [
      ...new Set(
        entityIdsInComponent.flatMap((entityId) => [
          ...(relationIdsByEntity.get(entityId) ?? []),
        ]),
      ),
    ].sort((left, right) => left.localeCompare(right));
    components.push({
      id: entityIdsInComponent[0]!,
      entityIds: entityIdsInComponent,
      relationIds: relationIdsInComponent,
    });
  }
  return components.sort(
    (left, right) =>
      right.relationIds.length - left.relationIds.length ||
      right.entityIds.length - left.entityIds.length ||
      left.id.localeCompare(right.id),
  );
}

/**
 * Build a deterministic map-like ego graph. Each relationship distance gets
 * one or more spacious rings so a large neighborhood remains navigable at a
 * readable zoom instead of being fit into one crowded viewport.
 */
export function layoutGraphEntities(
  entities: GraphEntity[],
  relations: GraphRelation[],
  focusedEntityId: string | null = null,
): Map<string, GraphPosition> {
  if (!entities.length) return new Map();

  const entityIds = new Set(entities.map((entity) => entity.id));
  const adjacency = new Map<string, Set<string>>();
  for (const entity of entities) adjacency.set(entity.id, new Set());
  for (const relation of relations) {
    if (
      !entityIds.has(relation.subject_id) ||
      !entityIds.has(relation.object_id)
    ) {
      continue;
    }
    adjacency.get(relation.subject_id)?.add(relation.object_id);
    adjacency.get(relation.object_id)?.add(relation.subject_id);
  }

  const centerId =
    focusedEntityId && entityIds.has(focusedEntityId)
      ? focusedEntityId
      : entities[0]!.id;
  const distances = new Map<string, number>([[centerId, 0]]);
  const queue = [centerId];
  for (const current of queue) {
    const nextDistance = distances.get(current)! + 1;
    for (const neighbor of adjacency.get(current) ?? []) {
      if (!distances.has(neighbor)) {
        distances.set(neighbor, nextDistance);
        queue.push(neighbor);
      }
    }
  }

  const maxDistance = Math.max(...distances.values());
  const disconnectedDistance = maxDistance + 1;
  const entitiesByDistance = new Map<number, GraphEntity[]>();
  for (const entity of entities) {
    if (entity.id === centerId) continue;
    const distance = distances.get(entity.id) ?? disconnectedDistance;
    const group = entitiesByDistance.get(distance) ?? [];
    group.push(entity);
    entitiesByDistance.set(distance, group);
  }

  const rings: Array<{ distance: number; entities: GraphEntity[] }> = [];
  for (const distance of [...entitiesByDistance.keys()].sort(
    (left, right) => left - right,
  )) {
    const group = entitiesByDistance.get(distance)!;
    const ordered = [...group].sort(
      (left, right) =>
        stableNoise(`${centerId}:${left.id}:order`) -
          stableNoise(`${centerId}:${right.id}:order`) ||
        left.canonical_name.localeCompare(right.canonical_name),
    );
    for (let index = 0; index < ordered.length; index += MAX_NODES_PER_RING) {
      rings.push({
        distance,
        entities: ordered.slice(index, index + MAX_NODES_PER_RING),
      });
    }
  }

  const positions = new Map<string, GraphPosition>([
    [centerId, { ...GRAPH_CENTER }],
  ]);
  let nextRingStart = GRAPH_RING_START;
  for (const [ringIndex, ring] of rings.entries()) {
    const count = ring.entities.length;
    const chordRadius =
      count > 1 ? NODE_CLEARANCE / (2 * Math.sin(Math.PI / count)) + 36 : 0;
    const distanceRadius =
      ring.distance === disconnectedDistance
        ? DISCONNECTED_RING_START + ringIndex * GRAPH_RING_STEP
        : GRAPH_RING_START + (ring.distance - 1) * GRAPH_RING_STEP;
    const radius = Math.max(nextRingStart, distanceRadius, chordRadius);
    const angleOffset =
      stableNoise(`${centerId}:${ring.distance}:${ringIndex}:angle`) *
      Math.PI *
      2;
    for (const [index, entity] of ring.entities.entries()) {
      const angle = angleOffset + (index / count) * Math.PI * 2;
      positions.set(entity.id, {
        x: GRAPH_CENTER.x + Math.cos(angle) * radius,
        y: GRAPH_CENTER.y + Math.sin(angle) * radius,
      });
    }
    nextRingStart = radius + GRAPH_RING_STEP;
  }

  return positions;
}

export function layoutGraphOverview(
  entities: GraphEntity[],
  relations: GraphRelation[],
): Map<string, GraphPosition> {
  const entityById = new Map(entities.map((entity) => [entity.id, entity]));
  const relationById = new Map(
    relations.map((relation) => [relation.id, relation]),
  );
  const positions = new Map<string, GraphPosition>();
  let cursorX = OVERVIEW_PADDING;
  let cursorY = OVERVIEW_PADDING;
  let rowHeight = 0;

  for (const component of connectedGraphComponents(entities, relations)) {
    const componentEntities = component.entityIds
      .map((entityId) => entityById.get(entityId))
      .filter((entity): entity is GraphEntity => Boolean(entity));
    const componentRelations = component.relationIds
      .map((relationId) => relationById.get(relationId))
      .filter((relation): relation is GraphRelation => Boolean(relation));
    const localPositions = layoutGraphEntities(
      componentEntities,
      componentRelations,
      component.entityIds[0] ?? null,
    );
    if (!localPositions.size) continue;

    const localValues = [...localPositions.values()];
    const minX = Math.min(...localValues.map(({ x }) => x));
    const maxX = Math.max(...localValues.map(({ x }) => x));
    const minY = Math.min(...localValues.map(({ y }) => y));
    const maxY = Math.max(...localValues.map(({ y }) => y));
    const width = maxX - minX + OVERVIEW_COMPONENT_MARGIN * 2;
    const height = maxY - minY + OVERVIEW_COMPONENT_MARGIN * 2;

    if (
      cursorX > OVERVIEW_PADDING &&
      cursorX + width > OVERVIEW_MAX_ROW_WIDTH
    ) {
      cursorX = OVERVIEW_PADDING;
      cursorY += rowHeight + OVERVIEW_COMPONENT_GAP;
      rowHeight = 0;
    }
    for (const [entityId, position] of localPositions) {
      positions.set(entityId, {
        x: cursorX + position.x - minX + OVERVIEW_COMPONENT_MARGIN,
        y: cursorY + position.y - minY + OVERVIEW_COMPONENT_MARGIN,
      });
    }
    cursorX += width + OVERVIEW_COMPONENT_GAP;
    rowHeight = Math.max(rowHeight, height);
  }
  return positions;
}
