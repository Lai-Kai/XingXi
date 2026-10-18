import { afterEach, expect, rs, test } from "@rstest/core";

async function createChat(initialPath = "/workspace/chats/new") {
  let pathname = initialPath;
  let params: { thread_id?: string } = {};
  let slot = 0;
  let dirty = false;
  let nextId = 0;
  const slots: unknown[] = [];
  const effects: Array<() => void> = [];
  const listeners = new Map<string, EventListener>();
  const location = { pathname };

  rs.resetModules();
  rs.doMock("next/navigation", () => ({
    useParams: () => params,
    usePathname: () => pathname,
    useSearchParams: () => new URLSearchParams(),
  }));
  rs.doMock("@/core/utils/uuid", () => ({
    uuid: () => `draft-${++nextId}`,
  }));
  rs.doMock("react", () => ({
    useCallback: (callback: unknown) => callback,
    useRef: (initial: unknown) => {
      const index = slot++;
      slots[index] ??= { current: initial };
      return slots[index];
    },
    useState: (initial: unknown) => {
      const index = slot++;
      if (!(index in slots)) {
        slots[index] = typeof initial === "function" ? initial() : initial;
      }
      return [
        slots[index],
        (value: unknown) => {
          if (!Object.is(slots[index], value)) {
            slots[index] = value;
            dirty = true;
          }
        },
      ];
    },
    useEffect: (effect: () => void, deps: unknown[]) => {
      const index = slot++;
      const previous = slots[index] as unknown[] | undefined;
      if (!previous || deps.some((dep, i) => !Object.is(dep, previous[i]))) {
        slots[index] = deps;
        effects.push(effect);
      }
    },
  }));
  rs.stubGlobal("window", {
    location,
    addEventListener: (name: string, listener: EventListener) =>
      listeners.set(name, listener),
    removeEventListener: (name: string) => listeners.delete(name),
  });
  const { useThreadChat: invokeChat, THREAD_CHAT_RESET_EVENT } =
    await import("@/components/workspace/chats/use-thread-chat");

  function render() {
    for (let attempts = 0; attempts < 10; attempts++) {
      slot = 0;
      dirty = false;
      const result = invokeChat();
      effects.splice(0).forEach((effect) => effect());
      if (!dirty) return result;
    }
    throw new Error("Chat state did not settle");
  }

  return {
    render,
    navigate(path: string, nextParams: typeof params = {}) {
      pathname = path;
      location.pathname = path;
      params = nextParams;
    },
    reset(deletedThreadId: string) {
      listeners.get(THREAD_CHAT_RESET_EVENT)?.({
        detail: { deletedThreadId, nextPath: "/workspace/chats/new" },
      } as CustomEvent);
    },
  };
}

afterEach(() => {
  rs.doUnmock("react");
  rs.doUnmock("next/navigation");
  rs.doUnmock("@/core/utils/uuid");
  rs.unstubAllGlobals();
  rs.resetModules();
});

test("keeps the created thread after native history leaves static new-route params empty", async () => {
  const chat = await createChat();
  const draft = chat.render();
  expect(draft.threadId).toBeTruthy();
  expect(draft.isNewThread).toBe(true);

  chat.navigate("/workspace/chats/created-thread");
  draft.setThreadId("created-thread");
  draft.setIsNewThread(false);

  const saved = chat.render();
  expect(saved.threadId).toBe("created-thread");
  expect(saved.isNewThread).toBe(false);
  expect(chat.render().threadId).toBe("created-thread");
});

test("other chat consumers observe the created thread without receiving onStart setters", async () => {
  const chat = await createChat();
  chat.render();
  chat.navigate("/workspace/chats/created-thread");

  expect(chat.render()).toMatchObject({
    threadId: "created-thread",
    isNewThread: false,
  });
});

test("uses the canonical path when the preserved route tree still has new params", async () => {
  const chat = await createChat();
  chat.render();
  chat.navigate("/workspace/chats/created-thread", { thread_id: "new" });

  expect(chat.render()).toMatchObject({
    threadId: "created-thread",
    isNewThread: false,
  });
});

test("direct entry and switching to another saved conversation follow the path", async () => {
  const chat = await createChat("/workspace/chats/first-thread");
  expect(chat.render()).toMatchObject({
    threadId: "first-thread",
    isNewThread: false,
  });
  chat.navigate("/workspace/chats/second-thread", {
    thread_id: "first-thread",
  });
  expect(chat.render()).toMatchObject({
    threadId: "second-thread",
    isNewThread: false,
  });
});

test("returning to new chat creates a fresh draft after the first send", async () => {
  const chat = await createChat();
  const firstDraft = chat.render().threadId;
  chat.navigate("/workspace/chats/created-thread");
  chat.render();
  chat.navigate("/workspace/chats/new");

  const nextDraft = chat.render();
  expect(nextDraft.isNewThread).toBe(true);
  expect(nextDraft.threadId).toBeTruthy();
  expect(nextDraft.threadId).not.toBe(firstDraft);
  expect(nextDraft.threadId).not.toBe("created-thread");
});

test("deleting the active conversation resets its local state before navigation", async () => {
  const chat = await createChat("/workspace/chats/created-thread");
  chat.render();
  chat.reset("created-thread");

  const reset = chat.render();
  expect(reset.isNewThread).toBe(true);
  expect(reset.threadId).toBeTruthy();
  expect(reset.threadId).not.toBe("created-thread");
});
