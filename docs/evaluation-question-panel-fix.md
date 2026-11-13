# 自动评测题库窗口修复

## 原因

人工题库与自动题库都注册了 `GET/POST /api/operations/evaluations/cases`。真实 Gateway 先挂载人工评测，因而 GET 返回人工题库数组。自动评测的“测试问题与方法”窗口预期包含 `cases`、`methods` 的对象，渲染时访问缺失的 `methods.find` 导致报错。之前仅挂载自动评测单个路由的测试没有覆盖此冲突。

## 改动

自动题库统一使用 `/api/operations/evaluations/questions` 及其删除、恢复子路由。人工题库接口保留。前端读取校验 `cases`、`methods` 数组，异常响应进入已有错误和重试界面。未变更数据库结构、已存题目、固定回放方法、批次快照或权限规则。

## 生效

Gateway 必须与前端代码一起更新。宿主 Gateway 没有热重载，在服务器普通终端执行：

```bash
bash /data/laikai/heikesong/deerflow-native/start.sh stop
bash /data/laikai/heikesong/deerflow-native/start.sh start
```

之后刷新 `/workspace/evaluations`，点击“测试问题与方法”，展开任一道题的“查看测试方法与判定规则”。若前端以生产模式运行，先按现有部署方式重新构建。当前编码环境不能操作启动器的 `.runtime` 或连接宿主服务，没有执行宿主重启。

## 验证

新增真实 `create_app()` 路由冲突回归及集成请求，覆盖人工数组和自动 30 题、10 种方法互不混用，管理员新增、删除、恢复，治理用户只读。SQLite/HTTP 原有题库测试继续覆盖实际持久化和历史快照保留。

- 后端相关专项 24 项通过；日志 `/tmp/xingxi-question-panel-backend.log`。
- 前端相关专项 17 项通过，覆盖新路径及无效数组响应被拒绝；日志 `/tmp/xingxi-question-panel-frontend.log`。
- 新测试在修复前复现 3 项后端、2 项前端失败。新增浏览器回归覆盖异常后的重新读取及方法展开。
- `pnpm check` 通过，保留图谱组件原有 4 条 warning；所改 Python Ruff lint/format 与前端 Prettier 通过，`git diff --check` 通过。
- 后端完整执行修改前后均在 `tests/blocking_io/test_persistence_bootstrap.py::test_bootstrap_offloads_alembic_stamp_and_upgrade` 断言失败，使用首个失败停止（26 passed、2 skipped、1 failed）；不能声称全量通过。日志 `/tmp/xingxi-question-panel-full-before.log`、`/tmp/xingxi-question-panel-full-after.log`。
- 3 条题库浏览器用例可收集；尝试管理员操作和异常恢复两条用例时，Chromium 因 `sandbox_host_linux.cc: Operation not permitted` 无法启动，未进入页面断言。日志 `/tmp/xingxi-question-panel-browser.log`。宿主浏览器验收尚未完成。

## 题库地址返回 404 的兼容处理（2026-10-18）

宿主现有 Gateway 日志实际记录了 `/questions` 连续返回 404、`/catalog` 返回 200。当前宿主启动器没有 `--reload`，本次代码与正在运行的服务接口未同步；编码环境无法连接宿主入口，启动器运行目录也不在可写范围内，因此没有执行宿主重启。

前端仅在 `/questions` 返回 404 时读取服务端 `/catalog`。此路径校验回放模式、题目正文及规则字段，保留服务端实际数据，不读取本地演示题库或人工 `/cases`，不推断缺失的内置 / 自定义身份。页面继续提供搜索和判定规则查看；暂时隐藏新增、删除、恢复、单题运行与已删除筛选，明确显示可用范围和重新读取。服务更新后重试会再次访问 `/questions`，恢复完整功能。

权限拒绝、服务器错误和取消请求不触发兼容读取；两个地址都缺失时显示“评测题库暂不可用，请更新并重启评测服务后重试。”，不再直接展示 `Not Found`。窗口的加载失败通过显式按钮重试，避免连续自动请求缺失接口。

本次兼容修复验证：24 项前端专项、7 项当前 Gateway 路由 / 题库专项通过；`pnpm check`、所改文件 Prettier 和 `git diff --check` 通过。后端在沙箱内使用现有测试专用轮询循环解决线程唤醒限制，产品循环未改。4 条题库浏览器用例可收集；没有在当前环境执行页面断言或宿主重启。日志：`/tmp/xingxi-question-404-tests.log`、`/tmp/xingxi-question-404-final-tests.log`、`/tmp/xingxi-question-404-backend-polling.log`、`/tmp/xingxi-question-404-final-check.log`。
