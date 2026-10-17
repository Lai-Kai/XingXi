# 01 — 仓库与功能初步审计

审计日期：2026-10-14（Asia/Shanghai）。范围：项目指令、包清单、路由文件、首页、工作区布局、导航、主题与测试配置。

**主体保留 2026-10-14 的代码初审；2026-10-15 已补充 Batch 0/1 运行证据，见文末与 `05-qa-report.md`。部分原有业务回归失败，不声称全部功能验收通过。**

## 技术栈与结构

- 前端：Next.js `^16.2.6`、React `^19.0.0`、TypeScript `^5.8.2`、Tailwind CSS 4。
- 包管理：`frontend/package.json` 的 `pnpm@10.26.2`；根目录另有工具包清单，不作为前端安装依据。
- 状态与流式交互：TanStack Query、LangGraph SDK；业务入口与传输位于 `frontend/src/core/`。
- 组件：已有 Radix／Shadcn 体系、Lucide、`motion`、GSAP、MapLibre 和 `@google/model-viewer`。优先复用，无需为重构重新选择全套 UI 库。
- 生成目录 `src/components/ui/`、`src/components/ai-elements/` 按模块规则不直接手改；可通过 Token、业务包装组件和页面组合调整视觉。
- 单元测试：Rstest；浏览器测试：Playwright Chromium。已存在配置和覆盖文件，尚未运行。

## 产品定位

面向吴文化与木渎地域文史研究的星羲产品。可以大幅重排信息层级与布局，但不能恢复通用 Agent 广场／创建入口或 DeerFlow 品牌。公共产品助手与 Graph 仍为 `xingxi`。

## 路由与验收映射

以下路径按 `frontend/src/app/` 与导航源码核实；文件存在不意味着已在当前环境成功访问。

| 路由／入口 | 内容与保留要求 | 对应现有测试线索 |
| --- | --- | --- |
| `/` | 当前重定向至 `/workspace`，不另造默认营销首页 | `xingxi-home.spec.ts`、`f01-business-layout.spec.ts` |
| `/workspace` | 研究输入、今日选题、依据链接、原地展开历史；最新收录与推荐页签 | `xingxi-home.spec.ts` |
| `/workspace/agent` | 单一星羲助手入口，进入共用新聊天 | `agents-feature-disabled.spec.ts`、`f01-business-layout.spec.ts` |
| `/workspace/chats`、`/workspace/chats/new`、`/workspace/chats/[thread_id]` | 历史、搜索、输入、模型选择、流式响应、停止、分支、附件、人工输入、目标、产物 | `chat.spec.ts`、`thread-history.spec.ts`、`branch-thread.spec.ts`、`sidecar-chat.spec.ts` |
| `/workspace/projects`、`/workspace/projects/[project_id]` | 研究项目、归档状态与聊天证据范围 | `research-project-workspace.spec.ts` |
| `/workspace/library` | 文献、源文件、上传、导入、审核、知识版本、Evidence 定位 | `library-permissions.spec.ts`、`source-registration.spec.ts`、`source-review.spec.ts` |
| `/workspace/map` | 现代底图、目录筛选、历史事件、轨迹、路线、实时位置、详情与 GLB | `map-business.spec.ts`、`map-model-preview.spec.ts` |
| `/workspace/knowledge-graph` | 全目录概览／主题探索、关系范围、跳数、Evidence、审核与 URL 状态 | `knowledge-graph.spec.ts`、`knowledge-graph-overview.spec.ts`、`knowledge-graph-review.spec.ts` |
| `/workspace/glossary`、`/workspace/name-authority` | 古文展签、异名辨析；保留证据与不确定性表达 | 需补齐实际行为与当前测试覆盖核对 |
| `/workspace/quality` | 质量队列／详情，读、审核、管理权限分别保留 | 需核对具体测试覆盖 |
| `/workspace/evaluations`、`/workspace/operations` | 评测与运营，真实指标、治理读取、管理员写入、导出与不可用状态 | `agent-evaluations.spec.ts`、`agent-evaluation-dashboard.spec.ts`、`operations-loop.spec.ts` |
| `/workspace/scheduled-tasks` | 定时任务列表、创建、详情及运行历史 | `scheduled-tasks.spec.ts` |
| `/login`、`/setup`、`/auth/callback` | 登录、初始化与回调；路径与重定向保留 | `tests/unit/core/auth/`；浏览器基线待补 |
| 设置、命令面板、侧栏 | 主题、模型与偏好、通知、渠道、技能、记忆、宽度与折叠状态 | `sidebar.spec.ts`、`settings-notification.spec.ts`、`channels.spec.ts`、`ui-polish-mobile.spec.ts` |
| `/blog/…`、`/[lang]/docs/…` | 已有内容路由；实际可达性与是否纳入视觉重构待核实，不能直接删除 | `docs-localized-links.spec.ts` |
| `/workspace/agents/…` | 旧通用 Agent 目录布局重定向 `/workspace`，保持禁用 | `agents-feature-disabled.spec.ts` |

