# Automatic Xingxi agent evaluation

Status: ready-for-human

Scope: P1. Extend operations with durable replay execution, isolated real Gateway runs, evidence-backed assertions, cancellation, immutable attempt records, human review and report export.

## Acceptance

- Six representative scenarios first, then the 30-case suite.
- Admin-only execution; governance reads; synthetic data never enters the business corpus.
- Missing observations and incomplete executions cannot pass.
- Normal Gateway identity, Release binding, RunManager and Xingxi Graph paths execute.
- Durable claims and lease recovery avoid silent duplicate execution.
- Results expose actual outputs, tool events, evidence and individual checks.
- Existing manual observations stay readable and separately identified.

## Comments

- 2026-09-26: Implement P0/P1; real model evaluation and external platform integration remain P2.

- 2026-09-26: 首版代码与使用说明已完成，待人工界面验收。Agent 真正运行 30/30 通过，聚焦后端检查 26 项通过；新增前端用例受本机监听限制未运行，浏览器验收未完成。详见 ../VALIDATION.md。
