# 星羲弦沚

星羲弦沚是面向吴文化与木渎地域文史的可信智能体。系统以地方志、碑刻、档案和经过审核的研究材料为证据基础，提供可追溯问答、实体关联、历史事件梳理、地图联动和研学辅助。

本项目直接在 DeerFlow 源码基础上重构。DeerFlow 只作为内部 Agent 引擎，提供 LangGraph 编排、流式运行、工具调用、沙箱、记忆、Sub-Agent、线程持久化和前端消息基础设施；它不是用户可见的产品主体，也不是需要用户选择或安装的上层 Agent。

## 当前状态

- 默认且唯一对外运行图：`xingxi`
- 默认前端助手 ID：`xingxi`
- 根路径直接进入星羲弦沚工作区
- 已建立产品级史料约束与无证据回答边界：先说明当前检索范围内暂无明确记载，再保留模型已有的背景分析和待核验方向，并明确标注其未被本地文献核验，不会用固定短句吞掉原回答
- 星羲使用独立的文史研究提示词与领域工具白名单，不向用户宣称底层 DeerFlow 的通用开发、演示或媒体能力；所有入口进入统一聊天页，模型能力由已配置的模型选择器决定，推理强度在聊天输入框内按模型支持情况调整
- 已建立独立 `wu_culture` 领域模型、确定性全文检索和结构化引用契约
- `SourceDocument`、`TextChunk`、`Evidence` 已接入统一 SQLAlchemy/Alembic 持久化，支持 SQLite 与 PostgreSQL
- 星羲运行图的异步 `search_sources` 已读取持久化证据库；数据库为空时仍按契约拒绝无证据回答
- 星羲运行图已注册 `query_knowledge_graph`：可按实体 ID、规范名或已审核别名查询一至三跳关系；空图谱会正常返回空结果，有证据的关系返回书名、卷目/章节与页码定位，仅有推断的关系明确标记为待文献核验
- 知识图谱页面默认展示两层关系网，可切换直接关系或三层关系网；保留外围主体之间的连线并支持查看文献出处，点击主体可在同一知识版本中继续探索。全图总览会按连通分量展示当前知识版本中的独立关系网，避免断开的关系网被当前主体遮住。单次查询最多载入 200 个主体，达到查询上限和图形分页会分别提示，切换层数失败时保留原有图形与选择
- 关系和事件始终标明待复核、已通过、有争议或已驳回，管理员可通过常驻的“修改审核结果”入口继续改判。驳回、有争议和修改已有结论需填写备注，无资料出处不能通过；每次改判追加审核人、时间、前后状态及备注历史。管理员可在“已驳回”列表找回记录，普通查询和图谱画布继续排除驳回内容。审核页签和筛选保留在网址中，刷新后仍可继续审核；改判不改写历史知识 Release、激活指针或已发布资产快照，对外发布沿用后续发布流程
- 史料原件、页图和派生文件已支持受控本地卷与 S3/MinIO；SQL 只保存对象元数据，不保存文件字节
- 管理员可通过 `/api/source-documents` 登记、查看和修改史料来源；同名不同版本或来源机构保留独立稳定 ID，并记录创建/修改审计
- 史料授权采用默认拒绝策略；管理员可登记授权依据、有效期、用途和可见范围，公开访问会自动阻断未确认、撤销、过期或用途不匹配的资料，并保留不可变更的授权审计历史
- 文献库支持管理员把 PDF、PNG、JPEG、DOCX、TXT 和 Markdown 原件上传到已登记来源；上传使用真实网络进度，支持逐文件取消和重试，服务端执行类型/大小校验、批量部分成功、临时文件清理及对象与来源的持久绑定
- 空资料库中也可以先选择待上传文件；弹窗会醒目引导管理员登记首个资料来源，只有真正开始上传仍要求文件绑定来源
- 文件上传按 SHA-256 全局识别重复内容；默认返回已有文件，管理员可选择跨来源引用同一对象或建立显式版本关系，同名不同内容必须确认后才能作为新版本保存
- 文献库提供后端搜索分页、状态筛选、来源元数据编辑和显式“上传新版本”入口；资料量增长时只展开当前页来源及其文件
- 回答反馈支持问题分类和说明并持久化；质量中心按 `quality:read`、`quality:review`、`quality:admin` 分离查看、复核和管理权限，只有复核权限可修改反馈状态与处理意见，只读账号仅能查看详情
- 星羲具备统一的内容安全拒答策略：拒绝会实质促进人身伤害、自伤、性剥削、恶意入侵、诈骗制毒、隐私侵害或仇恨暴力的请求，同时保留历史、学术、新闻、法律、预防和救助语境下的正常研究能力
- 数字 PDF、DOCX、TXT 和 Markdown 可解析为带原页号的有序正文块；标题、段落、表格和脚注标记及声明元数据保存到 SQLite，损坏、加密或无文本层 PDF 返回明确原因并交给后续 OCR 流程
- 上传文件由持久化 ingestion worker 自动执行解析、数字文本/OCR、清洗、结构化分块、Evidence 和图谱抽取；获得 `internal_processing` 授权后自动生成包含全部合格 ChunkSet 的内部工作 Release 和全文索引，避免已上传资料长期停在“无资料记载”状态
- 扫描 PDF、PNG 和 JPEG 可通过已配置的视觉模型逐页 OCR；结果保存原始文字、置信度、旋转角和归一化文字区域，单页失败不会丢弃同批成功页，低置信度页进入人工校对队列
- 已建立双模式首页和文史任务卡片
- 首页“今日选题”通过 `/api/research-feed/daily` 按上海日历日期每日更新：优先聚合昨日星羲真实提问（去重用户数优先、检索次数其次），过滤工具验收等非研究提示，并要求规范检索词在当前 Active Release 的绑定 Chunk 内至少命中 1 条授权证据；涉及来源比较时仍必须覆盖至少 2 份文献。卡片进入问答时会携带该检索词、文献 ID 和 Evidence ID，问答工具先校验并载入这些随附资料，避免模型扩写检索词后查空。结果按日期缓存，热门候选不足时使用经过同一门槛验证的本地文献种子，无合格候选才显示空状态
- 普通问答首次检索无结果时，可去掉独立的“历史联系”“相关记载”等提问用语，以至少两个核心词重试一次。例如“陆玩 灵岩寺 历史联系”会再检索“陆玩 灵岩寺”；重试沿用原知识版本、文献范围和筛选条件，保留引号中的精确表述。
- 研究项目页通过 `/api/research-projects` 读取当前用户的真实数据，并分别展示进行中与已归档项目；项目计数和项目卡片使用同一归档状态，已创建项目会稳定出现在对应列表
- 当前框架开发环境使用 SQLite；Docker PostgreSQL 仍是可选的共享部署模式。资料入库、证据侧栏和二维古舆地图已形成可运行闭环，三维 GLB 资产仍待授权资料接入

