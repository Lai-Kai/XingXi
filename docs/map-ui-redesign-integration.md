# feat/ui-redesign 地图整合

2026-10-18 从 `origin/feat/ui-redesign`（`2f952d5f`）提取地图功能，整合到
现有 `main` 工作区。其余工作区页面沿用当前实现。代码尚未创建合并提交或部署。

## 已接入

- 全尺寸地图、悬浮工具栏、响应式详情面板、按年份查阅及模型自动旋转。
- 点击标点先打开概览，选择带大小的模型页签后才加载；保留七个真实 GLB。
- 管理员创建持久点位，导入 PLY/GLB；登录用户查看、切换和下载关联模型。
- 彩色点云及 Gaussian PLY 预览，管理员影像重建和可选 FLUX3 预处理。
- Next.js 与 Nginx 流式上传入口，保留 Cookie、CSRF 和 Range 下载行为。

保留了本地紧凑时间轴：桌面最高 200px、移动端最高 176px，并受 28dvh
限制。播放和折叠按钮保持可见，年份控件与事件在内部滚动。地图样式限定在
`frontend/src/styles/xingxi-map.css`，使用当前工作区的语义颜色。

自建点位和模型不会写入 Evidence、知识图谱或知识 Release，也不升级已有
坐标的置信等级。上传仅保存模型；重建需要显式提交与额外服务端配置。

## 数据库兼容

保留现有两条迁移历史，通过 `0047_merge_map_reconstruction` 汇合：

```text
0044_agent_evaluations
  ├─ 0045_evidence_lookup_index → 0046_agent_evaluation_cases ─┐
  └─ 0045_map_reconstruction_jobs → 0046_custom_map_points ───┤
                                   0047_merge_map_reconstruction
```

原分支的版本标识不变。空数据库及两侧已有数据库均可升级为同一个 head。
表定义登记在 harness 的 `persistence/map_records.py`；Gateway 保留工作流
职责，后续自动生成迁移不会误删新表。

## 安装与启用

1. 使用 Node.js 22+，在 `frontend/` 执行 `pnpm install --frozen-lockfile`。
   新依赖为 Three.js、Spark 及 Three.js 类型包。项目 `.npmrc` 已将缓存固定为
   仓库内的 `../.pnpm-store`，避免默认 `/data/.pnpm-store` 无写权限导致 EACCES。
2. 正常启动 Gateway 时自动迁移数据库。模型导入不需要 SSH 或 GPU。
3. 如需影像重建，在 `backend/` 安装 `uv sync --extra reconstruction`，再按
   [SSH 配置说明](OOOSPLAT_SSH_INTEGRATION.md)配置服务端凭据与可信主机公钥。
   FLUX3 是另一项可选配置，见[预处理说明](FLUX3_PREPROCESSING.md)。
4. 通过 Nginx 的部署需要重载新增的上传代理配置；统一入口继续使用 2026。

本机原生部署的入口沿用 `http://localhost:12026`。其启动器没有开启后端热更新，
更新代码与安装前端依赖后，还须在服务器普通终端重启一次：

```bash
bash /data/laikai/heikesong/deerflow-native/start.sh stop
bash /data/laikai/heikesong/deerflow-native/start.sh start
bash /data/laikai/heikesong/deerflow-native/start.sh status
```

新 Gateway 启动时执行上述迁移并注册新增接口。只刷新页面无法更新运行中的
旧后端。当前编码环境与宿主进程和端口隔离，不能从这里完成服务重启。

创建与查看说明见[创建点位](MAP_POINT_CREATION.md)、[创建模型](MAP_MODEL_CREATION.md)
和[彩色 PLY 预览](COLORED_PLY_MAP_PREVIEW.md)。随分支导入的 GPU 验证记录
属于原分支历史，本次没有启动真实 GPU 任务。

## 本次验证

