"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { type PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import {
  ChatBox,
  useSpecificChatMode,
  useThreadChat,
} from "@/components/workspace/chats";
import { ExportTrigger } from "@/components/workspace/export-trigger";
import { GoalStatus } from "@/components/workspace/goal-status";
import {
  InputBox,
  type InputBoxSubmitOptions,
} from "@/components/workspace/input-box";
import {
  MessageList,
  MESSAGE_LIST_DEFAULT_PADDING_BOTTOM,
} from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import {
  SidecarProvider,
  SidecarTrigger,
} from "@/components/workspace/sidecar";
import { ThreadScheduledTasksLink } from "@/components/workspace/thread-scheduled-tasks-link";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { TokenUsageIndicator } from "@/components/workspace/token-usage-indicator";
import { useActiveGoal } from "@/components/workspace/use-active-goal";
import { Welcome } from "@/components/workspace/welcome";
import { useI18n } from "@/core/i18n/hooks";
import {
  buildHumanInputResponseText,
  hasOpenHumanInputRequest,
  type HumanInputRequest,
  type HumanInputResponse,
} from "@/core/messages/human-input";
import { isHiddenFromUIMessage } from "@/core/messages/utils";
import { useModels } from "@/core/models/hooks";
import { useNotification } from "@/core/notification/hooks";
import {
  getResearchProject,
  listResearchProjectDocuments,
} from "@/core/projects/api";
import { useLocalSettings, useThreadSettings } from "@/core/settings";
import {
  useBranchThread,
  useThreadMetadata,
  useThreadStream,
  useThreadTokenUsage,
} from "@/core/threads/hooks";
import { threadTokenUsageToTokenUsage } from "@/core/threads/token-usage";
import { textOfMessage } from "@/core/threads/utils";
import {
  dailyTopicContextForEntry,
  parseXingxiChatScope,
} from "@/core/threads/xingxi-entry";
import { env } from "@/env";
import { cn } from "@/lib/utils";

