# FLUX3 图片预处理接入

2026-10-17：已实现可选执行链，并使用反重力乐高案例完成真实 GPU 小批联调。本机 Gateway、地图界面与原有 FLUX3 服务已配置；其他环境仍需按下文配置。

## 页面操作

管理员进入古舆地图，选择点位，打开「影像重建」或「创建模型 → 上传影像重建」：

1. 选择图片或一个视频，填写名称与精度。
2. 「图片预处理」选择「FLUX3 图片编辑」。默认仍为「原图直接重建」，旧任务不改变。
3. 可填写图片编辑提示词；留空时使用固定默认指令，保留主体身份、颜色、视角与构图，整理白底并补全无关遮挡。
4. 点击「上传并重建」。页面显示原图相机重建、FLUX3 逐图进度与训练状态。完成结果沿用原有点位模型列表、彩色高斯预览和下载。

图片编辑可以重绘局部结构和表面；这里不增加结构/轮廓/跨视角拒训检查。白底 RGB 不等于透明 Alpha。原图、模型编辑图及回执分别保留，不自动加入 SAM、分割、抠像或新的 GPU 调度器。

## 实际执行链

```text
原件上传 → EXIF转正/尺寸标准化或视频抽帧
         → 完整原图 COLMAP（特征、匹配、相机、去畸变）
         → FLUX3 原图参考 + 固定提示词编辑
         → 按原图相机名称与尺寸组装 RGB 数据集
         → 既有 OOOSplat Brush GPU 训练 → 原生彩色 Gaussian PLY
```

SFTP、SSH、任务 UUID、幂等请求和受保护下载沿用已有实现。原图相机确定后，不再用编辑图重新求相机。FLUX 调用发生在 SSH 服务器内部，访问本机 ComfyUI；浏览器不需要连接远端 ComfyUI 端口。

工作流复用已部署节点：`LoadImage → ReferenceMultiLatent → KSampler → VAEDecode → SaveImage`，BF16 FLUX3 Klein、Qwen3-VL 编码器与现有 VAE，16 步、CFG 1、Euler/simple、固定 seed 42、`keep resolution`。当前配置不调用 Prompt Upsampler。生成尺寸的取整由全幅缩放恢复到对应相机图尺寸，不裁剪、不添加投影检查阶段。

全部输入图片保留预处理映射。若部分图片未被 COLMAP 注册，仍保留其编辑结果；训练只能使用有相机的视图。`pipeline_result.json` 分别记录输入、注册、已处理数量和未注册文件名，不能把处理完成宣称为全部相机注册成功。

融合精度档明确映射如下，不声称等同于原生 `generate` 的全部隐含默认参数：

| 档位     | Brush 步数 | 最大分辨率 | 高斯数量上限 |
| -------- | ---------: | ---------: | -----------: |
| fast     |      8,000 |      1,200 |      150,000 |
| balanced |     15,000 |      1,600 |      300,000 |
| high     |     30,000 |      2,000 |      500,000 |

high 另使用 `growth-grad-threshold=0.00003`、`growth-select-fraction=0.25`、`growth-stop-iter=25000`。RGB 方案不额外启用透明 Alpha 约束。点数是上限，实际点数会更少。视频按档位最多抽取60/120/150帧；本轮真实融合实测针对图片，视频分支尚未做真实GPU端到端验收。

## 连接与部署

先按 [SSH 接入文档](OOOSPLAT_SSH_INTEGRATION.md) 配置 SSH、严格校验的 `known_hosts` 与 `reconstruction` extra。在 Gateway 运行环境设置：

```dotenv
XINGXI_FLUX3_DEPLOY_ROOT=/data/yuyuan/a2g/flux3-klein-deploy-20261016-c3e9813c
XINGXI_FLUX3_BASE_URL=http://127.0.0.1:18188
# 默认使用 DEPLOY_ROOT/.venv/bin/python；该已有环境需包含 Pillow。
# XINGXI_FLUX3_PYTHON=/path/to/comfy/.venv/bin/python
# 默认从 OOOSplat executable 所在目录推导 ../engines。
# XINGXI_OOOSPLAT_ENGINE_DIR=/data/yuyuan/ooosplat/engines
```

`DEPLOY_ROOT/data/input` 和 `data/output` 必须对应该 ComfyUI 实例的实际输入/输出目录。主模型 `flux3_image_klein_sd_bf16.safetensors`、编码器 `qwen3vl_4b_bf16.safetensors` 和 `flux2-vae.safetensors` 继续使用已经部署的文件，不另行下载或替换模型。

