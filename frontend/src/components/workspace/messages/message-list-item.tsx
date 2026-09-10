import type { Message } from "@langchain/langgraph-sdk";
import {
  FileIcon,
  Loader2Icon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import {
  memo,
  useCallback,
  useMemo,
  useState,
  useEffect,
  type ImgHTMLAttributes,
} from "react";

import { Loader } from "@/components/ai-elements/loader";
import {
  Message as AIElementMessage,
  MessageContent as AIElementMessageContent,
  MessageToolbar,
} from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Task, TaskTrigger } from "@/components/ai-elements/task";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  deleteFeedback,
  upsertFeedback,
  type FeedbackCategory,
  type FeedbackData,
} from "@/core/api/feedback";
import {
  resolveArtifactURL,
  resolveMessageImageURL,
} from "@/core/artifacts/utils";
import { extractCitationSources } from "@/core/citations/sources";
import { useI18n } from "@/core/i18n/hooks";
import {
  extractContentFromMessage,
  extractReasoningContentFromMessage,
  getMessageCopyData,
  parseUploadedFiles,
  stripUploadedFilesTag,
  type FileInMessage,
} from "@/core/messages/utils";
import { recordOperationEvent } from "@/core/operations/api";
import { useRehypeSplitWordsIntoSpans } from "@/core/rehype";
import { readReferenceMessageContexts } from "@/core/sidecar";
import {
  parseSlashSkillReference,
  resolveSlashSkillDisplay,
} from "@/core/skills";
import { useSkills } from "@/core/skills/hooks";
import { SafeReasoningContent } from "@/core/streamdown/components";
import { cn } from "@/lib/utils";

import { WorkspaceChangeBadge } from "../changes";
import { CitationSourcesPanel } from "../citations/citation-sources-panel";
import { CopyButton } from "../copy-button";
import { ReferenceAttachmentSummary } from "../sidecar/reference-attachments";
import { SlashSkillChip } from "../slash-skill-chip";

import { MarkdownContent } from "./markdown-content";
import { createMarkdownLinkComponent } from "./markdown-link";

