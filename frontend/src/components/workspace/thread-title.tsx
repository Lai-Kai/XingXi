import type { BaseStream } from "@langchain/langgraph-sdk";
import { useEffect } from "react";

import { useI18n } from "@/core/i18n/hooks";
import type { AgentThreadState } from "@/core/threads";

import { useThreadChat } from "./chats";
import { FlipDisplay } from "./flip-display";

export function ThreadTitle({
  threadId,
  thread,
  newThreadTitle,
}: {
  className?: string;
  threadId: string;
  thread: BaseStream<AgentThreadState>;
  newThreadTitle?: string;
}) {
  const { t } = useI18n();
  const { isNewThread } = useThreadChat();
  useEffect(() => {
    let _title = t.pages.untitled;

    if (thread.values?.title) {
      _title = thread.values.title;
    } else if (isNewThread) {
      _title = newThreadTitle ?? t.pages.newChat;
    }
    if (thread.isThreadLoading) {
      document.title = `Loading... - ${t.pages.appName}`;
    } else {
      document.title = `${_title} - ${t.pages.appName}`;
    }
  }, [
    isNewThread,
    newThreadTitle,
    t.pages.newChat,
    t.pages.untitled,
    t.pages.appName,
    thread.isThreadLoading,
    thread.values,
  ]);

  if (!thread.values?.title) {
    return newThreadTitle ? <span>{newThreadTitle}</span> : null;
  }
  return (
    <FlipDisplay uniqueKey={threadId}>
      {thread.values.title ?? "Untitled"}
    </FlipDisplay>
  );
}
