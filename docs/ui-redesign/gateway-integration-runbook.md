# 真实 Gateway／数据库全链路演练准备

状态：**已准备演练步骤，未执行真实联调**。本轮未启动 Gateway／数据库、未迁移业务数据、未修改现有配置或创建账号。浏览器 Mock 成功不等于下面的真实环境验收。

## 本机已核对的条件

2026-10-15 16:03（Asia/Shanghai）的只读快照见 [environment-readiness.json](../../reports/ui-redesign/2026-10-15/closeout/environment-readiness.json)。这是当时状态，启动前应重新检查。

| 项目 | 当前证据 | 演练前动作 |
| --- | --- | --- |
| 数据库配置 | 当前 config.yaml 选择 SQLite；未测试数据库连接 | 确定使用独立 SQLite 测试目录或独立 PostgreSQL 测试库，保留现有业务库 |
| Gateway | `http://127.0.0.1:8001/health` 不可达 | 启动后验证健康响应及数据库初始化日志，不能只看进程存活 |
| 入口服务 | 快照未见 2026／8001／3000 的本机监听 | 准备 Nginx、Gateway、Frontend；浏览器统一走 2026 |
| Docker／WSL | 命令存在；默认 Docker engine pipe 未就绪；未探测其他 context | 若走容器，先确认选定 Docker context 的引擎可用及 PostgreSQL healthcheck |
| 本机工具 | Python 和 backend/.venv/Scripts/python.exe 存在；当前 PowerShell PATH 找不到 uv／make | 确认 Python 依赖、uv／make 所在 shell，或使用仓库部署脚本对应的环境 |
| 配置文件 | config.yaml、根 .env、frontend/.env 存在；未输出密钥内容 | 核对所需变量、文件权限与环境引用，不能把“文件存在”视为配置有效 |

PostgreSQL 的生产 overlay 不暴露宿主机 5432，宿主机无此监听不能证明容器内数据库不可用。尚未检查远端环境、数据库账户、扩展、模型可用性或真实 SSO。

## 环境与启动顺序

1. 选定一次性演练环境与数据负责人。记录代码版本、测试库标识、服务入口及测试账号角色。使用独立 `DEER_FLOW_CONFIG_PATH` 配置与 `DEER_FLOW_HOME` 数据目录；确认实际启动脚本使用这些路径，避免把演练写入现有业务库。
2. 选择数据库。SQLite 适合本机功能演练，但不能作为 PostgreSQL 方言／并发兼容的通过证据。若选 PostgreSQL，使用独立库，配置 `database.backend: postgres`、`database.postgres_url: $DATABASE_URL`。连接信息通过环境或受控配置提供，不写进报告。
3. 容器生产路径复用根 `make up` 对应的 `scripts/deploy.sh`；脚本根据 postgres 配置加载 `docker/docker-compose.postgres.yaml`。当前 PowerShell 没有 make，须在具备依赖的 shell 中使用，不能宣称本机已可直接启动。普通开发入口为 `make dev`，生产本机入口为 `make start`；均需先核对配置／工具，不在本次收尾中执行。
4. PostgreSQL 镜像与健康检查以现有 overlay 为准：当前是 pgvector/pgvector:0.8.1-pg17-bookworm。Gateway 启动时通过 `bootstrap_schema` 自动执行 Alembic upgrade head；检查日志与最终 schema revision。不要凭空另造一条 `make migrate` 命令。确认词法检索 pg_trgm 和向量扩展具备实际能力；未配置向量服务时明确跳过向量质量验收。
5. 准备鉴权。真实联调关闭 `DEER_FLOW_AUTH_DISABLED`，用本地初始化流程建立测试管理员，再准备普通读者、项目管理、治理读取／审核账号。按实际入口设置前后端信任来源，确保 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` 指向真实 Gateway；OAuth 回调、Cookie、CSRF 与内部令牌由现有认证配置管理。
6. 先起数据库与 Gateway，检查 `/health`、setup-status、登录／me、授权拒绝及持久化，再起 Frontend／Nginx，浏览器统一访问 `http://localhost:2026` 或事先选定的域名。Nginx 将 `/api/langgraph/*` 重写到 Gateway 运行时路径；普通 `/api/*` 仍走 Gateway，不用 UI 检查端口 3106／3107 代替正式代理链路。
7. 首轮保持后台 scheduler 关闭，先完成手工运行和取消。需要验证定时任务时再在独立环境启用 `scheduler.enabled`，核对只运行一个调度实例；记录真实触发、运行 ID、时区与失败状态。需要重启恢复验证时，先确认 run-events 与所需状态使用持久化配置，不能用默认内存状态推断可恢复。

