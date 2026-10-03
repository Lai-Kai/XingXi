# 首版实施与验收记录

日期：2026-09-26。用户已授权修改代码。本次交付自动回放、持久化记录、运营页面与软件报告入口；没有调用真实付费模型。

## 现在可以查看的产物

- [Agent 实际运行报告](../../reports/testing/implementation/agent-report/index.html)：可离线打开，展开用例查看回答、期望/实际、引用原文与工具时间线。
- [同批 Markdown](../../reports/testing/implementation/agent-report/summary.md)、[完整 JSON](../../reports/testing/implementation/agent-report/results.json)、[CSV](../../reports/testing/implementation/agent-report/results.csv)、[文件校验清单](../../reports/testing/implementation/agent-report/manifest.json)。
- [全量软件测试记录](../../reports/testing/software-20260926T114005Z-61d55101/index.html)：保留当前项目的测试收集失败和本机环境错误，没有删除失败记录。
- [相关后端检查 JUnit](../../reports/testing/implementation/backend-focused.xml)、[运行日志](../../reports/testing/implementation/backend-focused.log)、[修改前后端基线日志](../../reports/testing/implementation/backend-baseline.log)。
- [使用说明与覆盖边界](../../docs/agent-evaluation-testing.md)。

上述报告是当前工作区的本地产物，位于 gitignored 的 `reports/testing/`；其他机器可用 Make 命令重新生成。页面入口为 `/workspace/operations` → 回归评测 → Agent 自动评测。重启 Gateway 后自动执行迁移。

## 实际验证结果

| 检查 | 结果 | 范围与限制 |
| --- | --- | --- |
| 完整固定模型回放 | 30/30 通过 | 10 类场景 × flash/pro/ultra；实际创建 33 个独立 Run ID，多轮场景各有两次 Run |
| 后端相关回归 | 26 项通过 | 评分反例、取消确认、权限、导出、幂等、并发 claim、失效租约、不可变结果、人工复核、旧 API 兼容、迁移升级/重复升级/降级、报告失败留存 |
| SQLite 真实链路 | 通过 | 新建控制数据库与子 Gateway 数据库；真实认证、Release 发布/索引、动态授权、工具调用和日志读取 |
| 报告完整性 | 通过 | 四种报告已生成，manifest SHA-256 与实际文件一致 |
| Python 静态检查 | 通过 | 修改文件 Ruff check 和 format --check；git diff --check 通过 |
| TypeScript 静态检查 | 通过 | 全项 tsc --noEmit；修改文件 ESLint 通过 |
| 后端全量基线/实施后全量 | 未通过 | 前后均有 12 个 collection error、2 个 skipped；缺少原有 `deerflow.skills.skillscan.orchestrator`，不能把未收集到的测试计为通过 |
| 前端 Rstest | 环境阻塞 | 启动时报 `listen EPERM 127.0.0.1:3000`，新增前端单元用例未能执行 |
| 模拟后端浏览器套件 | 未完成 | 本次 webServer/build 阶段超出 90 秒执行限制，保留超时记录；没有产生可以认定为验收截图的附件 |
| 真实前后端浏览器套件 | 环境阻塞 | `uv` 在只读 `/home/laikai/.cache/uv` 下创建锁失败，webServer 未启动；报告包含真实启动错误 |
| PostgreSQL | 未运行 | 本次验证使用 SQLite；PostgreSQL 方言兼容尚需实际数据库验收 |

本机沙箱还阻止 asyncio 的 socket 唤醒，因此后端验证命令使用了只位于 `/tmp/xingxi-loop-poll/sitecustomize.py` 的临时定时唤醒辅助。它没有进入仓库或生产代码，也没有替换 Agent、数据库、工具或评分行为。正常部署不需要该辅助。为保留既有运行环境的 Python 启动辅助，评测子进程保留受信任部署 `PYTHONPATH` 的顺序。

实际成功批次：`70ae6485-2de7-4c57-a9b8-507b4f4d20bc`。冻结 Release：`release-aaa4d54719fa42db875643a055d32473`。完整实际环境、语料/提示词/代码指纹与每个 Run ID 均在 JSON 中。该批次来自 CLI 隔离数据库，不会自动出现在业务页面；页面可以启动自己的新批次。

## 范围说明

原方案第 7 节提出的 30 类领域问题是扩展目标；本次实际用例是 10 类流程场景在 3 种模式中的 30 项执行。六类核心纵向场景已打通；真实史料正确性、冲突解释、Release 切换等更多场景仍需专门数据与用例，不宣称已经覆盖。

固定脚本模型在真实星羲流程中运行，可以发现工具契约、引用过滤、授权、取消和记录回归；它无法证明真实模型的规划、回答质量或抗提示注入能力。真实模型、辅助评分、A/B 比较和费用基线均未实现；没有把这些能力伪装为通过或费用为零。

浏览器用例已加入 `frontend/tests/e2e/agent-evaluations.spec.ts`，覆盖失败详情、人工复核、导出、重跑、取消与刷新记录，但本次未实际通过浏览器验收。后续在允许监听端口的开发机或 CI 执行该场景，再完成页面验收。

## 主要代码位置

- `backend/app/gateway/evaluations/`：服务端用例、合成语料、隔离执行、确定性评分、队列服务、API、CLI、导出。
- `backend/packages/harness/deerflow/persistence/operations/evaluations.py`：持久化尝试和复核、全局租约、幂等键。
- `backend/packages/harness/deerflow/persistence/migrations/versions/0044_agent_evaluations.py`：兼容旧人工记录的增量迁移。
- `frontend/src/components/workspace/agent-evaluations.tsx` 与 `frontend/src/core/operations/evaluations.ts`：运营面板与 API 契约。
- `scripts/testing_report.py`、根 Makefile、Playwright/Rstest 配置和 CI：执行入口与可追溯报告。

开源参考沿用 pytest、Rstest、Playwright，借鉴 Promptfoo 的用例/断言组织；无需安装独立评测平台。Langfuse 等外部追踪在本版隔离回放中关闭。
