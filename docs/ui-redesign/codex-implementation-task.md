# 设计交接后交给 Codex 的完整实施任务

在 `C:\Users\蒲煜元\Desktop\XingXi` 实施 UI 全面重构，采用 Gemini 已输出的设计规格。保持全部原有功能与业务契约。请完成实现、实际检查与文档，不停留在建议阶段。

## 起始检查

1. 读取根与前端 `AGENTS.md`、`docs/ui-redesign/README.md`、审计、设计系统、实施计划、进度和回归清单。
2. 核对 `git status --short`、当前分支、设计版本与实际文件。目标分支 `feat/ui-redesign`，不覆盖用户的 `.scratch/map-glb-preview/` 或 `start-xingxi.sh`。
3. 设计应为 `ready-for-implementation` 并包含具体 Token、页面／组件状态和移动规格。仍为占位模板时，先完成不依赖视觉的环境与功能基线，并指出缺失设计；不要自行冒充 Gemini 已定稿。
4. 前端使用自身 `package.json` 中的工具链和现有 Rstest／Playwright。确认工具可执行，不重新初始化项目或测试库。

## 实施

- 先完成 Batch 0，记录原版功能、构建、已有失败、关键路由与视口截图。
- 按 `03-implementation-plan.md` 批次推进。Token／业务公共组件 → shell／导航 → 首页／聊天 → 文献／地图／图谱 → 其余页面 → 响应式／动效／完整验收。
- 充分重新组织表现层，但保留路径、查询参数、鉴权、API、状态／缓存、流式历史、人工输入、附件、目标／压缩、模型选择、Evidence、审核及发布语义。
- 使用现有语义主题与包装组件；不要手改生成的 `ui/`、`ai-elements/`，不要为视觉引入无必要的整库替换。
- 保留所有 loading／empty／error／offline／permission／pending／disabled 状态与键盘可用性。
- 地图、图谱、审核、发布、评测指标的特殊边界以模块指南为准。不能以假数据、示意值或隐藏困难功能完成视觉。

## 验证与收尾

- 每批运行相应功能测试并查看真实渲染，记录命令、退出码、证据路径及未测项。
- 最终执行前端 `pnpm check`、单元测试、构建与 E2E；必要时使用已有 Replay Gateway 套件验证跨层协议。
- Mock／Replay／真实浏览器分开报告；软件通过不代表真实模型质量。新 UI 视觉对照 Gemini 规格，旧截图用于功能核对。
- 覆盖回归清单中的角色、主题、视口、深链接、刷新持久化、长内容、地图／GLB、加载与失败恢复。
- 更新 `04-progress.md`、`05-qa-report.md`、本地 issue 及 README 迭代日志；架构改变时同步相关 AGENTS。
- 检查 `git diff --check` 与文件差异。提交仅包含本任务相关文件，不自动合并、推送上游或发布。
- 输出可复核的完成页面、文件、功能对应、实际检查和剩余限制，保留尚未完成的状态。
