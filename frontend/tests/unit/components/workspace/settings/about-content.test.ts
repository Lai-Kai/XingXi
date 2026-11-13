import { expect, test } from "@rstest/core";

import { aboutMarkdown } from "@/components/workspace/settings/about-content";

test("about explains research features without build or framework metadata", () => {
  expect(aboutMarkdown).toContain("关于星羲弦沚");
  expect(aboutMarkdown).toContain("吴文化与木渎地域文史");
  expect(aboutMarkdown).toContain("原始文献核验");
  expect(aboutMarkdown).not.toMatch(
    /当前版本|deer.?flow|bytedance|star-history|support@|API|MCP|JSON/i,
  );
});
