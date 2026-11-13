# 12026 前端加载性能与生产部署

## 2026-10-21 当前已启用

后续文件按钮更新已于本日部署至 `.next-releases/upload-button-20261021-v2`，当前私有env使用该版本目录；原 `.next-production` 保留作为本节性能对照的历史产物。仍使用next start，只更新前端，详见[文件选择与权限](map-upload-button.md)。

已通过 SSH 在宿主应用生产启动补丁，构建成功后仅切换前端。Gateway与Nginx进程及数据库未重启。当前命令为 `next start --hostname 127.0.0.1 --port 3000`，不再按访问编译页面。

私有 `.env` 仅设置 `DEERFLOW_FRONTEND_DIST_DIR=.next-production`，模式使用启动器默认production；没有在该文件固定模式，以保留shell的临时development覆盖。`next.config.js`仅在production且显式配置时使用该目录；开发与其他部署仍用 `.next`。构建自动加入的两条生产types路径保留在tsconfig。生产输出已加入gitignore。

### 同账号、同SSH隧道对照

HTTP耗时含本机到服务器隧道与响应接收；每组首次/再次请求各测一次，非p95或持续负载测试。浏览器为相同1440×1000、新登录context。

| 测量 | 切换前 | 切换后 |
| --- | ---: | ---: |
| 首页 HTTP 首次 | 15.015 s | 0.225 s |
| 评测 HTTP 首次 | 16.005 s | 0.044 s |
| 地图 HTTP 首次（切换前已预热） | 0.259 s | 0.074 s |
| 文献库 HTTP 首次（切换前已预热） | 0.168 s | 0.044 s |
| 浏览器首页主标题可见 | 7.119 s | 0.489 s |
| 浏览器地图“创建模型”窗口可用 | 19.015 s | 0.994 s |
| 浏览器文献库主标题可见 | 17.440 s | 0.146 s |

健康接口此前服务器内部仅1–6ms；CPU与可用内存充足。当前地图目录/点位/模型列表HTTP均200、约21–93ms。OSM瓦片本次返回200，但外部瓦片下载与3D大文件传输仍有自己的网络耗时，不能由本次生产切换保证。浏览器无pageerror；能力接口确认重建和FLUX仍启用。未重新启动GPU训练。

### 构建、切换与回退

13项现有启动器补丁/新目录隔离测试通过；Webpack生产构建142.944秒、退出0、81页。临时13026端口生产登录页探测通过，测试进程退出且端口释放；只切前端耗时5.679秒。前端PID2791318→2868472，Gateway2791198与Nginx2792363未变。当前生产日志位于宿主 `.runtime/logs/frontend.log`。

受保护的宿主备份：`.runtime/page-performance-20261021T071955Z/`。包含启动器、Next配置、私有env、旧PID记录、开发日志、build.log、build-result.json、switch-result.json及本轮修改前文档。私有env与日志不得提交。切换脚本在生产就绪失败时会停止自己启动的进程并恢复旧dev前端；本次无需触发回退。后续手工回退须核实当前PID、停止对应前端、使用development与原.next启动并更新启动器PID记录，不要把整套服务stop当作前端回退。

未来整套 `start.sh start` 默认先完成生产构建再启动服务；在无活动任务的维护窗口才执行stop/start。修改源码后必须重新构建以生效。需要热更新时可使用历史章节中的显式development方式；该历史章节“尚未启用”只描述10月18日状态。

运行测试：`python3 -m unittest discover -s tests -p 'test_native*.py' -v`。本机脱敏验证报告位于扫描项目 `outputs/xingxi_page_performance_20261021/`。

---

# 2026-10-18 历史诊断与未启用阶段

2026-10-18 检查本机启动器与最新前端日志，确认当前命令为
`next dev --webpack`，每个模块在首次访问时按需编译。近期更新和重启后，
连续切换尚未编译的模块，会等待编译完成。

| 页面 | 路由响应耗时 | Next.js 部分 | 应用代码部分 |
| --- | ---: | ---: | ---: |
| 研究项目 | 26.7 秒 | 26.5 秒 | 172 毫秒 |
| 古文展签 | 24.6 秒 | 24.4 秒 | 173 毫秒 |
| 知识图谱 | 24.2 秒 | 24.1 秒 | 174 毫秒 |
| 文献库首次打开 | 4.0 秒 | 3.8 秒 | 115 毫秒 |
| 文献库再次打开 | 18 毫秒 | 约 2 毫秒 | 16 毫秒 |
| 星羲智能体再次打开 | 20 毫秒 | 3 毫秒 | 17 毫秒 |

这组日志定位的是进入页面前的等待；页面显示后的业务接口查询、地图瓦片和
模型文件下载仍需按各自请求观察。上述数字不是生产模式的实测成绩。

## 切换到生产模式

仓库提供了[启动器补丁](patches/native-launcher-production-frontend.patch)：

- 默认 `start` 先执行 `next build --webpack`，成功后通过 `next start` 服务。
- 构建在所有新服务启动前完成，失败时直接退出。
- 保留原有端口、登录代理、Gateway 和数据库配置。
- `DEERFLOW_FRONTEND_MODE=development` 可显式恢复开发模式。

启动器位于本编码环境可写范围之外，须在宿主普通终端应用补丁并重启：

```bash
patch --forward --backup --suffix=.before-production-frontend --fuzz=0 -p1 \
  -d /data/laikai/heikesong/deerflow-native \
  -i /data/laikai/deer-flow/docs/patches/native-launcher-production-frontend.patch
bash /data/laikai/heikesong/deerflow-native/start.sh stop
bash /data/laikai/heikesong/deerflow-native/start.sh start
```

首次应用时只执行一次 `patch`；若提示补丁失败，先检查输出，不继续切换。
启动会先完成构建，随后访问 `http://localhost:12026`。以后正常执行 `start`
也默认使用生产模式。前端源码修改后须重新启动以构建新页面。

需要继续开发、使用热更新时，先停止服务，再显式启动开发模式：

```bash
bash /data/laikai/heikesong/deerflow-native/start.sh stop
DEERFLOW_FRONTEND_MODE=development \
  bash /data/laikai/heikesong/deerflow-native/start.sh start
```

如需撤销补丁，在停止服务后用同一补丁执行 `patch --reverse --fuzz=0 -p1`。

## 验证记录

补丁已对当前宿主启动器完成只读试应用。离线回归使用临时启动器和模拟服务，
验证默认生产启动、显式开发模式、构建顺序、失败不启动服务、配置保留及非法
模式拒绝；不监听端口、不修改宿主文件。连同原有地址复用补丁，共 10 项通过。

```bash
python3 -m unittest discover -s tests -p 'test_native*patch.py' -v
```

当前代码的 Webpack 生产构建已通过，生成 81 个页面。生产服务尚未在本次
排查中启动；宿主切换后须用同一登录账号依次打开各模块，确认日志不再出现
访问时的 `Compiling /workspace/...`，再比较实际页面与接口耗时。

原始日志摘录、启动器备份与测试结果位于
`/tmp/xingxi-workspace-loading-zm12kzj9/`。
