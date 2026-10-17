import type { Message } from "@langchain/langgraph-sdk";
import { BookOpenText } from "lucide-react";

import { extractCitationSources } from "@/core/citations/sources";
import {
  extractContentFromMessage,
  isHiddenFromUIMessage,
} from "@/core/messages/utils";

export function ResearchTurnHeading({
  messages,
  loading,
}: {
  messages: Message[];
  loading: boolean;
}) {
  const sources = new Set(
    messages
      .filter(
        (message) => message.type === "ai" && !isHiddenFromUIMessage(message),
      )
      .flatMap((message) =>
        extractCitationSources(extractContentFromMessage(message)).map(
          (source) => source.id,
        ),
      ),
  );
  return (
    <div className="research-turn-heading text-muted-foreground mb-4 flex flex-wrap items-center justify-between gap-2 border-b pb-3 font-sans text-xs">
      <span className="text-primary inline-flex items-center gap-2 font-medium">
        <BookOpenText className="size-4" />
        星羲 · 文史研读
      </span>
      <span>
        {loading
          ? "正在研究，出处随回答更新"
          : sources.size
            ? `${sources.size} 项引文 · 结论请对照原始出处`
            : "尚未附可核验引文"}
      </span>
    </div>
  );
}
