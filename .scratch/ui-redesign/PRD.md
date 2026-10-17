# XingXi UI 全面重构 PRD

Status: ready-for-agent

## 目标

参考用户提供的分阶段方案，建立 Gemini CLI／IDE 设计、Codex 实现的协作路径，全面更新视觉、布局、交互和移动体验，同时保留既有功能。

## 边界

- 仅改单一星羲产品表现层，不恢复 Agent 广场或 DeerFlow 品牌。
- 保留路由、API、权限、状态、真实数据、Evidence、审核／发布与模型协议。
- Gemini 设计写入 `docs/ui-redesign/`，Codex 负责产品代码与验证。
- 不覆盖既有未跟踪文件，不向上游发布本地任务。

## 交付

1. 仓库初审、运行／截图基线、设计规格与原型。
2. 分批实现及功能保留映射。
3. 实际测试／浏览器证据、视觉复核与可回滚差异。

## 验收

以 `docs/ui-redesign/regression-checklist.md` 和 `05-qa-report.md` 的实际证据为准。当前仅准备阶段，不代表 UI 或功能验收已完成。

## 任务

- `issues/01-design.md`：Gemini 设计。
- `issues/02-baseline.md`：Codex 运行基线。
- `issues/03-implementation.md`：Codex 分批实施与验收。

## Comments

- 2026-10-14：用户确定 Gemini CLI／IDE 直接读取仓库输出设计文档。