详细建设顺序见仓库上一级的 `PROJECT_PLAN.md`。

## 目录

```text
deer-flow/
├─ backend/
│  ├─ app/gateway/                         # 星羲弦沚 API 与流式运行入口
│  └─ packages/
│     ├─ harness/deerflow/agents/xingxi/   # 星羲弦沚专用运行图与领域工具装配
│     ├─ harness/deerflow/persistence/      # 统一数据库、迁移与领域 SQL 适配器
│     └─ wu_culture/                       # 文史模型、Repository 与检索服务
├─ frontend/
│  └─ src/app/workspace/                   # 智能体首页、会话与后续领域页面
├─ docker/                                 # 本地与容器部署
└─ config.example.yaml                     # 模型、工具、存储与运行配置示例
```

## 本地启动

项目需要 Python 3.12+、Node.js 22+、pnpm 10.26.2+ 和一个可用的大模型配置。

```bash
make setup
make dev
```

统一访问地址：<http://localhost:2026>

也可以分别运行：

```bash
cd backend
make dev

cd ../frontend
pnpm dev
```

## Docker PostgreSQL

当 `config.yaml` 使用 `database.backend: postgres` 时，`make up` / `scripts/deploy.sh` 会自动加载 `docker/docker-compose.postgres.yaml`，启动仅供内部网络访问的 PostgreSQL 17，并等待数据库健康后再启动 Gateway。数据保存在 `deer-flow_postgres-data` Docker volume；数据库密码保存在 `backend/.deer-flow/.postgres-password`，不会写入仓库或日志。

SQLite 与 PostgreSQL 不会自动复制历史数据。切换后 PostgreSQL 默认是新库，原 SQLite 文件 `backend/.deer-flow/data/deerflow.db` 会原样保留，便于回退或后续执行显式迁移。