以上是执行顺序，不是本轮已完成动作。账号、数据库及模型环境确定后再执行依赖它们的演练，不向现有配置自动填入占位密钥。

## 一条最小完整业务链

| 顺序 | 真实操作与应观察的结果 | 需要保留的证据 |
| --- | --- | --- |
| 1 | 管理员登录；普通用户不能读取管理拒绝列表或提交审核／发布 | 角色与 capability、401／403、Cookie／CSRF 行为；不记录令牌 |
| 2 | 上传有授权的少量测试原件，依次观察 parse／OCR／clean／chunk 到 awaiting_review | source／file／job ID、逐步事件、原始与清洗文本及哈希、真实页码 |
| 3 | 对照原件、按页与片段复核；争议／退回无意见应被服务端拒绝；审核记录可回查 | 精确页面代次、ChunkSet、意见与审核历史，失败重试结果 |
| 4 | 所有引用页和片段满足门禁后显式 finalize；完成复核仍不等于发布 | 门禁成功／失败响应与入库 Job 后续状态 |
| 5 | 发布一个知识版本，观察 preparing／ready／active；旧 state_version 冲突必须失败 | Release ID／version／manifest hash、指针和状态版本；准备失败／重试与回滚记录 |
| 6 | 首页或项目发起真实研究：检索只命中授权、正确 Release 与项目范围的资料 | thread／run ID、查询条件、引用定位、服务端冻结的 Release 元数据 |
| 7 | 聊天流式回答、停止、历史刷新、Evidence Inspector 与文献深链接一致 | 原文摘录、物理页／叶码、Run 终态与历史事件 seq，错误与恢复截图 |
| 8 | 地图与图谱只显示真实返回记录；争议、坐标不确定性与出处保留 | 记录 ID／Evidence ID／Release；地图署名、GLB 许可与单实例加载情况 |
| 9 | 展签保留原文／出处／待考；异名歧义不自动选名；反馈核对返回真实会话 | 原件对照、候选与依据、反馈 ID 与处理历史，不编造回答快照 |
| 10 | 管理员触发评测并查看记录，读取角色不能执行；启用测试任务后核对真实触发 | 批次／case、run／task、取消与重试、调度时区及终态 |
| 11 | 重启并复核会话、项目文献、审核、Release、任务状态；抽查撤销来源授权后检索失效 | 重启前后 ID 与内容一致、当前授权生效；不把缓存命中当作数据库恢复 |

实际影印接口目前展示上传的原文件。ReviewQueue 没有独立 OCR 页图和区域坐标，这轮演练应验证真实原件可达和文本页码对应；不能把没有实现的区域框作为已通过项目。

## 报告与结束条件

- 每次演练用独立目录保存版本／环境摘要、请求结果、截图与日志，关联 source、job、ChunkSet、Release、thread、run、task 和 evaluation ID。报告不包含账号密码、Cookie、Authorization header 或数据库 URL。
- `/health` 通过、流程终态正确、数据库状态持久、权限拒绝正确及人工确认史料质量分别判定；任何一项未测即保留未验收。
- 固定回放可复用 `make eval-smoke`／`make eval-agent`，它们启动隔离真实 Gateway 与脚本模型。回放通过只能证明软件协议，不证明真实模型或生产数据库质量，详见 [Agent 测试文档](../agent-evaluation-testing.md)。
- 真实模型／OCR 服务需要确定已有可用配置和调用预算后执行；本轮没有发起真实模型调用。首次真实演练结束后再依据证据更新 QA 和问题状态。
- 保留原环境与报告；演练结束的停服、测试数据清理按具体环境和负责人约定处理，不自动清空或覆盖已有数据。
