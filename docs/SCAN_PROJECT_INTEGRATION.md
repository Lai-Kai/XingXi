# 扫描项目操作与服务器连接继承指南

本指南记录星羲项目（XingXi）对 `c:\Users\蒲煜元\Desktop\扫描`（Windows 多视角 3D 扫描项目）全部操作与服务器连接的继承、配置和使用方法。

---

## 一、服务器环境与连接配置

### 1. 硬件与环境概况
- **服务器配置**：Ubuntu 20.04 x86_64，4× NVIDIA GeForce RTX 4090 (48GB 显存/张)，377GB 内存。
- **主机与端口**：`192.168.134.38:22`
- **用户与路径**：用户 `yuyuan`
  - 主流水线根目录：`/data/yuyuan/scan`
  - 生成式/实验模型目录：`/data/yuyuan/a2g`（包含 TRELLIS.2、Hunyuan3D、PointDiT 等）
- **凭据文件**：`.cache/server_ssh.json`（已加入 `.gitignore`，严格保密，禁止提交至代码仓库）。

### 2. TUN 代理/VPN 穿透机制
- **问题排查**：当本地开启 Sing-box / Clash Verge 等 TUN 虚拟网卡（`tun0`，默认路由 `0.0.0.0/0`）时，对端 `192.168.134.38` 的 SSH 握手会被 TUN 代理接管并直接断开（`Error reading SSH protocol banner`）。
- **解决方案**：在 `scripts/remote.py` 中实现了 `_get_ssh_socket` 自动探测机制。当直接连接受阻时，会自动枚举本地物理网卡（如 WLAN `10.70.93.88`）建立底层 Socket 绑定，确保在任何代理/VPN 环境下均可秒级稳定直连 GPU 服务器。

---

## 二、继承的操作命令与脚本

### 1. 远程命令执行与传输 (`scripts/remote.py`)
使用 `worldmirror_env` 或系统 Python（需安装 `paramiko`）：

```powershell
# 1. 执行远程命令（自动避开 TUN 代理）
python scripts/remote.py exec "nvidia-smi"

# 2. 上传文件或文件夹到服务器
python scripts/remote.py upload <本地路径> <远程路径>

# 3. 从服务器下载单文件
python scripts/remote.py download <远程路径> <本地路径>

# 4. 更新/保存服务器配置
python scripts/remote.py save --host 192.168.134.38 --user yuyuan --password <密码> --port 22
```

### 2. 服务器成果同步 (`scripts/sync_server_results.py`)
用于从服务器自动拉取 3D 重建最终产物（`final.ply`、`manifest.json`、`turntable.mp4`、`metrics.json`、对比图）：

```powershell
# 同步服务器最新一次运行成果（保存至 outputs/server_sync/<run_id>/）
python scripts/sync_server_results.py

# 同步指定 run_id 成果
python scripts/sync_server_results.py --run run_20260815_021412
```

### 3. 服务器只读快照巡检 (`server_snapshot.py`)
```powershell
python skills/custom/scan-server-ops/scripts/server_snapshot.py snapshot
python skills/custom/scan-server-ops/scripts/server_snapshot.py run-status --run-id <run_id>
python skills/custom/scan-server-ops/scripts/server_snapshot.py batch-status --remote-dir /data/yuyuan/a2g/...
```

### 4. OOOSplat 项目服务器部署与运行
已在服务器 `/data/yuyuan/ooosplat` 部署原生无 Docker 运行架构，解决 Ubuntu 20.04 宿主 glibc 2.31 与 OOOSplat 预编译要求 glibc 2.39 的兼容问题：
- **可执行脚本**：`/data/yuyuan/ooosplat/bin/splatstudio`
- **四大引擎**：`/data/yuyuan/ooosplat/engines/`（FFmpeg、FFprobe、CUDA COLMAP 3.13.0、Brush-cli 0.3.0）
- **常用命令**：
  ```bash
  # 1. 四项引擎健康检查
  /data/yuyuan/ooosplat/bin/splatstudio health

  # 2. 图像/视频序列元数据探查
  /data/yuyuan/ooosplat/bin/splatstudio probe /path/to/images

  # 3. 抽帧与采样规划
  /data/yuyuan/ooosplat/bin/splatstudio plan /path/to/images

  # 4. 端到端重建与 3D 高斯模型导出
  /data/yuyuan/ooosplat/bin/splatstudio generate --projects-root /path/to/projects --quality fast /path/to/images
  ```