## 史料对象存储

默认配置使用 `object_storage.backend: local`，文件写入 `DEER_FLOW_HOME/objects`。生产 Docker 已持久化挂载 `DEER_FLOW_HOME`，所以 Gateway 容器重建后对象仍可读取。对象按用户、类别和 SHA-256 生成键，原文件名仅作为元数据保存；跨用户访问、绝对路径、盘符、反斜杠和 `..` 路径会被拒绝，删除必须提供原因并留下审计记录。

切换 AWS S3、MinIO 或其他 S3-compatible 服务时，在 `config.yaml` 设置 `object_storage.backend: s3`、`bucket`、可选 `endpoint_url` 和凭据环境变量，然后重新运行部署脚本。脚本会自动安装 `s3` extra。数据库表 `wu_object_metadata` 只记录对象键、所有者、类别、哈希、MIME、大小、后端和存储位置；原件字节始终留在对象存储。

## 府县志批量导入

`wu_culture.corpus_import` 提供府县志七件套的只读扫描、JSONL 清单校验、dry-run 和幂等 SQL 导入。导入将原地 PDF 登记为受控 `corpus://` 只读资产，把已有繁体 OCR/清洗文本转换为页、ChunkSet、质量问题和 Ingestion Job；不会复制或修改原始 PDF。来源等级 `U` 表示“待评定”，不等同于 A-E 中任何已审核等级。

Release 分为两类。`public` Release 仍要求内容复核和公开授权全部通过；`internal` Release 只允许具备 `internal_processing` 权限的内部开发检索，可以容纳尚待复核的 Chunk。内部工作版不会把资料变成公开资料，也不能用于公共引用或公共全文接口。

```bash
cd backend

uv run python -m wu_culture.corpus_import.cli scan \
  --root /data/laikai/府縣志 \
  --root-id fuxianzhi \
  --output /data/laikai/import-manifests/fuxianzhi-v1.jsonl

uv run python -m wu_culture.corpus_import.cli validate \
  --manifest /data/laikai/import-manifests/fuxianzhi-v1.jsonl

uv run python -m wu_culture.corpus_import.cli import \
  --manifest /data/laikai/import-manifests/fuxianzhi-v1.jsonl \
  --root /data/corpora/fuxianzhi \
  --bundle 包山集四卷 \
  --dry-run
```

服务器内部开发环境可用下面的幂等命令导入全部书包、创建或复用一个内部工作版、激活它并构建全文索引。中断后重跑会复用已经完成的书包：

```bash
cd /data/laikai/deer-flow

docker compose \
  --env-file .env \
  -p deer-flow-dev \
  -f docker/docker-compose-dev.yaml \
  -f docker/docker-compose-server-dev.yaml \
  exec -T gateway sh -lc '
    cd /app/backend &&
    .venv/bin/python -m wu_culture.corpus_import.cli import \
      --manifest /data/import-manifests/fuxianzhi-v1.jsonl \
      --root /data/corpora/fuxianzhi \
      --allow-unconfirmed-internal \
      --publish-working-release \
      --actor laikai
  '
```

服务器开发 Compose 示例位于 `docker/docker-compose-server-dev.example.yaml`，将 `/data/laikai/府縣志` 只读挂载到 `/data/corpora/fuxianzhi`，并把清单目录挂载到 `/data/import-manifests`。管理账号可在文献库的“导入批次”查看书目、页数和质量问题，并从受权限保护的内容接口打开原件；复核与检索引用同时显示 PDF 物理页和原书叶码。

2026-08-22 的真实只读扫描基线为 74 个书包、518 个文件、120,815 页，清单 SHA-256 为 `767c999cf16a14575ae37fae671e5312d3bcd77d60f3aba0685aca63c59397c8`。2026-08-25 服务器实机验收已激活内部工作版 `release-2c7aafe43b4247fa86ab0d6b951590e7`（`v1`）：74 Documents、74 SourceFiles、74 ChunkSets、78,930 Release Items、78,930 全文 Documents 和 78,930 Evidence，索引状态为 `ready`。简体“木渎”可命中 742 个繁体正文 Chunk；真实 HTTP Agent Run 调用 `search_sources(query="木渎镇", top_k=3)` 后返回 3 条真实 Evidence，最终回答保留了对应的 3 个 `evidence://fulltext-release-...` 引用。向量通道尚未配置；若 structured/hybrid 通道超时，Agent 会跳过重复 hybrid 请求并继续使用直接全文检索，而不是误报索引未就绪。清单默认保持 `unconfirmed + internal + []`；使用内部工作模式时只补充 `internal_processing`，不推断来源等级、机构、持有人或公开授权。完整边界见 `plans/fuxianzhi-corpus-integration-plan.md`。

