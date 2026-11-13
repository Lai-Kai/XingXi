import { expect, test } from "@rstest/core";

import { publicErrorMessage } from "@/core/ui/presentation";

const diagnostic =
  "API https://private.invalid/run?token=secret-key trace internal-model";

test.each([
  diagnostic,
  new Error(diagnostic),
  { message: diagnostic, detail: diagnostic },
  { detail: { message: diagnostic } },
  null,
  undefined,
])(
  "service failures only render the supplied business message (%j)",
  (error) => {
    const message = publicErrorMessage(error, "暂时无法完成操作，请稍后重试。");
    expect(message).toBe("暂时无法完成操作，请稍后重试。");
    expect(message).not.toMatch(/API|private|secret-key|internal-model/);
  },
);
