import { Box3, BufferAttribute, BufferGeometry, Sphere, Vector3 } from "three";

import { parseColoredPlyData, type ColoredPlyData } from "./ply-data";
export { inspectPly, MAX_PLY_PREVIEW_BYTES, type PlyKind } from "./ply-data";

/** Attach transferred arrays without making another full point-data copy. */
export function coloredPlyGeometry(data: ColoredPlyData) {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(data.positions, 3));
  geometry.setAttribute("color", new BufferAttribute(data.colors, 4));
  geometry.boundingBox = new Box3(
    new Vector3(...data.min),
    new Vector3(...data.max),
  );
  geometry.boundingSphere = geometry.boundingBox.getBoundingSphere(
    new Sphere(),
  );
  return geometry;
}

/** Synchronous compatibility helper for format tests; UI uses the Worker client. */
export function parseColoredPly(bytes: ArrayBuffer) {
  return coloredPlyGeometry(parseColoredPlyData(bytes));
}