## 开发检查

```bash
cd backend
make test
make lint

cd ../frontend
pnpm check
pnpm test
```

后端功能必须遵循测试先行；前端关键路径必须包含单元测试和 Playwright E2E。真实密钥、用户数据、未授权文献、生成索引和运行目录不得提交。

`backend/tests/fixtures/wu_culture/` 中的数据全部是合成测试数据，不是历史资料，不得加载为产品知识。

Gateway 启动时会自动执行数据库迁移。阶段 06 只建立可靠的存储与查询链路，不会自动导入测试数据或未经授权的资料；真实资料登记和入库从阶段 08 开始。

来源记录新建后默认为 `unconfirmed + internal + []`，不会公开。管理员通过 `PUT /api/source-documents/{id}/authorization` 更新授权；匿名调用 `GET /api/public/source-documents/{id}/access?use=public_quote` 或 `use=public_full_text` 只能获得允许/拒绝结果，不会看到授权证明。阶段 09 只提供授权策略与访问判定，不提供文件上传或公开下载。

管理员可在文献库选择已登记来源后上传原件，也可直接调用 `POST /api/source-documents/{id}/files`。上传限制沿用 `config.yaml -> uploads`；文件按块读取并写入受控对象存储，`wu_source_files` 只保存来源与对象键的绑定。上传完成本身不自动执行 OCR、解析、发布或索引。

阶段 11 为 `wu_source_files` 增加 `sha256`、`duplicate_of_file_id` 和 `version_of_file_id`。相同内容默认返回 `duplicate_file`；`duplicate_policy=reference_existing` 复用已有对象，`duplicate_policy=new_version` 配合 `version_of_file_id` 建立版本关系。数据库部分唯一索引保证并发请求也只能产生一条 canonical 哈希记录。

阶段 12 提供 `POST/GET /api/source-documents/{document_id}/files/{file_id}/parse`。解析结果写入 `wu_parsed_documents` 和 `wu_parsed_blocks`；PDF 保留物理页号，DOCX 保留显式分页、表格和脚注，TXT/Markdown 识别编码并使用逻辑页。重复文件引用复用 canonical 文件的解析结果。扫描 PDF 返回 `no_extractable_text`，由阶段 13 OCR 处理，原件始终不被覆盖。

阶段 13 提供 `POST/GET /api/source-documents/{document_id}/files/{file_id}/ocr`、失败页重试端点以及 `/api/source-documents/ocr/review-queue`。在 `config.yaml -> ocr` 中引用一个 `supports_vision: true` 的 `models[]` 条目即可复用该模型已有的中转站 `base_url`/`api_base` 和 API key；标准服务使用 `api_mode: chat_completions`，要求 `/v1/responses` 的中转站使用 `api_mode: responses`。页图写入对象存储，所有 OCR 尝试及文字区域追加保存到 SQLite；重复文件引用复用 canonical OCR。此阶段不清洗原文、不切分 Chunk，也不建立索引。

阶段 14 提供 `POST/GET /api/source-documents/{document_id}/files/{file_id}/clean` 和页级 generation 历史接口。服务只从最新 OCR attempt 读取 raw，生成独立 clean、双 SHA-256、完整 policy 快照和逐项变更记录；API 不接受 raw 覆写。规则支持 CRLF 规范化、单断行连接、重复页眉/页脚和显式页码删除、OpenCC 繁简策略及显式一对一异体字映射。重新生成会追加 generation，不覆盖旧 clean；自动结果不视为人工校勘结论。

阶段 15 提供 `POST/GET /api/source-documents/{document_id}/files/{file_id}/chunks` 和指定 split version 查询。切分识别卷/目结构与段落，保留结构标题换行，合并无终止标点的跨页段落，并按最大字符数和重叠窗口拆分长段。每个 Chunk 带 stable ID、文献/文件、版本、卷目、段内范围、raw/clean、起止页和 clean generation 引用；同一版本只可复用相同 policy 与输入，规则变化必须使用新版本，旧 ChunkSet 不覆盖。