| 检查 | 结果 |
| --- | --- |
| 地图、模型、重建、FLUX3、迁移与相关持久化专项 | 88 项后端测试通过 |
| 地图、独立加载、参考时间轴、上传流式代理、Next 路由优先级与开发域名配置 | 64 项前端单元测试通过 |
| 此次时间轴及点位读取专项 | 26 项后端测试通过 |
| 后端修改文件 Ruff 与格式检查 | 通过 |
| 前端完整 ESLint | 0 错误，4 条原有图谱警告 |
| 七个 GLB 文件 | SHA-256 与内容摘要地址一致 |
| 浏览器用例收集 | 6 个文件、36 个场景，收集通过；未执行浏览器场景 |
| Python 锁文件离线一致性 | 保留原镜像与现有包版本，检查通过 |
| 完整 `pnpm check`（ESLint 与 TypeScript） | 通过，只有上述 4 条原有警告 |
| 生产构建 `pnpm build --webpack` | 通过，81 个页面生成完成；地图及上传代理路由均已产出 |

当前会话禁止本地端口绑定，无法执行需要服务端口的浏览器回归；上述 36 个
浏览器场景仍需在可启动本地服务的环境执行。

安装缓存权限已修复，`pnpm store path` 确认为仓库内的 `.pnpm-store/v10`。
依赖现已在普通终端通过 `pnpm install --frozen-lockfile` 安装完成；安装后完整
`pnpm check`、地图及配置单元测试和 Webpack 生产构建均通过。

## 自建点位失败时地图不可用的修复

本机运行日志确认 `/api/map/catalog` 返回 200，而新加的
`/api/map/custom-points` 返回 404：旧 Gateway 进程尚未加载新路由。原页面通过
`Promise.all` 等待两者，导致成功的地图目录也被丢弃。现由
`core/map/use-map-catalog.ts` 独立加载，底图及目录先显示；自建点位失败只显示
单独的提示与“重试自建点位”按钮。重试不重新加载目录或重置图层，旧点位在
暂时失败时保留，列表的旧响应也不会覆盖刚创建的点位。目录本身失败仍显示
页面错误。

新增 7 项单元回归；修复前 4 项失败，修复后全部通过。另补 2 项浏览器场景
覆盖 404 后重试和缓慢请求不阻塞地图。新接口的线上启用仍需要上述宿主重启。
修复后完整 `pnpm check` 与 Webpack 生产构建再次通过，81 个页面生成完成。

## 历史时间轴空白的修复

上次重启已成功应用地图迁移，自建点位和目录接口现均返回 200。只读检查确认
当前知识版本 v2 的地图快照没有事件，而浏览器此前只补充了模型景点，遗漏了
原有五条参考事件。另外，年份滑块放在事件轨道上方，会占满紧凑面板的初始
可见区域。

新增 `/api/map/reference-events` 读取原有、带出处的景点事件，按精确点位 ID
与可见参考景点关联；不修改知识快照，也不赋予知识版本或人工复核身份。
原有知识事件的 ID 和复核状态始终优先。补充请求与点位请求并发且有独立
超时，失败不会丢弃地图主体。事件轨道已移到年份滑块之前，保留 200/176px
及 28dvh 的高度上限。

此次回归包括空版本恢复参考事件、出处与绑定校验、原知识事件不被覆盖、
补充接口失败，以及桌面与手机首排事件可见。新增接口需要再次按上述命令
重启原生 Gateway 后生效。

此次时间轴修复后，26 项后端专项、64 项前端地图及配置测试、完整
`pnpm check` 与 Webpack 生产构建均通过，81 个页面生成完成。浏览器场景已
收集，桌面与手机的实际显示仍需在宿主重启后验证。

完整后端套件在改前、改后均因缺少
`deerflow.skills.skillscan.orchestrator` 出现相同的 12 个收集错误。
额外旧库 bootstrap 检查的三个历史迁移场景出现 OCR 表列排序循环依赖；
其中首个场景已在整合前代码的隔离副本复现。本次地图升级回归包含空库、
当前版本、地图分支版本、原记录保留以及自动生成迁移不删表检查，均通过。

本次原始日志及整合前文件备份位于
`/tmp/xingxi-ui-map-integration-h5nm0gpj/`。除地图整合所需的八个原有修改文件外，
其余预存修改均保持逐字节一致；时间轴工具函数与原单元测试也未被覆盖。
