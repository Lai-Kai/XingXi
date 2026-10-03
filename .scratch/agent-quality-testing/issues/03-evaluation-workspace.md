# Evaluation workspace and validation

Status: ready-for-human

Scope: P1 frontend and final verification. Add automatic evaluation list/detail, polling, cancellation, rerun, review and export to the existing operations entry. Preserve the manual evaluation panel.

## Acceptance

- Clear replay/manual labels, status counts and failure explanations.
- Detail shows question, actual answer, checks, evidence and event timeline.
- New attempts retain their predecessor and failures remain visible after reload.
- Unit/API/browser tests, format checks and real replay evidence are reported honestly.
- README and module guidance describe actual commands and limitations.

## Comments

- 2026-09-26: Existing fixtures and reports will be reused where their contracts match Xingxi.

- 2026-09-26: 首版代码与使用说明已完成，待人工界面验收。Agent 真正运行 30/30 通过，聚焦后端检查 26 项通过；新增前端用例受本机监听限制未运行，浏览器验收未完成。详见 ../VALIDATION.md。