阶段 16 在文件上传成功后创建持久化入库 Job，并返回 Job 快照。`wu_ingestion_jobs`、`wu_ingestion_steps` 和追加式 `wu_ingestion_events` 保存解析、OCR、清洗、切分、复核、索引的状态、进度、产物引用和结构化错误；管理员可查询、增量读取事件、取消或只重试当前失败步骤。worker 通过数据库原子 claim 获取全局并发名额，并使用 owner/lease 心跳避免多 Gateway 互相接管；服务重启只重新排队已过期租约。切分后任务强制停在“待复核”，不会自动索引或发布。并发与租约配置位于 `config.yaml -> ingestion`。

阶段 17 在文献库提供页/Chunk 人工复核工作台。管理员选择精确 ChunkSet 后可对照 OCR raw 与 clean，查看置信度、旋转、清洗变更和页码，执行单条或批量通过、退回、争议并查看全部 revision 历史。结论写入不可变 `wu_review_records`，当前状态同步到 clean page 与 Chunk；退回/争议必须填写意见。只有 Chunk 及其引用的每个 clean generation 都通过，`review/finalize` 才会把入库 Job 推进到 index pending；它不会创建阶段 18 的知识版本。

阶段 18 将通过复核门禁的一个或多个 ChunkSet 发布为不可变知识版本。Release 依次处于 `preparing`、`ready`、`failed`、`active`；manifest 先以准备中状态保存，全文索引、图谱快照和地图快照在同一准备事务全部成功后才允许切换 active pointer。任何派生资产失败都会整体回滚并把 Release 标为失败，前端不会将其显示为当前版本；管理员可从失败版本重试，旧数据库升级时也会撤销缺少完整索引或资产的活动指针。文献库可发布、重试或回滚版本；每个新 Run 只读取真实 `active` Release，并由服务端写入 Release ID、版本号和 manifest hash。

阶段 19 为每个知识 Release 建立独立中文全文索引。SQLite 使用内置 FTS5 `trigram`，PostgreSQL 使用 `pg_trgm` GIN；全文文档和索引就绪状态参与 Release 的原子准备事务，完成图谱与地图资产快照后才可激活。检索支持引号短语、空格分隔的多关键词 AND、二字专名、标题/卷目权重、分页、文献/类型/等级过滤、页码来源和纯文本高亮摘要。`search_sources` 读取 Run 固定的 Release ID，授权撤销或过期会在查询时动态拒绝。语义近义召回仍由阶段 20 负责。

阶段 20 为不可变知识 Release 建立版本化语义索引。SQLite 使用 `sqlite-vec`，PostgreSQL 使用 `pgvector` cosine/HNSW；批量向量全部校验并写入后才原子切换 active index，重建中或失败时旧版本继续查询。索引固定 `embedding.model + version + dimensions`，配置变化后必须重建，禁止新旧向量混用。`POST /api/knowledge-search/vector` 返回相似 Chunk 与完整引用，但相似度只表示候选相关性，不代表史实可信度；全文与向量融合留在阶段 21。

阶段 21 通过 `POST /api/knowledge-search/hybrid` 对同一 Release 并行执行全文与向量检索，再用明确的 Reciprocal Rank Fusion（RRF）按 Chunk ID 去重。每个结果保留全文/向量通道、原始分数、通道排名、RRF 贡献和融合分数。单通道超时、未配置或失败时返回另一通道并标记 `degraded`，两个通道都不可用才整体失败。`search_sources` 已使用这条融合链；来源等级与复核状态不参与本阶段融合，留到阶段 22。

阶段 22 在 RRF 候选池上执行确定性可信度重排，默认分项为相关性 70%、来源等级 15%、复核状态 10%、可信时间信号 5%，并对重复文献施加可见的多样性惩罚。结果返回 policy version、final score、各分项、原因和警示；D/E 级、disputed、时间冲突候选不会被静默删除。强相关低等级材料仍可能排在弱相关高等级材料之前。当前没有可靠结构化年代的候选默认 `temporal_unknown`，系统不从书名或原文猜测年代；阶段 23 再接结构化时间条件。

