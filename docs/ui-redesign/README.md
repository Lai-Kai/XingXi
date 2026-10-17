# XingXi UI 全面重构：Gemini 设计，Codex 实现

本目录是此次重构的交接入口。目标是重新设计信息架构、布局、配色、组件、动效和移动端体验，同时保留现有功能与业务协议。

## 当前状态

- 已完成仓库代码层面的初步审计与协作准备。
- Gemini 使用 CLI／IDE 直接读取仓库并输出设计文档。
- Gemini 设计 `v1.1.0` 已交接；Batch 0–2、Batch 3 首页／聊天／地图，以及 Batch 4 文献／图谱／质量／评测／运营／定时任务六页已实施。其余业务页与 Batch 5、完整 UI／业务验收继续后续。
- 工作分支：`feat/ui-redesign`；准备时基线：`111f59dfa07c7c52ad67d7eb435c35cc8db2b385`。
- 既有 `.scratch/map-glb-preview/` 与 `start-xingxi.sh` 保留，不纳入本任务。

## 本轮实施证据

[整体收尾与辅助页核对](closeout-qa.md) · [辅助页截图](../../reports/ui-redesign/2026-10-15/closeout/index.html) · [真实 Gateway／数据库演练准备](gateway-integration-runbook.md)

本次辅助入口补充核对完成，112 浏览器与 794 单元通过。真实联调尚未执行，范围外 5 项历史失败及 Batch 5 完整验收继续保留。

[Batch 4 实施说明](batch-04-admin.md) · [Batch 4 QA](batch-04-qa.md) · [六页与专业流程截图](../../reports/ui-redesign/2026-10-15/batch-4/index.html)

[Batch 3 实施说明](batch-03-core.md) · [Batch 3 QA](batch-03-qa.md) · [核心三页与真实 OSM 截图](../../reports/ui-redesign/2026-10-15/batch-3/index.html)

[Batch 2 实施说明](batch-02-workspace.md) · [Batch 2 QA](batch-02-qa.md) · [新版截图与前后对照](../../reports/ui-redesign/2026-10-15/batch-2/index.html)

[Batch 0/1 实施说明](batch-01-foundations.md) · [QA 汇总](05-qa-report.md) · [Batch 0/1 截图对照](../../reports/ui-redesign/2026-10-15/index.html)

## 文件与责任

| 文件 | 用途 | 负责方 |
| --- | --- | --- |
| `01-audit.md` | 技术栈、路由、功能边界及待核实项 | Codex |
| `02-design-system.md` | 设计规格与完整性清单 | Gemini |
| `03-implementation-plan.md` | 实施批次与验收边界 | Codex |
| `04-progress.md` | 设计版本、批次状态、下一动作 | 双方 |
| `05-qa-report.md` | 实际运行证据及限制 | Codex |
| `gemini-design-task.md` | 交给 Gemini 的完整任务 | 用户交给 Gemini |
| `codex-implementation-task.md` | 设计交接后交给 Codex 的完整任务 | 用户交给 Codex |
| `regression-checklist.md` | 功能保留、角色、视口验收矩阵 | Codex |

本地任务记录位于 `.scratch/ui-redesign/`，遵循既有本地 Markdown tracker，不向上游仓库发布任务。

## 执行顺序

1. 在 Gemini CLI／IDE 中打开 **XingXi 仓库根目录**。以 `gemini-design-task.md` 的完整内容作为任务；确认工具实际加载了 `GEMINI.md`、根 `AGENTS.md` 和 `frontend/AGENTS.md`。
2. Gemini 先读取审计与实际源码，提出视觉方向，再完成 `02-design-system.md`。布局草图、原型和素材仅写入 `docs/ui-redesign/design/`，不要改运行中的前端代码。
3. 设计文档达到 `ready-for-implementation` 后，将 `codex-implementation-task.md` 的完整内容交给在 XingXi 工作区运行的 Codex。已有用户确认直接沿用；缺少的局部决策由责任方明确记录，不能凭占位规格实现整套 UI。
4. Codex 先建立旧版运行与截图基线，再依次实现 Token／公共组件、全局布局、核心页面、管理页面、响应式及细节。
5. 每批更新进度、测试报告和 README 迭代日志；通过最终功能回归与 Gemini 视觉复核后再进入合并／发布流程。

## 同时工作的边界

- Gemini 的设计规格与原型是交接产物；Codex 负责产品代码、测试和集成。
- 不同时编辑同一文件。Codex 实施期间冻结所使用的设计版本；后续设计修订写清变化及受影响页面。
- 保留现有项目规则，特别是单一星羲产品入口、权限、证据与知识发布协议。
- 不自动提交已有用户文件；不初始化第二套 Playwright；不以演示数据替换业务数据。
- 从代码发现风险不等于浏览器复现问题；记录清楚证据层级。

## 环境提醒

`frontend/package.json` 指定 `pnpm@10.26.2`，与根目录工具包声明不同；前端操作必须使用前端自己的工具链。本轮使用 Node v24.19.0 直接调用已安装依赖，并用本机 Chrome 在独立 3106 端口验收；没有改包清单／锁文件。

根规则引用的 `../PROJECT_PLAN.md` 在此次本地路径未发现。设计可依据已核实的源码继续；涉及产品阶段或业务行为变化时先找回该权威计划。

## 官方依据

- [Codex AGENTS.md](https://developers.openai.com/codex/guides/agents-md)：本次核对了项目指令的目录层级规则。
- [Gemini GEMINI.md](https://geminicli.com/docs/cli/gemini-md/)：本次核对了 `@./file.md` 导入语法。具体 IDE 是否自动加载须在该 IDE 中确认。