export function FeedbackButtons({
  threadId,
  runId,
  initialFeedback,
  showPrompt = false,
}: {
  threadId: string;
  runId: string;
  initialFeedback: FeedbackData | null;
  showPrompt?: boolean;
}) {
  const [feedback, setFeedback] = useState<FeedbackData | null>(
    initialFeedback,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>("factual_error");
  const [comment, setComment] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    setFeedback(initialFeedback);
  }, [initialFeedback]);

  const handleClick = useCallback(
    async (
      rating: number,
      detail?: { category: FeedbackCategory; comment: string },
    ) => {
      if (isSubmitting) return;
      setSubmitError(null);
      setIsSubmitting(true);
      try {
        if (feedback?.rating === rating) {
          await deleteFeedback(threadId, runId);
          setFeedback(null);
        } else {
          const result = await upsertFeedback(
            threadId,
            runId,
            rating,
            detail?.comment,
            detail?.category,
          );
          setFeedback(result);
        }
        return true;
      } catch {
        setSubmitError("反馈提交失败，请稍后重试");
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [threadId, runId, feedback, isSubmitting],
  );

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      {showPrompt && (
        <span className="mr-1 text-xs text-[#718186]">这个回答有帮助吗？</span>
      )}
      <button
        type="button"
        className={cn(
          "flex size-8 items-center justify-center rounded-md border border-transparent text-[#718186] transition-colors hover:border-[#c8d9db] hover:bg-[#edf5f5] hover:text-[#276f79]",
          feedback?.rating === 1 &&
            "border-[#8fbcc2] bg-[#e5f1f2] text-[#1f6973]",
        )}
        onClick={() => void handleClick(1)}
        disabled={isSubmitting}
        aria-label="回答有帮助"
        aria-pressed={feedback?.rating === 1}
        title={feedback?.rating === 1 ? "取消有帮助" : "回答有帮助"}
      >
        {isSubmitting && feedback?.rating !== -1 ? (
          <Loader2Icon className="size-4 animate-spin" />
        ) : (
          <ThumbsUpIcon
            className={cn("size-4", feedback?.rating === 1 && "fill-current")}
          />
        )}
      </button>
      <button
        type="button"
        className={cn(
          "flex size-8 items-center justify-center rounded-md border border-transparent text-[#718186] transition-colors hover:border-[#dfb8b8] hover:bg-[#fbefef] hover:text-[#a34343]",
          feedback?.rating === -1 &&
            "border-[#d8aaaa] bg-[#f8eaea] text-[#a33d3d]",
        )}
        onClick={() => {
          if (feedback?.rating === -1) void handleClick(-1);
          else setDetailOpen(true);
        }}
        disabled={isSubmitting}
        aria-label="反馈回答问题"
        aria-pressed={feedback?.rating === -1}
        title={feedback?.rating === -1 ? "取消问题反馈" : "反馈回答问题"}
      >
        {isSubmitting && feedback?.rating === -1 ? (
          <Loader2Icon className="size-4 animate-spin" />
        ) : (
          <ThumbsDownIcon
            className={cn("size-4", feedback?.rating === -1 && "fill-current")}
          />
        )}
      </button>
      {feedback && (
        <span className="text-xs text-[#4d747a]" role="status">
          已记录
        </span>
      )}
      {submitError && !detailOpen && (
        <span className="text-xs text-red-700" role="alert">
          {submitError}
        </span>
      )}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>反馈回答问题</DialogTitle>
            <DialogDescription>
              反馈会进入质量审核队列，并关联当前会话与回答。
            </DialogDescription>
          </DialogHeader>
          <label className="grid gap-2 text-sm">
            <span className="font-medium">问题类型</span>
            <select
              value={category}
              onChange={(event) =>
                setCategory(event.target.value as FeedbackCategory)
              }
              className="h-10 rounded-md border border-[#d2dddf] bg-white px-3"
            >
              <option value="citation_error">引用错误</option>
              <option value="factual_error">事实错误</option>
              <option value="missing_source">资料缺失</option>
              <option value="expression_issue">表达问题</option>
              <option value="other">其他问题</option>
            </select>
          </label>
          <label className="grid gap-2 text-sm">
            <span className="font-medium">问题说明</span>
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="请说明哪一处需要核对"
              className="resize-none rounded-md border border-[#d2dddf] px-3 py-2 outline-none focus:border-[#6ea7af]"
            />
          </label>
          {submitError && <p className="text-sm text-red-700">{submitError}</p>}
          <DialogFooter>
            <button
              type="button"
              onClick={() => setDetailOpen(false)}
              className="h-9 rounded-md border px-4 text-sm"
            >
              取消
            </button>
            <button
              type="button"
              disabled={isSubmitting || !comment.trim()}
              onClick={async () => {
                setSubmitError(null);
                const submitted = await handleClick(-1, {
                  category,
                  comment: comment.trim(),
                });
                if (submitted) {
                  setDetailOpen(false);
                  setComment("");
                }
              }}
              className="h-9 rounded-md bg-[#276f79] px-4 text-sm text-white disabled:opacity-40"
            >
              {isSubmitting ? "提交中…" : "提交反馈"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function MessageListItem({
  className,
  message,
  isLoading,
  feedback,
  runId,
  threadId,
  artifactPaths = [],
  showCopyButton = true,
  turnStartTime,
}: {
  className?: string;
  message: Message;
  isLoading?: boolean;
  threadId: string;
  artifactPaths?: readonly string[];
  feedback?: FeedbackData | null;
  runId?: string;
  showCopyButton?: boolean;
  turnStartTime?: number | null;
}) {
  const isHuman = message.type === "human";
  return (
    <AIElementMessage
      className={cn("group/conversation-message relative w-full", className)}
      from={isHuman ? "user" : "assistant"}
    >
      <MessageContent
        className={isHuman ? "w-fit" : "w-full"}
        message={message}
        isLoading={isLoading}
        threadId={threadId}
        artifactPaths={artifactPaths}
        feedback={feedback}
        runId={runId}
        turnStartTime={turnStartTime}
      />
      {!isLoading && showCopyButton && (
        <MessageToolbar
          className={cn(
            isHuman
              ? "absolute right-0 -bottom-9 left-0 justify-end"
              : "absolute right-0 bottom-0 left-0",
            "z-20 opacity-0 transition-opacity delay-200 duration-300 group-hover/conversation-message:opacity-100",
          )}
        >
          <div className="pointer-events-auto flex gap-1">
            <CopyButton clipboardData={getMessageCopyData(message)} />
            {feedback !== undefined && runId && threadId && (
              <FeedbackButtons
                threadId={threadId}
                runId={runId}
                initialFeedback={feedback}
              />
            )}
          </div>
        </MessageToolbar>
      )}
    </AIElementMessage>
  );
}

/**
 * Custom image component that handles artifact URLs
 */
function MessageImage({
  src,
  alt,
  threadId,
  artifactPaths,
  maxWidth = "90%",
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement> & {
  threadId: string;
  artifactPaths: readonly string[];
  maxWidth?: string;
}) {
  if (!src) return null;

  const imgClassName = cn("overflow-hidden rounded-lg", `max-w-[${maxWidth}]`);

  if (typeof src !== "string") {
    return <img className={imgClassName} src={src} alt={alt} {...props} />;
  }

  const url = resolveMessageImageURL(src, threadId, artifactPaths);

  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      <img className={imgClassName} src={url} alt={alt} {...props} />
    </a>
  );
}

const clientTurnDurations = new Map<string, number>();

function HumanMessageText({ content }: { content: string }) {
  // `parseSlashSkillReference` is a pure regex gate (no data subscription), so
  // the overwhelmingly common plain-text human message never subscribes to the
  // skills query. Only a message that literally looks like a `/skill …`
  // activation mounts `HumanSlashSkillText`, which owns the `useSkills()`
  // lookup. This keeps a skill-enabled toggle from re-rendering every human
  // turn — only the few slash-candidate turns react to catalog changes.
  const reference = useMemo(() => parseSlashSkillReference(content), [content]);

  if (!reference) {
    return <div className="break-words whitespace-pre-wrap">{content}</div>;
  }

  return <HumanSlashSkillText content={content} />;
}

function HumanSlashSkillText({ content }: { content: string }) {
  const { skills } = useSkills();
  const slashSkill = resolveSlashSkillDisplay(content, skills);

  if (!slashSkill) {
    return <div className="break-words whitespace-pre-wrap">{content}</div>;
  }

  return (
    <div className="flex max-w-full min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <SlashSkillChip name={slashSkill.name} />
      {slashSkill.remainingText && (
        <span className="min-w-0 flex-1 break-words whitespace-pre-wrap">
          {slashSkill.remainingText}
        </span>
      )}
    </div>
  );
}

function MessageContent_({
  className,
  message,
  isLoading = false,
  threadId,
  artifactPaths,
  feedback,
  runId,
  turnStartTime,
}: {
  className?: string;
  message: Message;
  isLoading?: boolean;
  threadId: string;
  artifactPaths: readonly string[];
  feedback?: FeedbackData | null;
  runId?: string;
  turnStartTime?: number | null;
}) {
  const rehypePlugins = useRehypeSplitWordsIntoSpans(isLoading);
  const isHuman = message.type === "human";
  const rawTurnDuration = message.additional_kwargs?.turn_duration as
    | number
    | undefined;

  const [cachedDuration, setCachedDuration] = useState<number | undefined>(
    () =>
      message.id
        ? clientTurnDurations.get(`${threadId}:${message.id}`)
        : undefined,
  );
  const turnDuration = rawTurnDuration ?? cachedDuration;

  useEffect(() => {
    if (rawTurnDuration !== undefined && message.id) {
      clientTurnDurations.set(`${threadId}:${message.id}`, rawTurnDuration);
      setCachedDuration(rawTurnDuration);
    }
  }, [rawTurnDuration, message.id, threadId]);

  const handleDurationChange = useCallback(
    (d: number | undefined) => {
      if (d !== undefined && message.id) {
        clientTurnDurations.set(`${threadId}:${message.id}`, d);
        setCachedDuration(d);
      }
    },
    [message.id, threadId],
  );

  useEffect(() => {
    return () => {
      for (const key of clientTurnDurations.keys()) {
        if (key.startsWith(`${threadId}:`)) {
          clientTurnDurations.delete(key);
        }
      }
    };
  }, [threadId]);

  const [wasLoading, setWasLoading] = useState(isLoading);
  useEffect(() => {
    if (isLoading) setWasLoading(true);
  }, [isLoading]);
  const components = useMemo(
    () => ({
      img: (props: ImgHTMLAttributes<HTMLImageElement>) => (
        <MessageImage
          {...props}
          threadId={threadId}
          artifactPaths={artifactPaths}
          maxWidth="90%"
        />
      ),
      a: createMarkdownLinkComponent(threadId),
    }),
    [artifactPaths, threadId],
  );

  const rawContent = extractContentFromMessage(message);
  const reasoningContent = extractReasoningContentFromMessage(message);

  const files = useMemo(() => {
    const files = message.additional_kwargs?.files;
    if (!Array.isArray(files) || files.length === 0) {
      if (rawContent.includes("<uploaded_files>")) {
        // If the content contains the <uploaded_files> tag, we return the parsed files from the content for backward compatibility.
        return parseUploadedFiles(rawContent);
      }
      return null;
    }
    return files as FileInMessage[];
  }, [message.additional_kwargs?.files, rawContent]);
  const referenceAttachments = useMemo(
    () =>
      readReferenceMessageContexts(message.additional_kwargs).map(
        (context, index) => ({
          id: index,
          context,
        }),
      ),
    [message.additional_kwargs],
  );

  const contentToDisplay = useMemo(() => {
    if (isHuman) {
      return rawContent ? stripUploadedFilesTag(rawContent) : "";
    }
    return rawContent ?? "";
  }, [rawContent, isHuman]);
  const citationSources = useMemo(
    () => (isHuman ? [] : extractCitationSources(contentToDisplay)),
    [contentToDisplay, isHuman],
  );

  useEffect(() => {
    if (
      isHuman ||
      isLoading ||
      feedback === undefined ||
      !runId ||
      !contentToDisplay.trim()
    ) {
      return;
    }
    const messageId = String(message.id ?? "final");
    const refused = contentToDisplay.includes("当前检索范围内暂无明确记载");
    recordOperationEvent({
      event_type: "answer_completed",
      event_key: `answer:${runId}:${messageId}`,
      thread_id: threadId,
      run_id: runId,
      citation_count: citationSources.length,
      refused,
      metadata: { message_id: messageId },
    });
    if (refused) {
      recordOperationEvent({
        event_type: "search_miss",
        event_key: `miss:${runId}:${messageId}`,
        thread_id: threadId,
        run_id: runId,
        metadata: { message_id: messageId },
      });
    }
  }, [
    citationSources.length,
    contentToDisplay,
    feedback,
    isHuman,
    isLoading,
    message.id,
    runId,
    threadId,
  ]);

  const filesList =
    files && files.length > 0 ? (
      <RichFilesList files={files} threadId={threadId} />
    ) : null;

  // Uploading state: mock AI message shown while files upload
  if (message.additional_kwargs?.element === "task") {
    return (
      <AIElementMessageContent className={className}>
        <Task defaultOpen={false}>
          <TaskTrigger title="">
            <div className="text-muted-foreground flex w-full cursor-default items-center gap-2 text-sm select-none">
              <Loader className="size-4" />
              <span>{contentToDisplay}</span>
            </div>
          </TaskTrigger>
        </Task>
      </AIElementMessageContent>
    );
  }

  // Reasoning-only AI message (no main response content yet)
  if (!isHuman && reasoningContent && !rawContent) {
    return (
      <AIElementMessageContent className={className}>
        <Reasoning
          isStreaming={isLoading}
          startTimeProp={turnStartTime}
          duration={turnDuration}
          onTurnDurationChange={handleDurationChange}
        >
          <ReasoningTrigger />
          <SafeReasoningContent>{reasoningContent}</SafeReasoningContent>
        </Reasoning>
      </AIElementMessageContent>
    );
  }

  if (isHuman) {
    // Composer input is plain text, not authored Markdown. Parsing it as
    // Markdown mangles pasted code/logs (indented lines become code blocks,
    // "$...$" spans become math) and lets pathological input crash the page
    // through marked's recursive blockquote lexer, so render it verbatim.
    return (
      <div
        className={cn(
          "ml-auto flex max-w-full min-w-0 flex-col gap-2",
          className,
        )}
      >
        {referenceAttachments.length > 0 && (
          <ReferenceAttachmentSummary
            className="self-end shadow-none"
            references={referenceAttachments}
            testId="message-reference-attachment"
          />
        )}
        {filesList}
        {contentToDisplay && (
          <AIElementMessageContent className="w-full max-w-full">
            <HumanMessageText content={contentToDisplay} />
          </AIElementMessageContent>
        )}
      </div>
    );
  }

  return (
    <AIElementMessageContent className={className}>
      {filesList}
      {!isHuman &&
        (!!reasoningContent || wasLoading || turnDuration !== undefined) && (
          <Reasoning
            isStreaming={isLoading}
            startTimeProp={turnStartTime}
            duration={turnDuration}
            onTurnDurationChange={handleDurationChange}
          >
            <ReasoningTrigger hasContent={!!reasoningContent} />
            {reasoningContent && (
              <SafeReasoningContent>{reasoningContent}</SafeReasoningContent>
            )}
          </Reasoning>
        )}
      <MarkdownContent
        content={contentToDisplay}
        isLoading={isLoading}
        rehypePlugins={rehypePlugins}
        className="my-3"
        components={components}
      />
      <CitationSourcesPanel sources={citationSources} />
      {message.type === "ai" && (
        <WorkspaceChangeBadge
          threadId={threadId}
          runId={runId}
          disabled={isLoading}
        />
      )}
    </AIElementMessageContent>
  );
}

/**
 * Get file extension and check helpers
 */
const getFileExt = (filename: string) =>
  filename.split(".").pop()?.toLowerCase() ?? "";

const FILE_TYPE_MAP: Record<string, string> = {
  json: "JSON",
  csv: "CSV",
  txt: "TXT",
  md: "Markdown",
  py: "Python",
  js: "JavaScript",
  ts: "TypeScript",
  tsx: "TSX",
  jsx: "JSX",
  html: "HTML",
  css: "CSS",
  xml: "XML",
  yaml: "YAML",
  yml: "YAML",
  pdf: "PDF",
  png: "PNG",
  jpg: "JPG",
  jpeg: "JPEG",
  gif: "GIF",
  svg: "SVG",
  zip: "ZIP",
  tar: "TAR",
  gz: "GZ",
};

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"];

function getFileTypeLabel(filename: string): string {
  const ext = getFileExt(filename);
  return FILE_TYPE_MAP[ext] ?? (ext.toUpperCase() || "FILE");
}

function isImageFile(filename: string): boolean {
  return IMAGE_EXTENSIONS.includes(getFileExt(filename));
}

/**
 * Format bytes to human-readable size string
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return "—";
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

/**
 * List of files from additional_kwargs.files (with optional upload status)
 */
function RichFilesList({
  files,
  threadId,
}: {
  files: FileInMessage[];
  threadId: string;
}) {
  if (files.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap justify-end gap-2">
      {files.map((file, index) => (
        <RichFileCard
          key={`${file.filename}-${index}`}
          file={file}
          threadId={threadId}
        />
      ))}
    </div>
  );
}

/**
 * Single file card that handles FileInMessage (supports uploading state)
 */
function RichFileCard({
  file,
  threadId,
}: {
  file: FileInMessage;
  threadId: string;
}) {
  const { t } = useI18n();
  const isUploading = file.status === "uploading";
  const isImage = isImageFile(file.filename);

  if (isUploading) {
    return (
      <div className="bg-background border-border/40 flex max-w-50 min-w-30 flex-col gap-1 rounded-lg border p-3 opacity-60 shadow-sm">
        <div className="flex items-start gap-2">
          <Loader2Icon className="text-muted-foreground mt-0.5 size-4 shrink-0 animate-spin" />
          <span
            className="text-foreground truncate text-sm font-medium"
            title={file.filename}
          >
            {file.filename}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <Badge
            variant="secondary"
            className="rounded px-1.5 py-0.5 text-[10px] font-normal"
          >
            {getFileTypeLabel(file.filename)}
          </Badge>
          <span className="text-muted-foreground text-[10px]">
            {t.uploads.uploading}
          </span>
        </div>
      </div>
    );
  }

  if (!file.path) return null;

  const fileUrl = resolveArtifactURL(file.path, threadId);

  if (isImage) {
    return (
      <a
        href={fileUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group border-border/40 relative block overflow-hidden rounded-lg border"
      >
        <img
          src={fileUrl}
          alt={file.filename}
          className="h-32 w-auto max-w-60 object-cover transition-transform group-hover:scale-105"
        />
      </a>
    );
  }

  return (
    <div className="bg-background border-border/40 flex max-w-50 min-w-30 flex-col gap-1 rounded-lg border p-3 shadow-sm">
      <div className="flex items-start gap-2">
        <FileIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <span
          className="text-foreground truncate text-sm font-medium"
          title={file.filename}
        >
          {file.filename}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant="secondary"
          className="rounded px-1.5 py-0.5 text-[10px] font-normal"
        >
          {getFileTypeLabel(file.filename)}
        </Badge>
        <span className="text-muted-foreground text-[10px]">
          {formatBytes(file.size)}
        </span>
      </div>
    </div>
  );
}

const MessageContent = memo(MessageContent_);
