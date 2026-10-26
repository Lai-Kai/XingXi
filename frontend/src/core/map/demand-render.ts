export type DemandRenderState = "idle" | "rendering" | "hidden" | "disposed";

/** One queued frame; Orbit damping and Spark onDirty can request follow-up frames. */
export function createDemandRenderer({
  render,
  requestFrame = requestAnimationFrame,
  cancelFrame = cancelAnimationFrame,
  onState = () => undefined,
}: {
  render: () => boolean;
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (id: number) => void;
  onState?: (state: DemandRenderState, frames: number) => void;
}) {
  let frame: number | undefined,
    visible = true,
    disposed = false,
    frames = 0;
  const invalidate = () => {
    if (disposed || !visible || frame !== undefined) return;
    onState("rendering", frames);
    frame = requestFrame(() => {
      frame = undefined;
      if (disposed || !visible) return;
      const continuing = render();
      frames++;
      if (continuing) invalidate();
      if (frame === undefined) onState("idle", frames);
      else onState("rendering", frames);
    });
  };
  return {
    invalidate,
    setVisible(this: void, value: boolean) {
      visible = value;
      if (!value) {
        if (frame !== undefined) cancelFrame(frame);
        frame = undefined;
        if (!disposed) onState("hidden", frames);
      } else invalidate();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      if (frame !== undefined) cancelFrame(frame);
      frame = undefined;
      onState("disposed", frames);
    },
  };
}

/** Hidden tabs and off-screen previews stop scheduling frames, and wake on return. */
export function observeRenderVisibility(
  element: HTMLElement,
  setVisible: (value: boolean) => void,
) {
  let intersecting = true;
  const update = () => setVisible(!document.hidden && intersecting);
  const observer =
    typeof IntersectionObserver === "undefined"
      ? null
      : new IntersectionObserver((entries) => {
          intersecting = entries.some((entry) => entry.isIntersecting);
          update();
        });
  observer?.observe(element);
  document.addEventListener("visibilitychange", update);
  update();
  return () => {
    observer?.disconnect();
    document.removeEventListener("visibilitychange", update);
  };
}

export const previewPixelRatio = (light: boolean, deviceRatio: number) =>
  Math.min(Math.max(deviceRatio || 1, 1), light ? 1.25 : 2);

/** Register each resource immediately, including partially initialized viewers. */
export function createRenderResources() {
  const cleanups: Array<() => void> = [];
  let disposed = false;
  return {
    add(cleanup: () => void) {
      cleanups.push(cleanup);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      for (const cleanup of cleanups.splice(0).reverse()) {
        try {
          cleanup();
        } catch {
          /* Continue releasing independent GPU resources. */
        }
      }
    },
  };
}
