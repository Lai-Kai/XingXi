# 06 — Batch 3 核心三页

Status: ready-for-human

Owner: Codex

Progress: implementation-complete

用户指定的检索首页、星羲聊天／Evidence Inspector、古舆地图三页按 Gemini v1.1.0 实施完成。

- 首页：本地水墨 Hero、Composer、今日课题双列、资料依据与历史日期。
- 聊天：主对话题签、真实引用数、响应式考据视窗、安全出处链接、重试／竞态／焦点返回。
- 地图：原色 OSM 浮动控制台、纪年滑块、可见区域相机留白、关联人物、GLB 旋转／复位／单实例放大。

## 验证

110 文件／794 单元、类型／lint／构建通过；核心与兼容专项 74 项通过。全扩展检查按名称去重为 133 通过／16 未通过／0 跳过，原 Batch 2 的 80 项通过项保持通过；未通过的 10 项同组旧问题和 6 项额外检查分开记录。

预览：reports/ui-redesign/2026-10-15/batch-3/index.html。

实现与限制：docs/ui-redesign/batch-03-core.md、batch-03-qa.md。29 核心截图含真实 OSM 瓦片与本地 GLB；49 同条件页面、13 框架、8 组件截图另存。软件 Mock 验收不代替真实 Gateway、服务端权限、实体触摸或模型史实质量。

## 下一步

查阅三页；后续推进文献库／图谱和其余业务页。旧失败由 04-baseline-regressions.md、额外检查由 07-extended-compatibility.md 跟踪。未自动提交、推送或发布。
