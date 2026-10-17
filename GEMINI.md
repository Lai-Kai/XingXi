# XingXi — Gemini 项目入口

@./AGENTS.md

@./frontend/AGENTS.md

## 本次 UI 重构协作

在 `docs/ui-redesign/` 工作流中，Gemini 负责设计，Codex 负责产品实现。始终使用简体中文解释与总结，代码和命令保持原样。

先读取 `docs/ui-redesign/README.md` 和 `gemini-design-task.md`。核对真实代码，输出可直接实施的设计 Token、组件状态、页面布局、响应式、动效和本地原型。

设计阶段只更新设计资料和对应进度，不改产品源码、业务协议、依赖或运行配置。保留根与前端规则中的单一星羲助手、权限、Evidence、审核／发布、地图／图谱和流式聊天行为。

完整规格写入 `02-design-system.md`，用设计版本与 `ready-for-implementation` 状态交给 Codex。若 IDE 不支持 `@` 导入，必须显式读取被引用的两个 AGENTS 文件。