- **已实测产出结果**：
  1. **历史大规模生产产物**：`/data/yuyuan/ooosplat-data/projects/yongfu_fine_gpu3_20260921_220955/20260921-141041_yongfu_fine_20260921_214601/final.ply`（248MB，63 张单反原图全管线完整产出）。
  2. **测试图实机验证**：针对 24 张测试图运行 `splatstudio generate`，总耗时 62 秒，顺利完成抽帧、SIFT 特征提取、匹配、SfM 稀疏重建与 Brush 8000 步 GPU 训练，成功在 `/data/yuyuan/ooosplat/workspace/live_all24/20261015-173151_images/` 导出 `final.ply`（2.16MB，9,162 个高斯点，球谐阶数 SH 3，binary little-endian 格式）。
  3. **官方推荐基准视频实测验证（无本机历史素材）**：采用 3DGS/NeRF 领域官方权威学术基准 **Mip-NeRF 360 `bonsai`** 连续环绕序列合成的官方推荐视频（`official_bonsai_orbit.mp4`，6.0 秒，72 帧，448×294），升级引擎链接至现代 FFmpeg/FFprobe 8.1.2（彻底解决老版本不支持 `stream_side_data` 导致的视频探针异常），全自动端到端耗时 **52.4 秒**（Brush 训练 45.0 秒，COLMAP 重建 7.4 秒），**相机位姿注册率 100%（22/22 帧全部成功注册）**，解算三维特征点 1,545 个，并在 `/data/yuyuan/ooosplat/workspace/official_projects/20261015-180711_official_bonsai_orbit/` 成功导出 `final.ply`（**9.18MB，38,880 个高斯点，SH 3 阶球谐**）。

---

## 三、继承的自定义技能 (Skills)

已将扫描项目的全套工程与实验技能平移至 `skills/custom/`（本地独立维护）：

1. **`scan-server-ops`**：
   - 职责：远程 GPU 状态巡检、进程与显存占用审计、只读任务查询、结果校验。
2. **`scan-3d-model-run`**：
   - 职责：多模型 3D 生成调度（Hunyuan3D-2.1、TRELLIS、InfiniSplat、PointDiT 等）。
3. **`scan-experiment-control`**：
   - 职责：状态机实验轮次控制、账本与证据管理、阶段推进。
4. **`scan-quality-gate`**：
   - 职责：高斯模型/点云质量判定、指标协议核验、防过拟合与瑕疵过滤。
5. **`scan-agent-handoff`**：
   - 职责：Agent 之间的实验上下文安全交接、租约检查与防重复启动。

---

## 四、扫描数据资产与木渎古镇实体的关联

`c:\Users\蒲煜元\Desktop\扫描` 中的点位照片与三维模型，是星羲项目木渎历史地理实体的重要数据支撑：

| 地理点位 / 文物实体 | 扫描项目对应路径 | 资产类型与可用成果 |
|---|---|---|
| **木渎古镇总体** | `地图照片/木渎古镇/` | 场景全景照片、总体概貌 |
| **严家花园** | `地图照片/严家花园/` | 园林建筑多视角环绕组图 |
| **古松园** | `地图照片/古松园/` | 古松园砖雕、庭院多视角组图 |
| **榜眼府第** | `地图照片/榜眼府第/` | 冯桂芬故居建筑与细部图片 |
| **虹饮山房** | `地图照片/虹饮山房/` | 戏台、园林空间环绕图组 |
| **明月古寺** | `地图照片/明月古寺/`、`round_ooosplat_mingyue_single_*` | 古寺构件、三维点云试验成果 |
| **永安桥** | `地图照片/永安桥/` | 古桥石构件与多视角图 |
| **永福桥** | `round_ooosplat_yongfu_*`、`round_xfeat_yongfu*`、`spirula_smoke_yongfu*` | 完整的 3DGS 高斯模型与点云（`final.ply`，含 SH3 高保真色彩与几何） |
| **灵岩山 / 灵岩山寺** | `地图照片/灵岩山/`、`地图照片/灵岩山寺/` | 吴王夫差馆娃宫遗址、灵岩塔等图像与空间参照 |

星羲古舆地图与研学模块可直接引用上述资产进行 3D GLB/PLY 互动呈现。

---

## 五、环境与大模型凭证同步

已将扫描项目的核心 API Key 同步至星羲根目录 `.env`：
- **DeepSeek 官方 API**：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL=deepseek-flash`
- **StepFun（阶跃星辰）官方 API**：`STEPFUN_API_KEY`、`STEPFUN_BASE_URL`、`STEPFUN_MODEL=step-5-preview`
