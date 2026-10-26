import type { ColoredPlyData } from "./ply-data";

export type PlyWorkerRequest = {
  id: number;
  bytes: ArrayBuffer;
  maxPoints: number;
};
export type PlyWorkerResponse =
  | { id: number; parsed: ColoredPlyData; error?: never }
  | { id: number; error: string; parsed?: never };
export type PlyWorkerPort = Pick<
  Worker,
  "postMessage" | "terminate" | "onmessage" | "onerror" | "onmessageerror"
>;
let nextId = 0;

/** Ownership of bytes moves to the Worker; cancellation terminates actual CPU work. */
export function parsePlyInWorker(
  bytes: ArrayBuffer,
  maxPoints: number,
  signal: AbortSignal,
  createWorker: () => PlyWorkerPort = () =>
    new Worker(new URL("./ply-worker.ts", import.meta.url), { type: "module" }),
) {
  return new Promise<ColoredPlyData>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("已取消 PLY 解析", "AbortError"));
      return;
    }
    const worker = createWorker(),
      id = ++nextId;
    let settled = false;
    const settle = (failure?: Error, parsed?: ColoredPlyData) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener("abort", abort);
      worker.onmessage = null;
      worker.onerror = null;
      worker.onmessageerror = null;
      worker.terminate();
      if (failure) reject(failure);
      else resolve(parsed!);
    };
    const abort = () =>
      settle(new DOMException("已取消 PLY 解析", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event: MessageEvent<PlyWorkerResponse>) => {
      if (event.data.id !== id) return;
      if (event.data.error !== undefined) settle(new Error(event.data.error));
      else settle(undefined, event.data.parsed);
    };
    worker.onerror = () => settle(new Error("PLY 后台解析失败，请重试预览"));
    worker.onmessageerror = () => settle(new Error("PLY 后台解析结果无法读取"));
    try {
      worker.postMessage({ id, bytes, maxPoints } satisfies PlyWorkerRequest, [
        bytes,
      ]);
    } catch (error) {
      settle(
        error instanceof Error ? error : new Error("无法启动 PLY 后台解析"),
      );
    }
  });
}
