const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../..");
const esbuild = require(path.join(root, "frontend/node_modules/.pnpm/esbuild@0.27.7/node_modules/esbuild"));
const output = path.join(__dirname, "manual-rules.cjs");
esbuild.buildSync({ entryPoints: [path.join(root, "frontend/src/core/operations/manual-evaluations.ts")], bundle: true, platform: "node", format: "cjs", outfile: output });
const { canSubmitManualEvaluation, manualFailureLabel } = require(output);
const snapshot = JSON.parse(fs.readFileSync(path.join(__dirname, "snapshot.json"), "utf8"));
const active = snapshot.cases.find((item) => item.active);
const result = snapshot.runs[0].results[0];

test("empty observations cannot produce another empty evaluation", () => {
  assert.equal(canSubmitManualEvaluation(snapshot.cases, {}), false);
  assert.equal(canSubmitManualEvaluation(snapshot.cases, { [active.id]: { ...result, answer: "  \n " } }), false);
});
test("the actual recorded refusal is ready, while archived cases are ignored", () => {
  assert.equal(canSubmitManualEvaluation(snapshot.cases, { [active.id]: result }), true);
  assert.equal(canSubmitManualEvaluation(snapshot.cases.filter((item) => !item.active), {}), false);
});
test("invalid counts are blocked but genuine status mismatches can be graded", () => {
  for (const citation_count of [-1, 0.5, NaN]) assert.equal(canSubmitManualEvaluation(snapshot.cases, { [active.id]: { ...result, citation_count } }), false);
  assert.equal(canSubmitManualEvaluation(snapshot.cases, { [active.id]: { ...result, actual_status: "answered" } }), true);
});
test("historical failure reasons remain understandable", () => {
  assert.equal(manualFailureLabel("empty answer"), "没有填写本次回答");
  assert.equal(manualFailureLabel("missing required terms: 灵岩山"), "回答缺少必含词：灵岩山");
  assert.equal(manualFailureLabel("expected status refused, got answered"), "期望拒答，本次标记为回答");
  assert.equal(manualFailureLabel("expected at least 1 citations"), "有效引用不足，需要至少 1 条");
});
test("the standalone preview renders the real record without requiring a server", () => {
  const html = fs.readFileSync(path.join(root, "reports/testing/simple-demo/index.html"), "utf8");
  assert.match(html, /1 \/ 1 条规则通过/);
  assert.match(html, /100\.0%/);
  assert.match(html, /以下内容未被当前本地文献核验/);
  assert.match(html, /回答缺少必含词：灵岩山/);
  assert.match(html, /保存并查看结果/);
  assert.doesNotMatch(html, /<script[^>]+src=/);
  assert.equal(snapshot.runs[0].results[0].answer, fs.readFileSync(path.join(__dirname, "answer.txt"), "utf8").trim());
});
