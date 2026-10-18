# 修复文献库状态与编辑弹窗

Status: ready-for-human

## 范围

1. nullable edition 编辑崩溃及空版本保存。
2. 最新 ChunkSet 的精确页/片段复核状态独立显示，和实际 Job 状态分别刷新。
3. 大型全文索引避免无限 IN 参数；内部工作版本失败后复用原版本重试。
4. 对应软件回归、文档同步与真实宿主激活边界记录。

## 结果

- 已先复现空版本弹窗错误、大批量 SQL 参数错误、失败内部版本重复发布、复核状态缺失，再实现修复。
- 文献库 API 返回最新 canonical ChunkSet 的精确文本复核汇总，页面与实际 Job 独立显示；复核后重取服务端状态，失败行可重试。
- 后端相关 31 项、前端相关 17 项通过；前端全量 ESLint/TypeScript、本次后端 Ruff 通过。
- 全量后端修改前后均为相同 12 项收集错误，缺少既有 skillscan.orchestrator 模块，未在本任务内修改。
- 实际业务库以 mode=ro/query_only 只读验证新查询，约 0.56 秒返回 3 本相关资料；未改业务复核、任务或活动版本。
- 3 项 Playwright 已收集，受环境限制未执行浏览器。宿主 Gateway 重启及真实失败任务重试待现场验收，操作见 `docs/xingxi-library-status-fix.md`。