阶段 23 提供 `POST /api/knowledge-search/structured`，以同一个白名单 Filter schema 支持文献、版本、来源类型/等级、朝代、实体类型、复核状态和空间置信度组合过滤。分类内为 OR、分类间为 AND；所有 SQL 由 SQLAlchemy 列表达式与规范化 facet `EXISTS` 生成。游标绑定 Release 和查询/筛选指纹，换条件或 active Release 后必须重新分页。后端 API、`search_sources` 和前端客户端共享该 schema；当前发布只写入已有真实字段，尚无可靠来源的朝代、实体与空间 facet 保持为空，后续实体/时空阶段再回填。

阶段 24 在结构化搜索前执行 Release 级别名扩展。别名、规范名、实体候选、适用朝代、复核状态和 Evidence 外键分别持久化；只有已复核、有真实证据且年代匹配的唯一候选会替换查询。一个旧名对应多个实体时返回 `requires_disambiguation` 和所有候选，不自动任选或合并；无证据、未复核或年代不符记录只作为解释信息。扩展数量有上限，响应和 `search_sources` 都保留原查询、规范查询、证据 ID 和未扩展原因。

## 史料原则

- 关键事实必须绑定真实来源，不允许编造书名、版本、卷目、页码或原文。
- 一手方志、原始碑刻和正式档案优先于后世整理和网络材料。
- 民间传说、争议说法、空间推定和复原假设必须明确标注。
- 当前证据不足时回答“暂无明确方志记载”，并说明已检索范围。
- “未检索到”不等于“历史上不存在”。

## 古舆地图公开数据说明

地图工作台支持浏览器实时位置、站点排序和道路路线覆盖层。用户授权后，页面通过 `watchPosition` 持续更新蓝色本人标记；标记在空间探索和研学路线模式中都保留，并可一键重新居中。浏览器定位只允许在 HTTPS 或 `localhost` 安全上下文使用，通过 SSH 转发访问时应继续使用 `http://localhost:12026`。`POST /api/map/route-plan` 使用 OSRM-compatible 服务返回真实道路几何、距离和预计驾驶时间；默认公开服务仅供试用，生产环境应在 `.env` 设置 `XINGXI_ROUTING_BASE_URL` 指向自建或有 SLA 的服务。路由不可用时界面只显示红色虚线站点顺序，并明确标记为非道路导航。

`/workspace/map` 通过 `GET /api/map/catalog` 读取二维地图目录。目录合并现有静态现代地物与当前 Release 中绑定 Evidence、具有可辩护坐标且未被驳回的 SQL 实体、GeoFeature 和事件。已复核记录进入正式层，`pending/disputed` 记录只进入醒目标注的“语料草稿”层；两者可独立筛选。人物轨迹由人物参与事件和 `visited/lived_in/born_in/worked_at/studied_at` 关系动态生成，支持多人物选择，连接线只表达文献节点的时间顺序，不表示真实道路。

历史时间轴只自动播放目录中显式标记为 `featured` 的重要事件，不按固定年份空转。每个事件按 `year_start` 和稳定事件 ID 排序；播放时地图聚焦对应点位并显示脉冲，点击事件可在桌面右栏或移动端底部弹窗查看朝代、年份、地点、人物和资料出处，并可返回地点资料。同年事件聚合为一个年份节点，点击后先显示该年事件列表；相邻年份节点最多使用两条轨道避让。现代 OpenStreetMap 底图通过 `https://tile.openstreetmap.de/{z}/{x}/{y}.png` 以 100% 不透明度和原始色彩显示，首次视野聚焦木渎、灵岩山及附近证据点。古地图、历史范围和推测范围默认关闭；选择地点只定位并打开侧边详情，范围必须由用户在图层面板中主动开启。

74 部府县志完成全文索引后，正文都可以参与内部 RAG 检索，但这不代表 74 部书里的全部历史地名都会自动出现在地图上。未复核名称、没有 Evidence 的抽取结果、无法定位或只有猜测坐标的地点不得伪造成地图点；它们应先进入实体/异名/事件/GeoFeature 草稿与人工复核链路。

项目内置 `backend/data/fuxianzhi_knowledge_seed.json`，用于把已人工核对原文的代表性人物、关系、事件和地点写入当前内部 Release。导入是幂等的，所有记录固定为 `pending`，并校验每个 Evidence 确实属于目标 Release；重复执行不会覆盖已经被人工审核为其他状态的记录：

```bash
cd backend
uv run python scripts/bootstrap_fuxianzhi_knowledge.py --dry-run
uv run python scripts/bootstrap_fuxianzhi_knowledge.py
```

