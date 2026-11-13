import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, it } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { MessageGroup } from "@/components/workspace/messages/message-group";
import { I18nContext } from "@/core/i18n/context";
import type { Locale } from "@/core/i18n/locale";

const internalMessages: Message[] = [
  {
    id: "internal-message-id",
    type: "ai",
    content: "Retrying internal-model via https://private-api.invalid",
    additional_kwargs: {
      reasoning_content: "Private reasoning and service diagnostics",
    },
    usage_metadata: {
      input_tokens: 1234,
      output_tokens: 5678,
      total_tokens: 6912,
    },
    tool_calls: [
      {
        id: "internal-call-id",
        name: "bash",
        args: { command: "cat /private/config.yaml", token: "secret-key" },
      },
    ],
  },
  {
    id: "internal-result-id",
    type: "tool",
    name: "bash",
    tool_call_id: "internal-call-id",
    content: '{"error":"Service traceback with secret-key"}',
  },
] as Message[];

function renderGroup(isLoading: boolean, locale: Locale = "zh-CN") {
  return renderToStaticMarkup(
    createElement(
      I18nContext.Provider,
      { value: { locale, setLocale: () => undefined } },
      createElement(MessageGroup, {
        messages: internalMessages,
        isLoading,
        // A saved debug preference must not restore implementation details.
        showTokenDebugSummaries: true,
      }),
    ),
  );
}

describe("product conversation progress", () => {
  it("shows a neutral busy status without internal messages, parameters or reasoning", () => {
    const html = renderGroup(true);
    expect(html).toContain('role="status"');
    expect(html).not.toMatch(
      /internal-|private|secret-key|traceback|config\.yaml|6912|bash/i,
    );
    expect(html).not.toContain("<button");
  });

  it("does not leave a diagnostics disclosure in restored or completed history", () => {
    expect(renderGroup(false)).toBe("");
  });

  it("keeps the same privacy boundary in English", () => {
    const html = renderGroup(true, "en-US");
    expect(html).toContain('role="status"');
    expect(html).not.toMatch(
      /internal-|private|secret-key|traceback|config\.yaml|6912|bash/i,
    );
  });
});
