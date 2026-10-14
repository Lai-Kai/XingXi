# Software test reports

Status: ready-for-human

Scope: P0. Preserve existing test frameworks, produce per-batch manifests and readable reports, and retain first-failure browser evidence. Failed and unavailable checks must remain visible.

## Acceptance

- `make test-report` writes isolated reports, original command results and attachment hashes.
- Playwright generates HTML and JSON in CI and locally; first failures retain trace, screenshot and video.
- Report tooling has tests for failures, missing output, redaction and CSV/HTML safety where applicable.

## Comments

- 2026-09-26: User authorized implementation of the reviewed plan. Backend baseline started before changes.

- 2026-09-26: 首版代码与使用说明已完成，待人工界面验收。Agent 真正运行 30/30 通过，聚焦后端检查 26 项通过；新增前端用例受本机监听限制未运行，浏览器验收未完成。详见 ../VALIDATION.md。
