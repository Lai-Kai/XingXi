# 地图影像重建：SSH 接入

FLUX 3 图像预处理的后续融合设计见 [FLUX3_OOOSPLAT_FUSION_PLAN.md](FLUX3_OOOSPLAT_FUSION_PLAN.md)。该文档已核对新部署，但分阶段融合尚未实施；下文仍描述当前直接 `generate` 的执行链。

管理员打开古舆地图，选择一个点位，在详情的「影像重建」页签选择一个环拍视频或至少两张照片，填写名称和精度，点击「上传并重建」。结果保存在该点位的重建记录中，支持运行日志、取消、刷新恢复、按需高斯预览和 PLY 下载。原 GLB 建筑研习页签继续独立工作。

## 运行方式

1. Gateway 校验文件数量、扩展名、实际字节数，保存原件和持久任务。
2. SFTP 上传至固定远端目录下的任务 UUID 子目录。上传完成后直接启动远端 Python 监督进程。
3. 监督进程调用已有 `splatstudio generate --projects-root <任务目录>/projects --quality fast|balanced|high <输入>`。视频使用文件路径，照片使用目录路径。无 GPU 探测、资源门禁或排队调度。
4. 页面读取真实阶段和日志。连接中断保留最后状态；同一次请求重试复用任务 ID，远端 `.started` 原子目录防止重复启动。Gateway 重启后通过读取任务恢复连接。
5. CLI 退出后仍检查 `project.json` 的完成状态、结果路径、Gaussian 或 RGB PLY 属性、文件大小及 SHA-256，才标记完成。完成表示技术流程产物可用，不代表几何质量合格或史实核验通过。
6. 取消仅写入该任务的取消标记，监督进程只终止其自行创建的进程组。取消失败会明确显示连接错误，不声称已经停止。

上传原件和中间产物不会自动删除，成果不修改地图坐标、不替换 GLB、不创建知识发布或审核结论。已有 OOOSplat 项目不受新任务目录影响。

## Gateway 配置

在 `backend` 安装可选依赖：`uv sync --extra reconstruction`。本机已安装 Paramiko 4.0.0。Node 端使用 `@sparkjsdev/spark` 2.3.1、Three.js 0.183.2 渲染真正的 Gaussian PLY，不使用普通点云替代。

| 环境变量 | 默认值 / 用途 |
| --- | --- |
| `XINGXI_OOOSPLAT_SSH_CONFIG` | 项目根 `.cache/server_ssh.json`，仅服务端读取 |
| `XINGXI_OOOSPLAT_KNOWN_HOSTS` | `$DEER_FLOW_HOME/reconstructions/known_hosts`，可信主机公钥 |
| `XINGXI_OOOSPLAT_REMOTE_ROOT` | `/data/yuyuan/ooosplat/workspace/xingxi_jobs` |
| `XINGXI_OOOSPLAT_EXECUTABLE` | `/data/yuyuan/ooosplat/bin/splatstudio`，复用现有 wrapper |

SSH JSON 使用 `host`、`port`、`user`（或 `username`），以及 `password` 或 `key_filename`。不要提交该文件或将凭据传给浏览器。新连接使用已记录的主机公钥严格校验；主机密钥不匹配时必须由维护者核对后更新。当前 Windows 本地已复用既有连接记录该主机公钥，并验证严格校验连接成功。

远端需要 `python3`、可执行的现有 OOOSplat CLI、可写任务目录；服务账户只需普通用户权限。首次启动 Gateway 时 Alembic 增加 `0045_map_reconstruction_jobs`，SQLite/PostgreSQL 使用同一持久任务协议。部署容器时需挂载服务端 SSH 配置、known_hosts 和持久运行目录，并安装 `reconstruction` extra；本轮未部署远程 Gateway 或容器。

## 大文件与访问控制

上传总大小最多 2 GiB，最多 500 个文件；照片至少两张，视频仅一个，不能混传。API 对每个读取块累计实际字节数。首版所有上传、记录、取消和结果下载均限管理员；前端隐藏入口只是交互控制，后端鉴权仍是最终边界。

`/api/reconstructions/[[...segments]]` 是 Next.js 流式转发入口，通用 API rewrite 已移到 fallback，以免先于动态路由命中并截断超过 10 MiB 的请求。Cookie、CSRF、Range 和下载响应头通过白名单转发。Nginx 两份配置增加独立重建 location，允许 2050 MiB 请求体（含 multipart 开销），关闭请求/响应缓冲，Gateway 继续执行 2 GiB 素材限制。使用 Nginx 的部署需重载配置；本轮 Windows 本地使用 3000 入口验证，未运行 Nginx。

浏览器按需加载 Spark，仅挂载当前预览实例。初始视角聚焦高斯密集中心，「完整范围」恢复全部范围；两者只改相机，不删点或修改下载文件。支持旋转缩放、失败重试和资源释放。超过 256 MiB 的模型保留下载入口，避免在浏览器内整体解码。

2026-10-17 已增加 [彩色 PLY 地图预览](COLORED_PLY_MAP_PREVIEW.md)：RGB/RGBA 任务产物使用独立点云查看器并保留逐点颜色、Alpha；原高斯继续使用 Spark。任意点位的三维页签均可临时打开已有本地 PLY，支持点大小、深浅背景、方向翻转和单实例放大。后端兼容旧任务元数据；本地打开不等于持久资产发布。

## 验证证据与边界

本轮记录在 `reports/integration/2026-10-16/ooosplat/`：

- `backend-map.log`：22 项后端专项/地图回归通过，包括迁移、幂等冲突、限额、权限、断线、指定进程组取消、结果约束及非阻塞/并发初始化。
- `backend-before.log` / `backend-after.log`：完整后端套件改前/改后都因仓库缺少 `deerflow.skills.skillscan.orchestrator` 出现相同 12 个收集错误；不能声称完整后端通过。
- `ssh-smoke.log`：真实可信公钥 SSH 连接及真实 CLI `generate --help` 验证成功。
- `ssh-flow.log`：真实 SFTP、脱离 Gateway 的监督进程、轮询、校验下载、重复提交验证。使用专门的合成 CLI fixture，任务位于 `xingxi_integration_tests/475218c3-04ea-4c58-aa9c-828886b25a9b`，没有启动 GPU 训练，也没有写入业务任务表。
- `unit.log`：31 项地图单元通过。`browser-final.log` 的 18 项地图/GLB/新重建/代理检查通过；扩展的引用面板拖动用例曾在入场动画期间取坐标，修正为等待控件稳定后，`browser-core-confirm.log` 的全部 13 项核心界面检查通过，共 31 个不同浏览器用例。覆盖照片上传/CSRF/点位关联、取消、移动端混传拒绝与恢复、真实已有 PLY 预览/释放，以及 12 MiB 流式转发/Range/403 透传。
- `gaussian-canvas.png`：使用昨天 Bonsai 的真实 38,880 高斯 PLY 渲染。该结果不是本轮新训练，也不代表本轮训练质量验收。
- 类型、生产构建、格式检查通过；全前端 lint 无错误，保留 graph-overview 的 4 个原有警告。`gateway.migration.log` 记录实际数据库升级；本地 Gateway 健康检查 200，未登录地图跳转 307、重建 API 401，SSH 配置启用，业务任务表未注入测试任务。前端运行于 3000，Gateway 运行于 8001。

新实拍素材端到端 GPU 重建尚未在本轮执行。可直接从页面上传自己的素材启动；不额外实施资源检查和排队功能。
