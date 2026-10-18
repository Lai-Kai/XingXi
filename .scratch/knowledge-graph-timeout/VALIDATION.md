# 验证记录（2026-10-17）

- 原生部署日志中页面 `/workspace/knowledge-graph` 返回 200，而总览和主体目录多次返回 504；Nginx 错误明确为等待 Gateway 响应头超时。
- 当前真实 SQLite 约 2.4 GiB，包含 78,984 条 Evidence、300 个主体、530 条关系。仅通过 `mode=ro&uri=true` 连接读取，未更改业务数据或发布状态。
- 原版本仓储查询在 100 秒超时终止前仍停留在整版 Evidence 查询。
- 修复后仓储总览 0.848 秒，主体目录 0.851 秒。通过真实 FastAPI 路由、ASGITransport 和只读数据库验证，总览返回 HTTP 200 / 0.742 秒，目录返回 HTTP 200 / 0.646 秒；当前授权和版本范围内均有 16 个主体、12 条关系。此验证使用独立进程内的测试管理员依赖，没有修改运行服务的鉴权。
- 新增的总览/目录性能回归先失败，确认原实现加载未被图谱引用的 Evidence；修复后通过。另覆盖同一资料在单次请求内复用授权、下一次请求立即识别撤销授权。
- 图谱总览、接口、审核纠错、持久化和 Agent 工具五个测试文件共 41 项回归全部通过（69.29 秒）。
- 修改前完整后端测试在收集阶段因缺少 `deerflow.skills.skillscan.orchestrator` 等既有模块出现 12 个错误；修改后仍是同样的 12 个收集错误。
- 前端图谱总览 3 项单元测试和 TypeScript 检查通过。浏览器回归因沙箱无法启动本地 WebServer 而超时，未视为浏览器验收通过。
- 修改文件的 Ruff 检查、格式检查及 `git diff --check` 通过。

## 当前运行数据库的修复

用户进一步明确“实体与关系”显示“图谱加载失败，请重试”。2026-10-17 11:05 的最新访问仍是 overview/directory 504。此前仅完成了仓储源码优化，没有让运行中的旧进程恢复，不能视为页面已修好。

继续检查真实 SQLite 的查询计划发现：旧查询每次从 manifest 取出 Chunk 后，通过 `ix_wu_evidence_document_id(document_id)` 扫描整本文献的 Evidence，再按 Chunk ID 筛选；这是重复扫描的直接原因。已有单列 Chunk 索引不足以保证 SQLite 选择正确路径。

- 添加 ORM 和 Alembic `0045_evidence_lookup_index`，提供非唯一 `ix_wu_evidence_chunk_document(chunk_id, document_id)`。
- 新增 SQLite 指令预算测试：1,600 个同文献 Chunk 的查询在旧索引下被工作量上限中断，补齐复合索引后通过；覆盖新建库、重复升级、重复降级和数据保留。
- 通过标准 Alembic 升级将当前原生部署的工作区内数据库从 `0044_agent_evaluations` 升级至 `0045_evidence_lookup_index`，耗时 2.105 秒。升级前后 Evidence、主体、关系、Release、manifest 数量及 active pointer/state_version 均一致。
- 新查询计划明确使用复合索引的两个等值条件。原始查询读取 78,930 行耗时 2.312 秒，之前 100 秒仍未完成。
- 在独立进程中使用当前部署的原版仓储代码、真实 FastAPI 路由和只读真实数据库验证，总览 HTTP 200 / 8.972 秒、主体目录 HTTP 200 / 9.126 秒，返回 16 个主体、12 条关系。此验证无需加载修改后的仓储代码，证明数据库修复对旧服务代码同样有效。
- 索引已在当前数据库生效，不再依赖重启让这部分修复生效。优化仓储源码仍会在下次正常服务重启时加载。受限沙箱仍无法直接连接宿主 HTTP 服务或启动浏览器，已请用户刷新页面确认实际画布。
- 2026-10-17 11:13:26，原生 Nginx 访问日志确认实际页面发出的 `/api/knowledge-graph/overview?scope=all` 请求已返回 HTTP 200（16,160 字节），此前同一路径持续返回 504。
- 最终索引、图谱总览、接口、审核纠错、持久化及 Agent 工具六个测试文件共 43 项回归通过（77.10 秒）。修改文件 Ruff 检查、格式检查及 `git diff --check` 通过。

扩大测试时还发现原 `test_persistence_bootstrap.py` 将 head 固定为 `0040`，已随本次迁移更新为 `0045`。包含完整 bootstrap 的扩展检查结果为 54 通过、7 失败（156.41 秒）；失败集中于遗留库升级的既有 `0033` 外键重建，以及 ORM/Alembic 旧表集合差异，未把它们归因于本次单一索引迁移。新建库升级到 `0045`、当前版本启动，以及本次索引的正反迁移测试均通过。

## 主体总量与页面 16 个的差异

用户刷新成功后追问为什么只有 16 个主体。进一步通过 SQLite `mode=ro`
分解实际查询门禁，确认没有数据丢失，也不是分页上限：

| 范围 | 主体 | 关系 | 当前 manifest 覆盖 |
| --- | ---: | ---: | --- |
| 当前 Release 绑定记录 | 16 | 13 | 全部覆盖；1 条关系已驳回，画布显示 12 条 |
| release-neutral 待复核记录 | 284 | 517 | 无一覆盖 |
| 全数据库 | 300 | 530 | — |

另外 284 个主体、517 条关系均有 Evidence，关联《吴地记》（维基文库公开转录）
和《吴郡图经续记》（维基文库公开转录）。两份资料的授权状态均为
`unconfirmed`，授权用途为空，没有授权变更历史；相关入库任务仍停在
`awaiting_review` / `review`，相关 54 个 Chunk 全部为 `pending`。

当前唯一 Release 在 2026-08-24 创建，284 个主体在 2026-09-05 至 09-06
生成，尚未进入该 Release 的精确 Chunk/文献 manifest。查询本身允许
release-neutral 主体，真正排除原因是其 Evidence 不属于当前 manifest，
而两份来源的现有授权也不允许当前读取用途。这是未完成审核和入版的工作数据，
不是本次性能修复删除或减少了记录。

本轮只读核对数量、Evidence 连接、来源策略、入库状态与时间；没有变更授权、
复核结论、Release、manifest 或业务数据。后续展示需要按实际用途确认来源
授权并纳入新版本，不能通过删除查询门禁替代。

## 用户操作路径核对

继续核对 `SqlKnowledgeReleaseRepository.publish` 后更正：内部工作版允许
待复核 Chunk，前提是来源确有 `internal_processing` 授权，且保留精确清洗页
引用及内容 hash；公开版才强制要求 Chunk 和引用清洗页全部复核通过。
普通图谱读还要求主体、关系及 Evidence 已通过复核，来源允许公开引用。
因此“必须全部复核后才能看到更多主体”不适用于管理员的内部工作版。

现有前端 `/workspace/library` 有“复核”按钮和“知识版本”弹窗，但
`SourceEditDialog` 没有授权表单，`publishKnowledgeRelease` 也不传 `scope`，
故后台默认发布公开版。不能指引用户点击不存在的授权按钮，或把这个发布按钮
当成内部工作版发布。后台已有管理员 `PUT /api/source-documents/{id}/authorization`
和 `POST /api/knowledge-releases`（支持 `scope=internal`）接口。
新 manifest 需要保留现有资料；当前 Release 专属图谱记录也须按正常新版本
准备流程核对延续情况，不能只发布两份新增资料或承诺自动得到全部 300 个主体。
