import { describe, expect, it, rs } from "@rstest/core";

import { parseColoredPlyData } from "@/core/map/ply-data";
import {
  parsePlyInWorker,
  type PlyWorkerPort,
  type PlyWorkerRequest,
  type PlyWorkerResponse,
} from "@/core/map/ply-worker-client";

import { coloredPlyFixture } from "../../../fixtures/map-ply";

function port() {
  let request!: PlyWorkerRequest;
  const worker: PlyWorkerPort = {
    onmessage: null,
    onerror: null,
    onmessageerror: null,
    terminate: rs.fn(),
    postMessage: rs.fn((value: PlyWorkerRequest) => {
      // Simulate the real transfer ownership contract, including detaching input.
      request = structuredClone(value, { transfer: [value.bytes] });
    }),
  };
  const reply = (response: PlyWorkerResponse) =>
    worker.onmessage?.call(
      worker as Worker,
      { data: response } as MessageEvent,
    );
  return { worker, reply, request: () => request };
}

describe("PLY background parsing lifecycle", () => {
  it("transfers the original input once and settles with correctly parsed arrays", async () => {
    const mock = port(),
      bytes = coloredPlyFixture(20).buffer;
    const result = parsePlyInWorker(
      bytes,
      4,
      new AbortController().signal,
      () => mock.worker,
    );
    expect(bytes.byteLength).toBe(0);
    const request = mock.request();
    expect(request.maxPoints).toBe(4);
    const parsed = parseColoredPlyData(request.bytes, request.maxPoints);
    mock.reply({ id: request.id - 1, error: "stale" });
    expect(mock.worker.terminate).not.toHaveBeenCalled();
    mock.reply({ id: request.id, parsed });
    expect((await result).count).toBe(4);
    expect(mock.worker.terminate).toHaveBeenCalledTimes(1);
    expect(mock.worker.onmessage).toBeNull();
  });

  it("terminates CPU work on cancel and ignores a stale queued response", async () => {
    const mock = port(),
      controller = new AbortController();
    const promise = parsePlyInWorker(
      coloredPlyFixture().buffer,
      4,
      controller.signal,
      () => mock.worker,
    );
    const late = mock.worker.onmessage!;
    controller.abort();
    late.call(
      mock.worker as Worker,
      {
        data: {
          id: mock.request().id,
          parsed: parseColoredPlyData(mock.request().bytes),
        },
      } as MessageEvent,
    );
    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
    expect(mock.worker.terminate).toHaveBeenCalledTimes(1);
  });

  it("does not start an already-cancelled parse", async () => {
    const controller = new AbortController(),
      create = rs.fn();
    controller.abort();
    await expect(
      parsePlyInWorker(
        coloredPlyFixture().buffer,
        4,
        controller.signal,
        create,
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(create).not.toHaveBeenCalled();
  });

  it("releases a failed worker and permits a fresh retry", async () => {
    const first = port();
    const failed = parsePlyInWorker(
      coloredPlyFixture().buffer,
      4,
      new AbortController().signal,
      () => first.worker,
    );
    first.reply({ id: first.request().id, error: "PLY 点数据被截断" });
    await expect(failed).rejects.toThrow("被截断");
    expect(first.worker.terminate).toHaveBeenCalledTimes(1);
    const second = port();
    const retried = parsePlyInWorker(
      coloredPlyFixture().buffer,
      4,
      new AbortController().signal,
      () => second.worker,
    );
    second.reply({
      id: second.request().id,
      parsed: parseColoredPlyData(second.request().bytes, 4),
    });
    expect((await retried).count).toBe(4);
  });
});
