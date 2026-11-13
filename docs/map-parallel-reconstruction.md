# 地图重建的并发、续跑与双格式产物

2026-10-29：当前正式 runner 已升级为 `d1e67f8488dd667e`，修复自动上传素材在画面匹配时的嵌套线程崩溃。前端沿用 `.next-releases/map-job-permissions-20261029`。本次实际任务与验证边界见 [自动流程修复](map-auto-flow-20261029.md)；下文保留 2026-10-27 的历史验证记录。

新建任务可以通过 `XINGXI_PARALLEL_RUNNER_ROOT` 接入扫描项目已部署的 FLUX / OOOSplat runner，`XINGXI_PARALLEL_PYTHON` 指向现有 FLUX Python。配置只影响新任务；任务创建时持久化 runner 根目录与 Python，旧串行任务继续使用原入口。

服务器入口仍要求四张卡中至少两张各空闲 20480 MiB，按 UUID 绑定 CUDA 与 Vulkan。资源不足会返回失败原因，不自动排队、不降低精度。CPU 相机准备不持有 GPU 锁，计算开始前再次检查。单场景 FLUX 双路处理后完整训练一次；批处理的多个独立场景可分卡推进，分别完成 FLUX 后直接训练。

保留原有管理员、CSRF、点位规范绑定、SSH可信主机校验以及幂等上传。`GET /api/reconstructions/{id}` 只观察任务；管理员显式 `POST /api/reconstructions/{id}/resume` 才能续跑失败/取消的并发任务。SQL revision CAS 确保多个 Gateway worker 只有一个能认领续跑；其他状态不能重开。失败或中断的训练可能重新执行该训练阶段，不声称恢复优化器检查点。

原 `GET /api/reconstructions/{id}/artifact/final.ply` 保留原生 Gaussian 作为地图默认预览。新增 `GET /api/reconstructions/{id}/artifact/rgb_points.ply` 返回独立的标准 RGB 点云。两个格式都进行完整文件检查和 SHA256 核对，下载仍仅管理员可用。接口返回 `resumable` 和可选 `rgb_artifact_url`，地图面板对应显示“继续处理”“查看 RGB 点云”和“下载 RGB 点云”。保留服务器已有选择文件按钮动画。

服务端计算目录位于原任务的 `projects/parallel/batch/`，回执包括输入摘要、处理图、相机、逐帧 prompt、进程所有权和阶段记录。重试保留 `.started` 防重目录。拥有同一随机标记且属于同一 Linux 用户的后代可在主进程退出后被核对和清理，不能据 PID 名称批量停止其他任务。

新 runner 支持基于输入/权重清单/提示词/seed/工作流的 RGB 编辑缓存、只读 HTTP 有限重试、失败场景隔离、准备阶段复用、磁盘预算、可选主体保护 mask 和 Alpha 预览。结构重绘不增加拒绝门禁。标准 RGB 文件不混入 Gaussian 属性，避免混合格式的预览兼容性问题。

2026-10-27 的验证已部署到正式地图，当日 runner 为 `/data/yuyuan/ooosplat/workspace/parallel_runner/ae99935e018272df`，正式前端发布目录为 `.next-releases/map-parallel-20261027`。调度服务器32项、后端定向114项、前端839项、浏览器10项全部通过；Webpack正式构建成功。完整后端套件因既有 `deerflow.skills.skillscan.orchestrator` 等模块缺失在收集阶段出现12项错误，未宣称全项目全绿。

真实GPU验证包含两张古松图的双卡FLUX新推理，以及120帧、原相机、15000步/1600的均衡训练；复用118张旧编辑及2张本轮新编辑，未减少素材或降低精度。新原生PLY有300000个Gaussian，标准RGB有273817点，下载摘要与Gateway产物契约均通过。另用新模型在正式地图页面跑过2项预览回归，业务接口模拟、正式数据库零写入；本轮没有再从HTTP上传创建一条正式业务训练任务。

原生默认视角能清楚显示古松，但有少量边缘散点；RGB默认全包围盒与初始朝向导致主体偏小，可缩放旋转。无独立holdout，本轮实验质量结论为INCONCLUSIVE。证据在扫描项目 `outputs/flux_ooosplat_improvements_20261027/`，软件回归、GPU执行完成及模型质量分别记录。
