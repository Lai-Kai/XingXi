# 关系与事件支持重复改判及审计

Status: ready-for-agent

范围：knowledge-graph Gateway、SQL Repository、追加审核历史迁移、前端状态/控件/审核列表及相关测试。

## Comments

- 2026-09-14：开始前完整阅读根、前后端 AGENTS；工作区初始无修改。当前环境仓库为 /data/laikai/deer-flow，../PROJECT_PLAN.md 不存在。
- 后端 TDD：先新增真实 SQL/HTTP 测试并运行，7 个测试因旧接口不支持备注/预期状态、缺少管理员驳回查询和迁移而失败，再实现。
- 已实现四状态持续改判、管理员驳回列表、追加历史及并发保护。失败保留状态与输入，成功采用服务端结果。
- 测试环境禁止本地 TCP 监听和 Chromium 所需系统调用；Playwright 用例已添加并尝试执行，浏览器验证受环境限制。Rstest 使用临时无监听编译启动器；后端 SQL 测试使用临时 asyncio 定时唤醒启动器处理沙箱线程唤醒限制，均未修改仓库测试配置或依赖。
- 全量 backend make test 在改动前即有 12 个收集错误，原因是仓库缺少 deerflow.skills.skillscan.orchestrator。
- 2026-09-14 续作验收：复核现有实现，本轮未新增业务代码。后端 `test_graph_review_corrections.py`、`test_knowledge_graph_router.py` 共 19 项通过；`test_graph_persistence.py`、`test_temporal_geo_persistence.py`、`test_relations_events_geo_graph.py`、`test_xingxi_graph_tool.py` 共 18 项通过。使用上次保留的 `/tmp/xingxi_pytest_runner.py` 处理沙箱 asyncio 唤醒限制。
- 前端使用已有 `/tmp/node-v22.14.0-linux-x64/bin/node` 与 `/tmp/xingxi-rstest-offline.cjs`，知识图谱 5 个单测文件共 19 项通过；直接执行项目 eslint 与 tsc（与 `pnpm check` 相同检查）通过。9 个本任务 Python 文件 ruff check / format --check 及 git diff --check 通过。
- 复跑 Playwright 普通用户权限用例，Chromium 在进入页面前因 `sandbox_host_linux.cc:41 shutdown: Operation not permitted` 退出，未执行浏览器断言。保留 ready-for-agent，验收尚缺允许 Chromium 和本地服务运行的环境中的完整 `tests/e2e/knowledge-graph-review.spec.ts`。全量后端先前记录的 12 个收集错误及 harness/app 边界测试失败不属于本次审核修复范围，不能宣称全量通过。
