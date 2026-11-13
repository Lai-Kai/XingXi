import { afterEach, describe, expect, it, rs } from "@rstest/core";

import {
  createDemandRenderer,
  observeRenderVisibility,
  previewPixelRatio,
} from "@/core/map/demand-render";

afterEach(() => {
  rs.unstubAllGlobals();
});

function clock(render: () => boolean) {
  let next = 0;
  const pending = new Map<number, FrameRequestCallback>(),
    states: string[] = [];
  const loop = createDemandRenderer({
    render,
    requestFrame: (callback) => {
      pending.set(++next, callback);
      return next;
    },
    cancelFrame: (id) => {
      pending.delete(id);
    },
    onState: (state) => states.push(state),
  });
  const tick = () => {
    const entry = pending.entries().next().value!;
    pending.delete(entry[0]);
    entry[1](0);
  };
  return { loop, pending, states, tick };
}

describe("on-demand 3D rendering", () => {
  it("coalesces changes, renders damping to rest, then stops all frame requests", () => {
    let remaining = 2;
    const render = rs.fn(() => remaining-- > 0),
      app = clock(render);
    app.loop.invalidate();
    app.loop.invalidate();
    expect(app.pending.size).toBe(1);
    app.tick();
    app.tick();
    app.tick();
    expect(render).toHaveBeenCalledTimes(3);
    expect(app.pending.size).toBe(0);
    expect(app.states.at(-1)).toBe("idle");
    // Spark calls onDirty asynchronously when sorting finishes: wake from idle.
    app.loop.invalidate();
    app.tick();
    expect(render).toHaveBeenCalledTimes(4);
    expect(app.pending.size).toBe(0);
  });

  it("honors an async update queued during a frame", () => {
    let first = true;
    const app = clock(() => {
      if (first) {
        first = false;
        app.loop.invalidate();
      }
      return false;
    });
    app.loop.invalidate();
    app.tick();
    expect(app.pending.size).toBe(1);
    app.tick();
    expect(app.pending.size).toBe(0);
  });

  it("pauses hidden previews, wakes when visible, and permanently cancels on dispose", () => {
    const render = rs.fn(() => false),
      app = clock(render);
    app.loop.invalidate();
    app.loop.setVisible(false);
    app.loop.invalidate();
    expect(app.pending.size).toBe(0);
    expect(app.states.at(-1)).toBe("hidden");
    app.loop.setVisible(true);
    app.tick();
    expect(render).toHaveBeenCalledTimes(1);
    app.loop.invalidate();
    app.loop.dispose();
    app.loop.dispose();
    app.loop.invalidate();
    app.loop.setVisible(true);
    expect(app.pending.size).toBe(0);
    expect(app.states.at(-1)).toBe("disposed");
  });

  it("watches tab visibility and viewport intersection and releases both observers", () => {
    const document = {
      hidden: false,
      addEventListener: rs.fn(),
      removeEventListener: rs.fn(),
    };
    let change!: IntersectionObserverCallback;
    const disconnect = rs.fn(),
      observe = rs.fn();
    rs.stubGlobal("document", document);
    rs.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: IntersectionObserverCallback) {
          change = callback;
        }
        observe = observe;
        disconnect = disconnect;
      },
    );
    const visible = rs.fn(),
      element = {} as HTMLElement;
    const stop = observeRenderVisibility(element, visible);
    expect(visible).toHaveBeenLastCalledWith(true);
    change(
      [{ isIntersecting: false }] as IntersectionObserverEntry[],
      {} as IntersectionObserver,
    );
    expect(visible).toHaveBeenLastCalledWith(false);
    document.hidden = true;
    change(
      [{ isIntersecting: true }] as IntersectionObserverEntry[],
      {} as IntersectionObserver,
    );
    expect(visible).toHaveBeenLastCalledWith(false);
    stop();
    expect(disconnect).toHaveBeenCalledTimes(1);
    expect(document.removeEventListener).toHaveBeenCalledWith(
      "visibilitychange",
      document.addEventListener.mock.calls[0]![1],
    );
  });

  it("caps lightweight raster load while allowing full fidelity", () => {
    expect(previewPixelRatio(true, 3)).toBe(1.25);
    expect(previewPixelRatio(false, 3)).toBe(2);
    expect(previewPixelRatio(true, 1)).toBe(1);
  });
});