- OpenStreetMap/Wikidata 坐标只用于当前地物定位，不自动证明历史时期的位置、边界或沿革。
- 中文维基百科等公开条目作为待复核历史线索，不能替代项目方校勘后的方志、档案或测绘资料。
- 永安桥坐标由“严家花园前”的文字地址与 OSM 未命名桥位交叉对应，API 和 UI 均标记为 `approximate`，待实地或正式测绘确认。
- 人物活动节点不做路线插值；静态参照轨迹和府县志动态人物轨迹均使用虚线，并明确说明不能据此还原真实道路。
- 美国国会图书馆开放的《平江图》（1229）主要表现平江城，不覆盖木渎镇区；没有控制点和校准成果时只显示为参考资料，不作为可叠加古地图发布。
- 研学路线是可编辑、可导出的内容建议，不是实时导航；票务、开放时间、宗教场所规则和现场可达性必须在出发前核验。

GLB 三维资产仍仅保留协议与降级占位，不在本次二维地图资料范围内。

## 运营治理闭环

治理账号可通过 `/workspace/operations` 查看回答准确率、出处引用率、拒答合规率、未命中问题、热门实体、二维地图点位点击、用户满意度和人工修订量。最终回答、引用打开、拒答未命中和地图点位点击由实际交互采集；准确性与拒答合规性以治理标注为依据，不以点赞代替事实准确性，离线回归通过率不计入线上回答准确率。

`/api/operations` 提供追加式运营事件、人工修订、固定评测用例、不可变评测运行结果、资产版本清单和统一后台任务中心。`GET /api/operations/tasks` 汇总资料入库任务的解析、识别、清洗、切分、复核和索引步骤，返回失败步骤、错误代码、错误原因、尝试次数及可重试状态；`POST /api/operations/tasks/{task_id}/retry` 复用入库状态机恢复可重试失败，查看需要 `governance:read`，恢复需要 `source:manage`。图谱与二维地图 SHA-256 快照是知识版本激活前的必备产物；实体查询或快照写入失败会让知识版本准备失败，不会静默生成实体数为零的错误快照。历史修订、评测结果和成功资产快照均保留，不覆盖旧记录。三维模型加载成功率在三维资产尚未接入期间明确返回空值。

## 开源基础

本项目复用了 DeerFlow 的开源实现，并保留其 MIT License。对底层引擎的修改应尽量维持清晰边界，便于审计安全行为和评估上游变更。
## Agent 自动评测与测试记录

“回归评测”首先展示简单人工测试：已保存的回答、逐条判定和规则通过率。填写区只展示启用用例；空回答不能提交。历史结果可以展开查看，新增用例与自动流程评测收在折叠区。规则通过不代表史料内容准确，也不会自动调用模型。

点击左侧 **Agent 评测**，或打开 `/workspace/evaluations`。独立大盘提供所选批次的规则通过率、平均回放耗时及有效样本数、执行错误数和待复核数，展示历史批次趋势与未通过/未完成项分布。管理员可以运行核心 6 项或全部 30 项（10 类场景 × 3 种模式），取消任务、重跑未通过项、追加人工复核，并导出 HTML、Markdown、JSON、CSV。具有治理读取权限的用户可以查看和导出；运营中心的回归评测保留人工测试和跳转入口。

测试记录可按场景、模式、结果及问题/回答关键词筛选。点击“查看轨迹”在抽屉中核对实际回答、按事件序号排列的工具参数与返回结果、逐项期望/实际和原文/页码/证据版本；抽屉支持窄屏。缺失指标显示“未采集”，时间筛选与趋势图仅覆盖当前历史页（每页最多 20 批）。图表使用 SVG，支持悬停提示和键盘查看，不需要外部图表服务或新增依赖。未作同条件版本比较，不生成趋势涨跌或虚构失败根因。

在仓库根目录执行 `make eval-smoke`、`make eval-agent` 或 `make test-report`，报告保存到 `reports/testing/`，终端打印实际路径。CLI 使用独立数据库，其批次不会自动出现在业务页面。Gateway 重启时自动执行 `0044_agent_evaluations` 迁移。

本版使用固定脚本模型和合成资料，通过真实 Gateway 与星羲 Graph 验证软件行为。真实模型的回答质量需要另行评测。命令、报告、权限和覆盖边界见[使用说明](docs/agent-evaluation-testing.md)。