已有部署可由维护者在服务器按其原入口启动：

```bash
python3 /data/yuyuan/a2g/flux3-klein-deploy-20261016-c3e9813c/standalone.py start \
  --precision bf16 --uuid '<已分配的 GPU UUID>' --port 18188 --vram-limit-gib 40
```

重启 Gateway 使配置生效。未设置 `XINGXI_FLUX3_DEPLOY_ROOT` 时该选项不可选；capabilities 中 `flux3_enabled` 表示配置存在，不代表实时在线探测。服务断开或推理失败会保留原图与任务日志并报告失败，不静默改为原图训练。远端服务生命周期由维护者管理，创建重建任务不会自动重启或抢占服务。

SSH 密码、私钥与登录文件仍不进入代码仓库或浏览器响应。部署容器时需保持 SSH 配置、可信公钥、数据库和 `DEER_FLOW_HOME/reconstructions` 持久化。

## API 与恢复

原 `POST /api/reconstructions` multipart 增加：

| 字段                | 说明                                     |
| ------------------- | ---------------------------------------- |
| `preprocessing`     | `none`（默认）或 `flux3`                 |
| `preprocess_prompt` | 可选，最多4000字符；空值使用固定默认指令 |
| `preprocess_seed`   | 可选，默认42，0到2^53−1                  |

提示词、种子和融合 profile 参与请求指纹。原请求重试复用任务；更改提示词、精度或素材应创建新请求 ID。默认直接路径保留原指纹，旧请求仍可读取和重试。服务端返回 `preprocessing`、`pipeline_profile` 与 `preprocess_progress: {completed,total}`，不返回部署路径或凭据。

每帧先持久保存 ComfyUI `prompt_id`，再按 `/history/<prompt_id>` 的输出记录取图，不根据「最近生成文件」猜结果。监督进程的 `.started` 保证同一任务不重复启动；Gateway 重启后继续读取同一任务，不重新提交推理。当前没有自动失败重试、自动训练断点恢复或跨任务结果复用。

取消时只删除本任务尚在 ComfyUI 队列中的 prompt；若已经执行，等待本张完成后停止后续步骤，不调用全局 `/interrupt`。COLMAP/Brush 只终止该适配器自行创建的进程组。连接断开导致取消尚未送达时，仍显示真实待取消/连接状态。

融合结果使用版本化 `pipeline_result.json`，不伪造原生 OOOSplat `project.json`。任务目录包含原件、`original_frames`、COLMAP 几何、`undistorted`、`flux_edits`（工作流与逐图回执）、`dataset/images`、`dataset/sparse/0`、日志与 `final.ply`。只有完成回执及任务目录内有效PLY通过现有大小/字段/SHA检查，才提供完成下载。

## 本轮实际验证

- 复用反重力原乐高素材、原相机信息选取重叠视角，以及既有 FLUX3/OOOSplat 部署；没有覆盖原项目或安装新重建引擎。
- 首轮均匀16图只注册2图，旧试验适配器编辑2张并生成1,604高斯，仅证明初始接口连通，不作为完整16图验收。后续实现修正为保留全部输入的预处理记录。
- 第二轮选取重叠充分的16图，任务 `453023c9-568e-4537-98fb-54774756bcdd`：16/16相机注册、16/16真实FLUX编辑、fast档8,000步，Brush用时44.027秒；生成17,853高斯、4,214,858字节原生彩色PLY。
- SHA256：`dc20be3dc2d5b6bf559ef5fb4122a637679b2cfcdb7d3e6a81678f65bb052919`。训练后相机SHA保持一致；PLY为SH3/59字段，有限数值、颜色和完整性通过。
- GPU训练使用隔离任务数据库和真实SSH/ComfyUI/Brush，没有向正式地图写测试记录。正常登录正式3000界面后，已验证FLUX配置、可编辑提示词和本轮PLY的临时本地预览；浏览器无异常，无API mock。
- 后端相关专项63通过，地图单元42通过，浏览器16通过、0失败、0跳过；生产构建及代码规范通过。完整后端在修改前后均为同样12个既有收集错误、2 skipped（`deerflow.skills.skillscan.orchestrator` 缺失）。

原始证据在本机扫描项目 `outputs/flux3_connected_integration_20261017/`，产品验证报告在 `reports/integration/2026-10-17/flux3/`；运行产物不属于源码交付。本轮是链路与文件可用性验证，没有独立留出集指标或几何精度对比，不宣称FLUX必然提升重建精度。
