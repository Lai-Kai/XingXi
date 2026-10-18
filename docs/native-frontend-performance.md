# 本机前端模块首次加载慢

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
