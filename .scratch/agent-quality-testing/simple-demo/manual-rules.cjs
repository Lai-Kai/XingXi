"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// frontend/src/core/operations/manual-evaluations.ts
var manual_evaluations_exports = {};
__export(manual_evaluations_exports, {
  canSubmitManualEvaluation: () => canSubmitManualEvaluation,
  manualFailureLabel: () => manualFailureLabel
});
module.exports = __toCommonJS(manual_evaluations_exports);
function canSubmitManualEvaluation(cases, observations) {
  const active = cases.filter((item) => item.active);
  return active.length > 0 && active.every((item) => {
    const observation = observations[item.id];
    if (!observation) return false;
    return Boolean(observation.answer.trim()) && Number.isInteger(observation.citation_count) && observation.citation_count >= 0;
  });
}
function manualFailureLabel(reason) {
  if (reason === "empty answer") return "\u6CA1\u6709\u586B\u5199\u672C\u6B21\u56DE\u7B54";
  if (reason === "missing observation") return "\u6CA1\u6709\u5F55\u5165\u672C\u6B21\u89C2\u6D4B";
  if (reason.startsWith("missing required terms: "))
    return `\u56DE\u7B54\u7F3A\u5C11\u5FC5\u542B\u8BCD\uFF1A${reason.slice(24)}`;
  const citations = /^expected at least (\d+) citations$/.exec(reason);
  if (citations) return `\u6709\u6548\u5F15\u7528\u4E0D\u8DB3\uFF0C\u9700\u8981\u81F3\u5C11 ${citations[1]} \u6761`;
  const status = /^expected status (answered|refused), got (answered|refused)$/.exec(reason);
  if (status)
    return `\u671F\u671B${status[1] === "answered" ? "\u56DE\u7B54" : "\u62D2\u7B54"}\uFF0C\u672C\u6B21\u6807\u8BB0\u4E3A${status[2] === "answered" ? "\u56DE\u7B54" : "\u62D2\u7B54"}`;
  return reason;
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  canSubmitManualEvaluation,
  manualFailureLabel
});
