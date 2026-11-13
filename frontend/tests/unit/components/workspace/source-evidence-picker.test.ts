import { expect, test } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  SourceEvidencePicker,
  type SourceEvidenceSelection,
} from "@/components/workspace/source-evidence-picker";

test("selected evidence shows its book and page while keeping internal identities out of text and accessible labels", () => {
  const citation = {
    evidence_id: "private-evidence-unique-id",
    document_id: "private-document-unique-id",
    document_title: "木渎镇志",
    page_start: 23,
  } as SourceEvidenceSelection;
  const html = renderToStaticMarkup(
    createElement(SourceEvidencePicker, {
      name: "候选 1",
      suggestedQuery: "香溪",
      selected: [citation],
      onChange: () => undefined,
    }),
  );
  expect(html).toContain("木渎镇志");
  expect(html).toContain("23");
  expect(html).toContain("候选 1 出处关键词");
  expect(html).toContain("查找出处");
  expect(html).not.toContain(citation.evidence_id);
  expect(html).not.toContain(citation.document_id);
});
