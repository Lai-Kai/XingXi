# 修正端口预检并恢复启动

Status: ready-for-human

## 实施

`docs/patches/native-launcher-reuseaddr.patch` 在端口预检 bind 前增加 `SO_REUSEADDR`，不改变服务配置、端口、进程管理或业务数据。`tests/test_native_launcher_patch.py` 在临时目录应用实际发布补丁，以合成 socket 覆盖旧逻辑误报、修复后三个端口通过、真实监听仍拒绝、权限错误仍拒绝。README、根 AGENTS 与启动文档已同步。

## 验证

4 项离线测试通过。补丁已成功应用于宿主当前启动器的临时副本，完整文件通过 Python 编译，确认只增加一行。Ruff lint/format、`git diff --check` 通过。没有写入宿主启动器或执行宿主进程操作；宿主端口状态与恢复启动仍待实际终端验收。

## Comments

已向用户请求 `ss -ltnp 'sport = :8001'`；连接回收时间通常已足够，已先提供直接重试 `start` 的恢复步骤。待用户提供监听/启动结果。不能仅凭 EADDRINUSE 断定有残留进程，也不能将正常关闭日志当作全部端口已释放的证据。
