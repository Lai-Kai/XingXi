# 彩色 PLY 预览
Status: ready-for-human

- [x] 后端先写失败测试，允许 RGB PLY 并返回类型和点数，兼容旧高斯元数据。
- [x] 前端按文件属性选择查看器，保留 RGB、Alpha，支持本地文件与任务产物。
- [x] 验证真实彩色产物、放大单实例、移动端、错误恢复与既有 GLB/Gaussian。
- [x] 更新 README、模块指南和交付文档。

## Comments
- 2026-10-17：启动；后端改前全套测试仍有 12 个既有 skillscan.orchestrator 收集错误，记录于 reports/integration/2026-10-17/colored-ply/backend-before.log。
- 2026-10-17：实现完成；35 项后端专项、37 项地图单元和 22 个不同浏览器用例有通过记录。最终显示默认实体颜色，保留文件 Alpha 开关，解决高斯派生 Alpha 直接混合导致普通点云偏暗的问题。完整验证与边界见 reports/integration/2026-10-17/colored-ply/README.md，供用户检查。
