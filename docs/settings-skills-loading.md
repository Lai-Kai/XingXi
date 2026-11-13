# 设置中的技能列表加载修复

## 原因与改动

宿主 Gateway 日志中 `GET /api/skills` 持续返回 404。技能路由没有注册到实际应用，且其依赖的原生静态扫描模块在历史提交 `71412c01` 中被删除，直接导入路由也会报 `ModuleNotFoundError`。

本次从该提交的父版本恢复原有 `skillscan/orchestrator.py`，重新注册既有技能路由。列表读取实际技能文件；普通用户可读，启停与管理仍要求管理员；安装、编辑与回滚继续使用原有扫描实现。没有更换为模拟技能列表。

设置页加载失败时增加“重新加载”，请求进行中禁用该按钮，权限错误保留独立提示。

## 本机生效

宿主启动器的 Gateway 没有 `--reload`，需要在服务器普通终端重启服务：

```bash
bash /data/laikai/heikesong/deerflow-native/start.sh stop
bash /data/laikai/heikesong/deerflow-native/start.sh start
```

本次编码环境不能写入启动器的 `.runtime` 目录，也不能连接宿主服务，因此没有执行宿主重启。前端若使用生产构建，也需按现有部署方式重新构建并启动。

服务启动后打开设置 → 技能，必要时点“重新加载”，应能看到真实内置技能；管理员切换启停后重新打开，应保留所选状态。

## 验证记录

回归覆盖真实 `create_app()` 路由、临时目录中的实际技能解析、空技能目录、普通用户写入拒绝、管理员启停保存与重新读取，以及动态执行脚本仍被原生扫描拦截。另直接用本仓库当前配置读取实际技能目录，成功返回 23 个内置技能。前端回归覆盖中文失败提示、手动重试、请求中禁用、权限提示及成功列表；浏览器用例覆盖后台恢复后重新加载。

- 后端专项：171 项通过；日志 `/tmp/xingxi-skills-backend.log` 和 `/tmp/xingxi-skills-safety.log`。
- 前端专项：14 项通过；日志 `/tmp/xingxi-skills-frontend.log`。
- `pnpm check` 通过，保留图谱组件既有 4 条 lint 警告；日志 `/tmp/xingxi-skills-check.log`。
- 后端全部 8460 项测试成功收集，原有 12 个扫描模块缺失收集错误消除。完整执行仍遇到未修改的持久化测试 `tests/blocking_io/test_persistence_bootstrap.py::test_bootstrap_offloads_alembic_stamp_and_upgrade` 失败，首个失败停止记录为 26 passed、2 skipped、1 failed；不能声称全量通过。日志 `/tmp/xingxi-skills-full-first-failure.log`。
- 浏览器恢复用例可成功收集，实际执行在 Chromium 启动阶段因 `sandbox_host_linux.cc: Operation not permitted` 失败，未进入页面断言；日志 `/tmp/xingxi-skills-browser.log`。未完成宿主浏览器验收。
- 改动 Python 的 Ruff lint/format 和 `git diff --check` 通过；恢复的扫描实现与删除前历史版本逐字一致。
