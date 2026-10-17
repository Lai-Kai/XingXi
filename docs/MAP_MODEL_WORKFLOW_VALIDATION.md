# 模型新建与重新建立流程验证

日期：2026-10-17。分支：`feat/ui-redesign`。

## 验证结论

本次检查确认以下软件流程可用：

- 地图选点、输入名称、保存、刷新恢复，并返回创建模型弹窗关联新点位。
- 上传已有彩色 PLY、Gaussian PLY 或 GLB，保存后预览、下载及切换模型。
- 上传多张照片或单个视频创建重建任务，读取状态、失败原因和日志，取消指定任务，完成结果进入点位资产列表。
- 已有模型的点位重新上传素材会建立独立任务，保留旧模型和任务历史；同一次请求重试仍复用原任务。
- 同一批照片在首次失败后可重新选择并再次上传，产生新的请求 ID；刷新后仍可读取两个任务记录。
- 12 MiB 上传不被通用代理截断，Cookie、CSRF、Range 和权限错误正确透传。

使用重新建立流程时，在已有点位详情打开「影像重建」，重新选择素材并点击「上传并重建」。新结果保留为另一模型版本，可在「三维预览」的已接入模型列表切换。

## 检查结果

| 检查 | 结果 |
| --- | --- |
| 后端地图/点位/模型/重建/迁移专项 | 64 passed |
| 地图单元测试 | 42 passed |
| 桌面和移动端浏览器、真实 PLY/GLB 及代理专项 | 32 passed，0 failed，0 skipped |
| 前端 `pnpm check` | passed，4 条既有图谱组件警告 |
| 当前产品代码生产构建 | 上轮已通过；本轮只新增回归测试和验证文档 |
| 严格主机公钥校验的真实 SSH 连接 | passed |
| 当前服务端 `splatstudio generate --help` | exit 0，支持当前使用的参数 |
| 真实 SFTP 写入、读取及 SHA-256 比较 | 67,584 字节一致，诊断文件与 UUID 目录已清理 |
| 完整后端套件 | 仍有相同 12 个既有收集错误、2 skipped；缺少 `deerflow.skills.skillscan.orchestrator` |

新后端组合用例为 `backend/tests/test_map_model_workflow.py`，使用独立 SQLite 文件，将自建点位、导入模型、图片/视频重建、新请求重建、旧结果读取和重启恢复串联验证。远端模型执行在这类用例中为明确的测试适配器。浏览器对应复测位于 `frontend/tests/e2e/map-create-point.spec.ts`，并联合原模型/重建/代理用例执行。

真实服务器检查只执行入口帮助和独立传输诊断，没有启动新的 GPU 重建。因此以上结论验证软件交互、持久化、传输及服务入口，不等于新实拍素材的训练质量验收。当前产品仍使用已有 OOOSplat 直接执行链；FLUX 多阶段编排的范围保持原融合方案文档所述状态。

本地原始记录位于 `reports/integration/2026-10-17/model-workflow-check/`，包括 `backend.log`、`backend-full.log`、`unit/results.json`、`browser/results.json`、`browser.log`、`ssh-preflight.json` 和 `remote-generate-help.txt`。这些运行产物不随分支上传；仓库提交包含产品代码、回归用例和本说明。
