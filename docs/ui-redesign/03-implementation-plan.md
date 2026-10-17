# 03 — Codex 实施计划

已按 Gemini v1.1.0 完成 Batch 0/1、Batch 2、用户指定的 Batch 3 三页及 Batch 4 六个管理与专业页面。最新实现、证据和限制见 `batch-04-admin.md`、`batch-04-qa.md`；辅助入口（展签／异名／项目／登录）本次已补充核对并完成主题兼容，详见 `closeout-qa.md`；其余页面和全套最终验收继续后续实施。

| 批次 | 范围 | 完成条件 |
| --- | --- | --- |
| Batch 0 | 运行环境、功能与截图基线、设计文件完整性 | 已有失败与环境限制可追溯，主要路由／角色／视口有行为记录 |
| Batch 1 | 语义 Token、主题兼容、业务公共组件 | 原页面可用，键盘与状态正确，没有整库重装或手改生成组件 |
| Batch 2（已完成本批） | 导航、工作区 shell、侧栏、移动入口与滚动 | 25 项框架与导航检查通过；原路由和权限入口、Cookie／折叠／调整宽度保留 |
| Batch 3（已完成指定三页） | 首页、聊天／Evidence Inspector、地图／GLB | 核心与兼容专项 74 项通过；扩展回归及剩余问题见 Batch 3 QA；文献库与图谱主体留在后续功能域 |
| Batch 4（已完成用户指定六页） | 文献库、知识图谱、质量中心、Agent 评测、运营中心、定时任务 | 794 单元和 97 浏览器检查通过；保留审核／发布／权限；辅助入口补充核对见 closeout-qa；设置与其他次级路由完整重构为剩余范围 |
| Batch 5 | 响应式、动效、长内容、无障碍、完整回归与 Gemini 视觉复核 | 规格一致，关键业务回归通过；未测项目和剩余问题明确 |

## 代码边界

- 优先范围：`frontend/src/styles/`、业务展示组件、各页面的表现层与布局组合。
- `frontend/src/core/` 的 API、契约、状态、缓存、流式、持久化与权限逻辑保持原义；确需改动先解释必要性并补充相关回归。
- Backend、数据库、迁移、knowledge release、工具协议和模型行为不属于本次视觉重构。
- 根、前端、后端指南按当前模块读取，不能用通用模板替换已有规则。

## 检查命令

在 **frontend** 中使用包清单指定的 Node／pnpm 环境：

```powershell
Set-Location 'C:\Users\蒲煜元\Desktop\XingXi\frontend'
pnpm check
pnpm test
pnpm build
pnpm test:e2e
```

先确认 `pnpm test` 在实际环境中的运行／watch 模式。每批可先执行相应功能域测试；最终验收执行完整检查，不能仅凭首页打开就关闭任务。

- Mock E2E：已有 `playwright.config.ts`，不重复 `npm init playwright`。默认启动构建和服务，复用既有服务前确认版本及测试隔离。
- Replay Gateway E2E：已有 `playwright.real-backend.config.ts`，通过 `pnpm exec playwright test --config playwright.real-backend.config.ts` 执行；这是确定性软件行为验证，不代表真实模型质量。
- 真实浏览器：使用标准 Nginx 入口或已核实的本地入口，验证认证、权限、真实数据和资产；不为截图访问生产写操作。
- README 既有记录提到中文路径下 Turbopack 问题。仅在实际复现时考虑 `pnpm exec next build --webpack`，记录原因，不能把旧日志当作本轮失败。

## 证据与提交

- 用 `TEST_REPORT_DIR` 为单元、Mock E2E、Replay E2E 分配不同目录，避免 `results.json` 互相覆盖。
- 在 `05-qa-report.md` 记录版本、命令、退出码、结果、报告路径、数据来源与覆盖限制。
- 截图同时记录路由、视口、主题、权限／数据情景和 commit，建议存入 `reports/ui-redesign/<batch>/`。
- 旧截图用于功能与内容核对；新截图对照新规格，不要求新旧像素相同。
- 每批审核 `git diff --check`、文件差异与功能回归后，只暂存属于该批次的文件。保留用户原文件；不执行 `git add .`、自动 stash／reset／clean。
- 后续代码／配置／脚本变更完成时，在根 README「迭代日志」最前添加同轮记录。