测试线索均指 `frontend/tests/e2e/`，除非另有说明。旧 landing／agent 测试可能包含历史假设，需先运行核对，不能见到文件就宣称其有效覆盖。

## 权限与状态边界

- 导航实际由 `workspace-nav-chat-list.tsx` 按 capability 过滤：文献 `source:manage`、研究项目 `project:manage`、质量 `quality:read`、评测与运营 `governance:read`。
- `workspace/layout.tsx` 处理登录、初始化、Gateway 离线和配置错误；重排布局不得删除这些分支。
- 客户端隐藏按钮不是授权；保留 Gateway 的写入校验与当前能力区分。
- 聊天历史顺序、人工输入协议、附件提交、`/goal`／`/compact`、模型选择与停止后的缓存刷新保持既有实现。
- 地图保留原始 OSM 现代底图与 attribution，不通过透明、滤镜、纸张覆盖改变底图。历史范围保持可选；原图、参考点与知识发布资产继续分离。
- GLB 按精确参考点绑定，保留 28 CSS 像素圆点、44 像素点击目标、按需加载与单实例查看器。
- 图谱保留 Release、Evidence、四类审核状态、失败时旧结果、服务器截断与页面分页的区分。
- 文献上传的独立取消／重试、真实进度、冲突操作、审核队列、明确 finalize、乐观 `state_version` 和发布指针不可改成浏览器模拟。

详细行为以根与前端 `AGENTS.md` 为准，本文件不替代它们。

## 当前视觉组织的代码发现

- `src/styles/globals.css` 已有语义主题变量及暗色映射，应在此体系上兼容设计 Token。
- 首页仍大量使用局部十六进制颜色；主题调整需要逐步迁移，不能仅改全局变量就视为所有页面已更新。
- `WorkspaceContent` 包含 Query provider、可调整侧栏、Cookie 初始状态、Gateway 横幅、命令面板与 Toaster，需在布局迁移中完整保留。
- 首页今日选题由 API／带真实依据的降级池提供；`latest`／`collections` 另有现有静态 `researchItems`。设计不得将这些静态内容或计数扩展成新的线上真实指标。
- 输入框与全局 `.field` 存在移除原生 outline 的写法，焦点视觉需要浏览器核实；尚未断言当前键盘体验有缺陷。

## 实施前仍需完成

1. 确认运行环境、有效工具路径与服务入口，建立原版构建／测试结果。
2. 采集代表性页面在 1440×900、1024×768、390×844、360×800 的截图；对地图／表格补充窄屏行为。
3. 逐项验证普通读者、研究／文献管理、治理读取与管理员能力，不凭角色名称假定 capability。
4. 核实列表、弹窗、表单、深链接、刷新后的状态、加载／空／错误／权限不足场景。
5. 找回或确认根规则引用的 `../PROJECT_PLAN.md`，记录产品范围；不借 UI 重构修改业务。

## 2026-10-15 运行补充

- 旧版：106 文件／771 单元通过，类型／lint／默认构建成功，4 条既有 lint warning。
- Batch 0 已采集 49 张四视口／主题／角色截图，固定源码副本与摘要；Batch 1 另有对应 49 张页面截图。
- 新版：107 文件／784 单元通过，新增组件专项 13 项浏览器检查通过，原来通过的 42 项同组用例保持通过；13 既有失败与 5 未执行单列保留。
- 这次使用 Mock API 与 auth-disabled 测试服务，未验证真实 Gateway 的认证／写权限或模型质量。
- 组件 API、实现边界及设计补充见 batch-01-foundations.md；完整报告见 05-qa-report.md。
