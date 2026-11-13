"use client";

import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { ArtifactsProvider } from "@/components/workspace/artifacts";
import { SubtasksProvider } from "@/core/tasks/context";

export function ChatProviders({ children }: { children: React.ReactNode }) {
  return (
    <SubtasksProvider>
      <ArtifactsProvider>
        <PromptInputProvider>
          <div
            className="xingxi-chat relative size-full min-h-0 min-w-0 overflow-hidden"
            data-testid="xingxi-chat-surface"
          >
            {children}
          </div>
        </PromptInputProvider>
      </ArtifactsProvider>
    </SubtasksProvider>
  );
}
