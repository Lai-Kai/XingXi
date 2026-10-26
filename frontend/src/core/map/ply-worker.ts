import { parseColoredPlyData } from "./ply-data";
import type { PlyWorkerRequest, PlyWorkerResponse } from "./ply-worker-client";

const scope = self as unknown as {
  onmessage: ((event: MessageEvent<PlyWorkerRequest>) => void) | null;
  postMessage: (message: PlyWorkerResponse, transfer?: Transferable[]) => void;
};
scope.onmessage = ({ data }) => {
  try {
    const parsed = parseColoredPlyData(data.bytes, data.maxPoints);
    scope.postMessage({ id: data.id, parsed }, [
      parsed.positions.buffer,
      parsed.colors.buffer,
    ]);
  } catch (error) {
    scope.postMessage({
      id: data.id,
      error: error instanceof Error ? error.message : "PLY 解析失败",
    });
  }
};
