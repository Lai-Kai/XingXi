import { expect, test } from "@rstest/core";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

import { SourceEditDialog } from "@/components/workspace/source-edit-dialog";
import { type SourceDocumentSummary } from "@/core/source-files/api";

test("opens imported source metadata when its edition is unknown", () => {
  const source: SourceDocumentSummary = {
    id: "source-1",
    title: "测试方志",
    edition: null,
    source_institution: "测试资料室",
    source_type: "gazetteer",
    source_type_label: null,
    source_level: "U",
    holder: "测试资料室",
    status: "registered",
    created_at: "2026-10-17T00:00:00Z",
    updated_at: "2026-10-17T00:00:00Z",
  };

  expect(() =>
    renderToString(
      createElement(SourceEditDialog, {
        source,
        open: true,
        onOpenChange: () => undefined,
        onSaved: () => undefined,
      }),
    ),
  ).not.toThrow();
});