function sameStringArray(left: unknown, right: string[] | undefined) {
  if (left === undefined || right === undefined) {
    return left === right;
  }
  return (
    Array.isArray(left) &&
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

export default function ChatPage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const starterPrompt = searchParams.get("prompt")?.trim();
  const { threadId, setThreadId, isNewThread, setIsNewThread, isMock } =
    useThreadChat();
  const starterProjectId = isNewThread
    ? searchParams.get("project_id")?.trim()
    : undefined;
  // `isNewThread` tracks whether the backend has the thread yet — gates the
  // SDK's history fetch (see issue #2746).  `isWelcomeMode` is the visual
  // welcome layout (centered input, hero, quick actions); we flip it to false
  // the moment the user submits so the UI animates immediately, even though
  // `isNewThread` stays true until the backend actually creates the thread.
  const [isWelcomeMode, setIsWelcomeMode] = useState(isNewThread);
  const [settings, setSettings] = useThreadSettings(threadId);
  const entryTopicContext = useMemo(
    () =>
      isNewThread
        ? dailyTopicContextForEntry(parseXingxiChatScope(searchParams))
        : {},
    [isNewThread, searchParams],
  );
  const [projectScope, setProjectScope] = useState<{
    id: string;
    name: string;
    documentIds: string[];
  } | null>(null);
  const [projectScopeLoading, setProjectScopeLoading] = useState(
    Boolean(starterProjectId),
  );

  useEffect(() => {
    if (!starterProjectId) {
      setProjectScope(null);
      setProjectScopeLoading(false);
      return;
    }
    let active = true;
    setProjectScopeLoading(true);
    void Promise.all([
      getResearchProject(starterProjectId),
      listResearchProjectDocuments(starterProjectId),
    ])
      .then(([project, documents]) => {
        if (!active) return;
        setProjectScope({
          id: project.id,
          name: project.name,
          documentIds: documents.map((document) => document.id),
        });
      })
      .catch(() => {
        if (active) setProjectScope(null);
      })
      .finally(() => {
        if (active) setProjectScopeLoading(false);
      });
    return () => {
      active = false;
    };
  }, [starterProjectId]);
  const projectContextForEntry = useMemo(
    () =>
      isNewThread
        ? {
            research_project_id: projectScope?.id,
            research_project_name: projectScope?.name,
            research_project_document_ids: projectScope?.documentIds,
          }
        : null,
    [isNewThread, projectScope],
  );
  const topicContextForEntry = useMemo(
    () =>
      isNewThread
        ? {
            daily_topic_query: entryTopicContext.daily_topic_query,
            daily_topic_document_ids:
              entryTopicContext.daily_topic_document_ids,
            daily_topic_evidence_ids:
              entryTopicContext.daily_topic_evidence_ids,
            daily_topic_release_id: entryTopicContext.daily_topic_release_id,
          }
        : null,
    [entryTopicContext, isNewThread],
  );
  const runtimeContext = useMemo(
    () => ({
      ...settings.context,
      ...(topicContextForEntry ?? {}),
      ...(projectContextForEntry ?? {}),
    }),
    [projectContextForEntry, settings.context, topicContextForEntry],
  );
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { models, tokenUsageEnabled, isLoading: modelsLoading } = useModels();
  const threadTokenUsage = useThreadTokenUsage(
    isNewThread || isMock ? undefined : threadId,
    { enabled: tokenUsageEnabled && !isMock },
  );
  const threadMetadata = useThreadMetadata(threadId, {
    enabled: !isNewThread && !isMock,
    isMock,
  });
  const branchThread = useBranchThread();
  const backendTokenUsage = threadTokenUsageToTokenUsage(threadTokenUsage.data);
  const [mounted, setMounted] = useState(false);
  const starterSentRef = useRef(false);
  useSpecificChatMode();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Keep welcome layout in sync when navigating between threads (sidebar
  // clicks, "new chat" button).  Submitting in /chats/new flips the layout
  // via onSend below — `isNewThread` stays true until onStart, so this effect
  // is harmless during the submit transition.
  useEffect(() => {
    setIsWelcomeMode(isNewThread);
  }, [isNewThread]);

  const { showNotification } = useNotification();

  const {
    thread,
    pendingUsageMessages,
    sendMessage,
    regenerateMessage,
    isUploading,
    isHistoryLoading,
    hasMoreHistory,
    loadMoreHistory,
  } = useThreadStream({
    threadId: isNewThread ? undefined : threadId,
    displayThreadId: threadId,
    context: runtimeContext,
    isMock,
    // onSend only animates the UI; do NOT flip `isNewThread` here — the
    // LangGraph SDK eagerly fetches /history the moment it receives a
    // thread id and assumes the thread exists on the backend (issue #2746).
    onSend: () => {
      setIsWelcomeMode(false);
    },
    onStart: (createdThreadId) => {
      // ! Important: Never use next.js router for navigation in this case, otherwise it will cause the thread to re-mount and lose all states. Use native history API instead.
      history.replaceState(null, "", `/workspace/chats/${createdThreadId}`);
      setThreadId(createdThreadId);
      setIsNewThread(false);
    },
    onFinish: (state) => {
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages.at(-1);
        if (lastMessage) {
          const textContent = textOfMessage(lastMessage);
          if (textContent) {
            body =
              textContent.length > 200
                ? textContent.substring(0, 200) + "..."
                : textContent;
          }
        }
        showNotification(state.title, { body });
      }
    },
  });

  useEffect(() => {
    if (!isNewThread || projectScopeLoading) {
      return;
    }

    const projectChanged =
      projectContextForEntry !== null &&
      (settings.context.research_project_id !==
        projectContextForEntry.research_project_id ||
        settings.context.research_project_name !==
          projectContextForEntry.research_project_name ||
        !sameStringArray(
          settings.context.research_project_document_ids,
          projectContextForEntry.research_project_document_ids,
        ));
    const topicChanged =
      topicContextForEntry !== null &&
      (settings.context.daily_topic_query !==
        topicContextForEntry.daily_topic_query ||
        !sameStringArray(
          settings.context.daily_topic_document_ids,
          topicContextForEntry.daily_topic_document_ids,
        ) ||
        !sameStringArray(
          settings.context.daily_topic_evidence_ids,
          topicContextForEntry.daily_topic_evidence_ids,
        ) ||
        settings.context.daily_topic_release_id !==
          topicContextForEntry.daily_topic_release_id);

    if (!projectChanged && !topicChanged) {
      return;
    }

    setSettings("context", {
      ...(projectChanged ? projectContextForEntry : {}),
      ...(topicChanged ? topicContextForEntry : {}),
    });
  }, [
    isNewThread,
    projectContextForEntry,
    projectScopeLoading,
    setSettings,
    settings.context,
    topicContextForEntry,
  ]);

  useEffect(() => {
    if (
      !starterPrompt ||
      starterSentRef.current ||
      !isNewThread ||
      isMock ||
      projectScopeLoading ||
      (starterProjectId && !projectScope) ||
      modelsLoading ||
      models.length === 0
    ) {
      return;
    }
    starterSentRef.current = true;
    void sendMessage(threadId, { text: starterPrompt, files: [] }).catch(() => {
      starterSentRef.current = false;
    });
  }, [
    isMock,
    isNewThread,
    models.length,
    modelsLoading,
    projectScope,
    projectScopeLoading,
    sendMessage,
    starterPrompt,
    starterProjectId,
    threadId,
  ]);

  const hasThreadMessages = thread.messages.length > 0;

  useEffect(() => {
    if (
      !isNewThread &&
      !isMock &&
      threadMetadata.data === null &&
      !threadMetadata.isLoading &&
      !threadMetadata.isFetching &&
      !isHistoryLoading &&
      !hasMoreHistory &&
      !hasThreadMessages
    ) {
      const query = searchParams.toString();
      router.replace(`/workspace/chats/new${query ? `?${query}` : ""}`);
    }
  }, [
    hasMoreHistory,
    hasThreadMessages,
    isHistoryLoading,
    isMock,
    isNewThread,
    router,
    searchParams,
    threadMetadata.data,
    threadMetadata.isFetching,
    threadMetadata.isLoading,
  ]);

  const handleSubmit = useCallback(
    (message: PromptInputMessage, options?: InputBoxSubmitOptions) => {
      if (models.length === 0) {
        toast.error(t.inputBox.modelUnavailable);
        return;
      }
      const sendPromise = sendMessage(threadId, message, undefined, options);
      if (message.files.length > 0) {
        return sendPromise;
      }
      void sendPromise;
    },
    [models.length, sendMessage, t.inputBox.modelUnavailable, threadId],
  );
  const handleSubmitHumanInput = useCallback(
    async (request: HumanInputRequest, response: HumanInputResponse) => {
      let sent = false;
      await sendMessage(
        threadId,
        {
          text: buildHumanInputResponseText(request, response),
          files: [],
        },
        undefined,
        {
          additionalKwargs: {
            hide_from_ui: true,
            human_input_response: response,
          },
          onSent: () => {
            sent = true;
          },
        },
      );
      return sent;
    },
    [sendMessage, threadId],
  );
  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);
  const handleRegenerate = useCallback(
    (messageId: string, supersededMessageIds: string[]) =>
      regenerateMessage(threadId, messageId, supersededMessageIds),
    [regenerateMessage, threadId],
  );
  const handleBranchTurn = useCallback(
    async (messageId: string, messageIds: string[]) => {
      if (
        isNewThread ||
        isMock ||
        env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"
      ) {
        return;
      }

      try {
        const response = await branchThread.mutateAsync({
          threadId,
          messageId,
          messageIds,
        });
        toast.success(t.conversation.branchCreated);
        router.push(`/workspace/chats/${response.thread_id}`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : t.conversation.branchFailed,
        );
      }
    },
    [branchThread, isMock, isNewThread, router, t, threadId],
  );

  const tokenUsageInlineMode = tokenUsageEnabled
    ? localSettings.tokenUsage.inlineMode
    : "off";
  const hasTodos = (thread.values.todos?.length ?? 0) > 0;
  const { activeGoal, hasGoal, setLocalGoal } = useActiveGoal(
    threadId,
    thread.values.goal,
  );
  const hasOpenHumanInputCard = useMemo(
    () =>
      hasOpenHumanInputRequest(
        thread.messages,
        (message) => !isHiddenFromUIMessage(message),
      ),
    [thread.messages],
  );

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <SidecarProvider
        parentThreadId={threadId}
        context={runtimeContext}
        isMock={isMock}
      >
        <ChatBox threadId={threadId}>
          <div className="relative flex size-full min-h-0 justify-between">
            <header
              className={cn(
                "absolute top-0 right-0 left-0 z-30 flex h-12 shrink-0 items-center gap-2 px-2 sm:px-4",
                isWelcomeMode
                  ? "bg-background/0 backdrop-blur-none"
                  : "bg-background/80 shadow-xs backdrop-blur",
              )}
            >
              <SidebarTrigger className="md:hidden" />
              <div className="flex min-w-0 flex-1 items-center text-sm font-medium">
                <ThreadTitle threadId={threadId} thread={thread} />
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!isNewThread && (
                  <ThreadScheduledTasksLink threadId={threadId} />
                )}
                <TokenUsageIndicator
                  threadId={isNewThread ? undefined : threadId}
                  backendUsage={backendTokenUsage}
                  enabled={tokenUsageEnabled}
                  messages={thread.messages}
                  pendingMessages={pendingUsageMessages}
                  preferences={localSettings.tokenUsage}
                  onPreferencesChange={(preferences) =>
                    setLocalSettings("tokenUsage", preferences)
                  }
                />
                <SidecarTrigger />
                <ExportTrigger threadId={threadId} />
                <ArtifactTrigger />
              </div>
            </header>
            <main className="flex min-h-0 max-w-full grow flex-col">
              <div className="flex min-h-0 flex-1 justify-center">
                <MessageList
                  className={cn("size-full", !isWelcomeMode && "pt-10")}
                  testId="main-message-list"
                  threadId={threadId}
                  thread={thread}
                  paddingBottom={MESSAGE_LIST_DEFAULT_PADDING_BOTTOM}
                  hasMoreHistory={hasMoreHistory}
                  loadMoreHistory={loadMoreHistory}
                  isHistoryLoading={isHistoryLoading}
                  tokenUsageInlineMode={tokenUsageInlineMode}
                  canRegenerate={
                    !isNewThread &&
                    !isMock &&
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" &&
                    !isUploading &&
                    !thread.isLoading
                  }
                  onRegenerateMessage={handleRegenerate}
                  onSubmitHumanInput={
                    isMock || env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"
                      ? undefined
                      : handleSubmitHumanInput
                  }
                  canBranch={
                    !isNewThread &&
                    !isMock &&
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" &&
                    !isUploading &&
                    !thread.isLoading &&
                    !branchThread.isPending
                  }
                  onBranchTurn={handleBranchTurn}
                />
              </div>
              <div
                className={cn(
                  "right-0 bottom-0 left-0 z-30 flex justify-center px-3 sm:px-4",
                  isWelcomeMode ? "absolute" : "relative shrink-0 pb-4",
                )}
              >
                <div
                  className={cn(
                    "relative w-full",
                    isWelcomeMode &&
                      "-translate-y-[calc(50vh-48px)] sm:-translate-y-[calc(50vh-96px)]",
                    isWelcomeMode
                      ? "max-w-(--container-width-sm)"
                      : "max-w-(--container-width-md)",
                  )}
                >
                  {(hasGoal || hasTodos) && (
                    <div
                      className={cn(
                        "right-0 left-0 z-0",
                        isWelcomeMode ? "absolute -top-4" : "relative",
                      )}
                    >
                      <div
                        className={cn(
                          "right-0 bottom-0 left-0 flex flex-col",
                          isWelcomeMode ? "absolute" : "relative",
                        )}
                      >
                        {activeGoal && <GoalStatus goal={activeGoal} />}
                        {hasTodos && (
                          <TodoList
                            className="bg-background/5"
                            todos={thread.values.todos ?? []}
                            hidden={false}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  {mounted ? (
                    <>
                      {!modelsLoading && models.length === 0 && (
                        <div
                          className="border-border bg-background text-muted-foreground mb-3 rounded-md border px-3 py-2 text-center text-sm shadow-xs"
                          role="status"
                        >
                          {t.inputBox.modelUnavailable}
                        </div>
                      )}
                      <InputBox
                        className={cn(
                          "bg-background/5 w-full",
                          isWelcomeMode && "-translate-y-2 sm:-translate-y-4",
                        )}
                        isWelcomeMode={isWelcomeMode}
                        threadId={threadId}
                        autoFocus={isWelcomeMode}
                        status={
                          thread.error
                            ? "error"
                            : thread.isLoading
                              ? "streaming"
                              : "ready"
                        }
                        context={runtimeContext}
                        extraHeader={
                          isWelcomeMode &&
                          !hasGoal &&
                          !hasTodos && <Welcome mode={runtimeContext.mode} />
                        }
                        disabled={
                          isMock ||
                          env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ||
                          isUploading ||
                          hasOpenHumanInputCard ||
                          (!isNewThread && isHistoryLoading)
                        }
                        onContextChange={(context) =>
                          setSettings("context", context)
                        }
                        onGoalChange={setLocalGoal}
                        onSubmit={handleSubmit}
                        onStop={handleStop}
                      />
                    </>
                  ) : (
                    <div
                      aria-hidden="true"
                      className={cn(
                        "bg-background/5 h-32 w-full rounded-2xl",
                        isWelcomeMode && "-translate-y-2 sm:-translate-y-4",
                      )}
                    />
                  )}
                  {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                    <div className="text-muted-foreground/67 w-full translate-y-12 text-center text-xs">
                      {t.common.notAvailableInDemoMode}
                    </div>
                  )}
                </div>
              </div>
            </main>
          </div>
        </ChatBox>
      </SidecarProvider>
    </ThreadContext.Provider>
  );
}
