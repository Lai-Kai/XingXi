# 地图创建模型

管理员登录后打开 `http://localhost:3000/workspace/map`，点击地图顶部「创建模型」，或在点位详情中点击「创建模型」。顶部入口需要先选择点位；点位详情入口自动选中当前点位。

## 两种方式

1. **上传影像重建**：选择一个环拍视频或至少两张照片，填写名称和精度，点击「上传并重建」。继续使用现有 SSH / OOOSplat 执行链；提交后自动进入该点位的「影像重建」记录，可查看阶段、日志和取消。任务完成并刷新状态后，模型会进入点位「三维预览」的已接入列表。
2. **接入已有模型**：填写名称，选择一个 PLY 或 GLB，点击「保存并接入地图」。支持 RGB/RGBA 彩色点云、Gaussian PLY、内嵌几何与贴图的 GLB 2.0，最大 256 MiB。成功后自动打开所选点位的三维预览，刷新后可重新选择该模型。多个模型可通过「已接入模型」切换，原有 GLB 仍保留。

接入后的模型对可访问地图的登录用户提供预览与下载；创建、上传和重建任务管理仍限管理员。模型关联不会改变点位坐标、置信等级或知识发布状态。

「打开本地 PLY」继续提供临时预览；它不保存文件。需要持久保存时使用「创建模型 → 接入已有模型」。PLY 的颜色、透明度和查看操作见 [彩色 PLY 预览](COLORED_PLY_MAP_PREVIEW.md)。

## 新接口

| 方法与路径 | 用途 | 权限 |
| --- | --- | --- |
| `POST /api/map/model-assets` | multipart 上传一个 `file`，同时提交 `title`、`point_id`、可选 `request_id` | 管理员 |
| `GET /api/map/model-assets?point_id=...` | 列出已接入模型及已完成的关联重建结果 | 登录用户 |
| `GET /api/map/model-assets/{id}/file` | 预览文件；支持 Range | 登录用户 |
| `GET /api/map/model-assets/{id}/file?download=true` | 下载原件 | 登录用户 |

影像创建继续调用 `POST /api/reconstructions`。模型列表只返回名称、点位/实体标识、格式、类型、大小、哈希与文件入口，不返回 SSH 凭据、服务器路径或任务日志。

`kind` 为 `mesh | gaussian | point_cloud`，`format` 为 `glb | ply`。前端按文件属性选择 PLY 查看器，GLB 使用原 ModelViewer；地图标记只根据准确的 `point_id + entity_id` 关联显示 3D 标识。

## 存储与部署

- 复用 `map_reconstruction_jobs` 持久记录。文件接入记录为 `input_type=model`、`quality=imported`、`status=completed`，不启动 SSH 或训练；旧任务接口列表排除这些导入记录。无需新数据库迁移。
- 上传文件保存于 `$DEER_FLOW_HOME/reconstructions/<UUID>/model.ply|model.glb`。重建产物保留原任务目录。部署时继续持久挂载该运行目录与数据库。
- 请求 ID 与内容指纹用于重复提交恢复；改变素材或关联点位后使用新请求 ID。服务端检查实际字节数、扩展名与文件格式，失败不会创建完成记录。
- 模型读取需对应当前地图的有效点位/实体；已移出当前地图范围的资产不公开读取。列表目前查询最近 1000 条记录。
- Next.js 新增独立流式路由，避免通用 rewrite 的 10 MiB 克隆限制。两份 Nginx 配置新增 `/api/map/model-assets`，257 MiB 请求体上限及关闭缓冲；使用 Nginx 的部署需要重载配置。本轮本地未运行 Nginx。

本功能沿用现有直接 `splatstudio generate` 流程，未新增 GPU 检查、资源队列、结构/跨视角检查或人工审批，也未实现 FLUX 多阶段执行编排。本轮未启动新的 GPU 训练。

## 验证

记录位于 `reports/integration/2026-10-17/create-map-model/`：48 项后端专项、39 项地图单元、27 项浏览器用例通过，类型/生产构建/改动文件 lint 通过。浏览器使用真实已有 PLY/GLB 文件渲染，任务执行与界面数据使用软件测试夹具，未向正式业务库导入测试模型。完整后端改前/改后仍有相同 12 个既有 `skillscan.orchestrator` 收集错误。
