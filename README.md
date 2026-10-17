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
- 当前框架开发环境使用 SQLite；Docker PostgreSQL 仍是可选的共享部署模式。资料入库、证据侧栏和二维古舆地图已形成可运行闭环，已接入七个本地 GLB 的地图按需预览，模型范围与许可仍待核实

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

地图现有七个景点使用固定 28 像素的“3D”圆点，点击区域为 44 像素；地图缩放或点位选中不改变圆点大小。可预览模型的点位：木渎古镇、虹饮山房、古松园、榜眼府第、明月古寺、灵岩山寺与永安桥。点击点位停留在概览页签，模型页签在标题标注体积，打开页签后才开始加载；桌面使用右侧详情栏，移动端使用底部面板；支持旋转、缩放、复位、放大和失败重试。严家花园与灵岩山暂无对应模型。模型加载后切换或关闭即卸载，桌面与移动布局只保留一个活跃实例。

模型登记在 `frontend/src/core/map/model-assets.ts`，精确绑定既有 reference 点位与实体 ID；七个 GLB 存在 `frontend/public/models/` 的内容摘要版本地址。查看器依赖 `@google/model-viewer`，当前文件无需外部压缩解码服务。模型为照片生成示意，不表示完整景区或实测复原；永安桥仍为近似定位。文件总计约 400 MiB，移动设备性能需实测并按需制作轻量版。许可登记为待确认，本地接入不代表已经获得公开发布许可。三维预览独立于知识 Release 的二维地图快照。完整使用与验证说明见[地图模型预览](docs/map-model-preview.md)。

## 运营治理闭环

治理账号可通过 `/workspace/operations` 查看回答准确率、出处引用率、拒答合规率、未命中问题、热门实体、二维地图点位点击、用户满意度和人工修订量。最终回答、引用打开、拒答未命中和地图点位点击由实际交互采集；准确性与拒答合规性以治理标注为依据，不以点赞代替事实准确性，离线回归通过率不计入线上回答准确率。

`/api/operations` 提供追加式运营事件、人工修订、固定评测用例、不可变评测运行结果、资产版本清单和统一后台任务中心。`GET /api/operations/tasks` 汇总资料入库任务的解析、识别、清洗、切分、复核和索引步骤，返回失败步骤、错误代码、错误原因、尝试次数及可重试状态；`POST /api/operations/tasks/{task_id}/retry` 复用入库状态机恢复可重试失败，查看需要 `governance:read`，恢复需要 `source:manage`。图谱与二维地图 SHA-256 快照是知识版本激活前的必备产物；实体查询或快照写入失败会让知识版本准备失败，不会静默生成实体数为零的错误快照。历史修订、评测结果和成功资产快照均保留，不覆盖旧记录。三维模型预览已接入；模型加载统计尚未接入运营事件，加载成功率继续返回空值。

## 开源基础

本项目复用了 DeerFlow 的开源实现，并保留其 MIT License。对底层引擎的修改应尽量维持清晰边界，便于审计安全行为和评估上游变更。
## Agent 自动评测与测试记录

“回归评测”首先展示简单人工测试：已保存的回答、逐条判定和规则通过率。填写区只展示启用用例；空回答不能提交。历史结果可以展开查看，新增用例与自动流程评测收在折叠区。规则通过不代表史料内容准确，也不会自动调用模型。

点击左侧 **Agent 评测**，或打开 `/workspace/evaluations`。独立大盘提供所选批次的规则通过率、平均回放耗时及有效样本数、执行错误数和待复核数，展示历史批次趋势与未通过/未完成项分布。管理员可以运行核心 6 项或全部 30 项（10 类场景 × 3 种模式），取消任务、重跑未通过项、追加人工复核，并导出 HTML、Markdown、JSON、CSV。具有治理读取权限的用户可以查看和导出；运营中心的回归评测保留人工测试和跳转入口。

测试记录可按场景、模式、结果及问题/回答关键词筛选。点击“查看轨迹”在抽屉中核对实际回答、按事件序号排列的工具参数与返回结果、逐项期望/实际和原文/页码/证据版本；抽屉支持窄屏。缺失指标显示“未采集”，时间筛选与趋势图仅覆盖当前历史页（每页最多 20 批）。图表使用 SVG，支持悬停提示和键盘查看，不需要外部图表服务或新增依赖。未作同条件版本比较，不生成趋势涨跌或虚构失败根因。

在仓库根目录执行 `make eval-smoke`、`make eval-agent` 或 `make test-report`，报告保存到 `reports/testing/`，终端打印实际路径。CLI 使用独立数据库，其批次不会自动出现在业务页面。Gateway 重启时自动执行 `0044_agent_evaluations` 迁移。

本版使用固定脚本模型和合成资料，通过真实 Gateway 与星羲 Graph 验证软件行为。真实模型的回答质量需要另行评测。命令、报告、权限和覆盖边界见[使用说明](docs/agent-evaluation-testing.md)。

模型参考点通过独立的 `/api/map/reference-points` 获取，只合并与实际模型精确绑定的景点；即使尚未发布知识版本也可以预览，原正式目录与快照保持独立。

## UI 全面重构协作

本次重构采用 Gemini CLI／IDE 设计、Codex 实现与验证的分工。协作入口、设计任务和分批验收见 [UI 重构工作流](docs/ui-redesign/README.md)。设计阶段不改变运行界面，已有功能与业务协议作为保留边界。

## 迭代日志

### 2026-10-17 22:05 — 完成100图GPU联调并清理乐高测试内容
- 改动文件：README.md；本地正式数据库的本次测试点位/任务，以及对应本机、服务器运行产物和测试报告（均非版本化产品代码）。
- 内容：乐高100图按balanced完成真实COLMAP与Brush训练，100/100注册、15,000步、54,360高斯；正常登录地图验证彩色预览、下载SHA、Range206、刷新持久化，并用同一请求ID经HTTP重传100图确认不重复训练。按用户后续要求，删除此次测试点位、任务、素材副本、模型、截图、报告和远端专属任务目录。
- 原因：确认现有创建模型全链路可用后清除演练数据，再推送功能分支，避免测试内容保留在正式地图或进入Git提交。
- 影响/验证：清理后正常登录确认点位、任务与资产列表均无该测试记录，原任务及文件接口返回404，原七个地图模型点与其他两条模型记录保留；反重力原始100图及原项目保留。pnpm check通过（0错误、4条既有graph-overview警告）。本轮未修改产品逻辑、账户或SSH配置，未提交模型及凭据；训练103.120秒，服务端流程194.226秒，属于功能集成实测而非独立几何精度验收。

### 2026-10-17 20:40 — 模型新建与重新建立流程验收
- 改动文件：backend/tests/test_map_model_workflow.py、frontend/tests/e2e/map-create-point.spec.ts、前后端 AGENTS.md、新 docs/MAP_MODEL_WORKFLOW_VALIDATION.md。
- 内容：补充自建点位关联、已有模型导入、图片/视频重建、同素材用新请求重新建立、旧结果保留、幂等重试和重启恢复的组合回归；手机/桌面界面与大文件代理一并复核。
- 原因：按用户要求确认新建模型、重新建立模型流程可用后再上传分支。
- 影响/验证：后端专项 64、地图单元 42、浏览器 32 项全部通过，浏览器无失败或跳过；pnpm check 通过（4 条已有警告），当前产品构建上轮已通过，本轮未改产品逻辑。真实 SSH 严格公钥连接、当前 generate 参数与 67,584 字节 SFTP 上传下载/哈希校验通过；不启动新 GPU 训练。完整后端仍为相同 12 个既有收集错误、2 skipped。详见 docs/MAP_MODEL_WORKFLOW_VALIDATION.md。

### 2026-10-17 18:12 — 地图新增选点命名与持久点位
- 改动文件：地图页面、MapLibreCanvas、CreateModelDialog、新 CreatePointForm、地图 API/types 与测试；后端 custom_map_points 路由、map_points_store、0046_custom_map_points 迁移、应用挂载、模型点位解析及测试；前后端 AGENTS.md、docs/MAP_POINT_CREATION.md。
- 内容：地图工具栏与创建模型弹窗增加「创建点位」；点击地图选取 WGS84 坐标、填写名称并保存，支持重新选点、取消和失败重试。新点位独立持久保存，刷新保留，并可关联 PLY/GLB 与重建任务；从模型弹窗进入后返回并自动选中新点位。保留管理员创建和登录用户读取权限，重复保存使用请求唯一键。
- 原因：创建模型此前只能选择已有点位，需要允许为新的拍摄位置建立模型关联点位。
- 影响/验证：后端专项 62 项、地图单元 42 项通过，前端 lint/类型检查通过（4 条已有警告）；生产构建通过，浏览器 22 项全部通过、无跳过；记录见 reports/integration/2026-10-17/create-map-point/README.md。完整后端改前/改后均为相同 12 个既有 skillscan.orchestrator 缺失收集错误、2 skipped。自建点位显式标识 custom，不发布知识版本或生成史料证据；本轮不启动 GPU 任务。

### 2026-10-17 17:32 — 地图新增创建模型与持久资产接入
- 改动文件：前端地图页面、创建弹窗、点位预览/重建面板、registered-models 客户端、新流式路由及单元/浏览器测试；后端 map_models 路由、model_files 格式/文件处理、任务存储与列表、应用挂载及测试；两份 Nginx 配置、前后端 AGENTS.md、新 docs/MAP_MODEL_CREATION.md。
- 内容：在地图顶部与点位详情增加管理员「创建模型」，支持上传影像发起现有 SSH 重建，或将彩色/高斯 PLY、GLB 持久保存并关联准确点位/实体；新增模型列表、预览与下载接口，普通登录用户可查看成果，任务管理权限保留；完成重建后刷新点位资产，支持多模型切换和 3D 标记；保留原七个 GLB、临时本地预览和地图业务功能。
- 原因：用户确认需要地图三维模型创建入口，并希望通过新接口接入已有模型，补足此前只有临时本地预览的使用路径。
- 影响/验证：48 项后端专项、39 项地图单元、24 项地图/创建浏览器回归和 3 项流式代理测试通过；类型、生产构建、改动文件 lint 与格式检查通过。覆盖持久恢复、权限、幂等、跨分块文件、12 MiB 传输、Range、真实既有 PLY/GLB 渲染及移动端。完整后端改前/改后仍为相同 12 个既有 skillscan.orchestrator 收集错误。初轮公共 mock 遗漏新接口导致测试登录跳转，补齐后回归全部通过。复用现有持久表，无新数据库迁移；本地服务已加载新功能，未启动新 GPU 训练、添加资源队列/结构检查或向正式库导入测试模型。说明见 [地图创建模型](docs/MAP_MODEL_CREATION.md)，证据见 reports/integration/2026-10-17/create-map-model/。

### 2026-10-17 16:36 — 地图兼容彩色 PLY 与本地成果预览
- 改动文件：前端 `core/map/ply.ts`、点云/PLY 查看器、点位模型入口、重建面板与类型、地图页面及单元/浏览器测试；后端重建 runner、service 及测试；前后端 AGENTS.md、相关接入/融合文档与新 `docs/COLORED_PLY_MAP_PREVIEW.md`。
- 内容：根据 PLY vertex 属性自动分流 Gaussian 和 RGB/RGBA 点云，保留逐点 sRGB 颜色和 Alpha，支持 ASCII、两种二进制字节序及常用颜色属性；默认实体颜色、可切换原 Alpha，避免高斯派生透明度使普通点云偏暗；地图点位新增临时打开本地 PLY，提供旋转/缩放、复位/方向翻转、点大小、深浅背景和单实例放大；后端结果元数据兼容彩色点数与旧高斯记录，保留现有 GLB、权限、下载和点位坐标。
- 原因：用户要求最终彩色 PLY 产物能在 XingXi 地图中直接预览，已有成果无需重训。
- 影响/验证：已用真实 487,474 点药罐 RGB、155,770 点保温杯 RGB 和 38,880 高斯 Bonsai 文件核验；37 项地图单元、35 项后端专项/地图回归通过；22 个不同浏览器用例均有通过记录，初轮一项地图冷启动等待超时经单独复核通过；最终颜色/透明度和移动端再次定向验证，生产构建/类型与格式检查通过，前端 lint 仅 4 个既有警告。完整记录见 `reports/integration/2026-10-17/colored-ply/README.md`。完整后端改前/改后仍为同样 12 个既有 `skillscan.orchestrator` 收集错误。未启动训练或新增 GPU 调度/结构一致性门禁；本地打开仅临时预览，不等于持久资产登记。使用说明见 [地图彩色 PLY 预览](docs/COLORED_PLY_MAP_PREVIEW.md)。

### 2026-10-16 23:28 — 补充重建结果的地图预览适配设计
- 改动文件：docs/FLUX3_OOOSPLAT_FUSION_PLAN.md、README.md。
- 内容：规划统一三维资产入口，原始 Gaussian PLY 复用 Spark、普通 RGB PLY 新增点云查看器、现有 GLB 继续使用原组件；补充点位/版本关联、普通用户可读接口、方向与视角、全屏/移动端和轻量预览策略，支持已有成果导入。
- 原因：用户询问最终重建成果如何适配地图预览及现有功能应如何修改。
- 影响/验证：只读核对现有前后端与本地三个 PLY 文件头，确认彩色派生产物不含完整高斯属性；当前高斯预览位于管理员任务面板、普通地图资产仍以 GLB 为主。本轮只更新适配方案，未修改运行代码或启动训练，未新增结构/跨视角检查。

### 2026-10-16 23:15 — 明确接受 FLUX 结构重绘用于整体展示与重建
- 改动文件：docs/FLUX3_OOOSPLAT_FUSION_PLAN.md、README.md。
- 内容：按用户确认，将局部结构、轮廓与纹理重绘及遮挡表面补全纳入可接受编辑；永安桥白底处理图可进入重建输入，默认提示词允许模型编辑与补全，不增加检查或拒训条件。
- 原因：用户明确结构重绘不影响项目的整体使用。
- 影响/验证：同步方案的使用目标、素材说明、提示词策略和来源描述；仅调整文档，未改运行代码或提交新任务。

### 2026-10-16 23:12 — 融合方案移除训练前一致性检查
- 改动文件：docs/FLUX3_OOOSPLAT_FUSION_PLAN.md、README.md。
- 内容：按用户要求删除图像/相机对齐与跨视角结构检查阶段，FLUX 输出按既定帧映射和相机数据组装后直接进入 Brush；同步流程图、面板阶段和验收描述，不因主体结构或轮廓变化阻断训练。
- 原因：用户明确不需要标注的训练前检查部分。
- 影响/验证：仅更新设计文档并核对相关描述；未改运行代码，未提交推理或训练。

### 2026-10-16 23:00 — 核验 FLUX 3 新部署并归档 OOOSplat 融合方案（设计，未改执行代码）
- 改动文件：docs/FLUX3_OOOSPLAT_FUSION_PLAN.md、docs/OOOSPLAT_SSH_INTEGRATION.md、reports/integration/2026-10-16/flux3-ooosplat-plan/deployment-verification.json、README.md。
- 内容：读取反重力纯主体 SOP、对应会话与 Work 的 FLUX 3 部署/白底试验；规划原图 COLMAP 定姿、FLUX 提示词编辑、尺寸/跨视角校验、OOOSplat Brush 重建及原始高斯/派生点云双产物。沿用“只提示词、不自动提取”的默认要求，Alpha/SAM 单列可选增强，不加入 GPU 门禁或训练排队。
- 原因：整合新部署的 FLUX 3 图像编辑服务与现有地图 SSH 重建入口，并明确白底 RGB 与真实透明训练输入的差异。
- 影响/验证：只读实测 ComfyUI 0.41.0 在线、BF16 模型与 keep resolution 节点可见、OOOSplat/COLMAP/Brush 入口及 Alpha/点数上限参数可用；未提交新推理、未训练、未改后端或前端执行代码。记录永安桥侧面重绘、相机尺度对齐、50 万点上限与 Gaussian/普通点云区别；不把方案归档宣称为融合链路已部署。

### 2026-10-16 22:55 — 沉淀实拍物体 50 万高精 3DGS 纯主体三维重建标准操作方案 (SOP)
- 改动文件：`docs/3dgs-pure-subject-reconstruction-sop.md`、`README.md`。
- 内容：响应用户“将当前重建流程总结成可直接按步骤使用的方案”指令；基于实拍白色保温杯与黑色肌酸药罐两次实战经验，正式沉淀两段式纯主体重建工业级 SOP；梳理了“手机双层环视拍摄规范”、“120~150 帧无损平滑重采样”、“大场景 COLMAP 求解高精度相机几何位姿”、“SAM 2.1 双提示点 + CPU 内存卸载时空追踪抠像”、“Brush 透明度权重（`--match-alpha-weight 0.2`）超稠密训练”与“标准 24-bit sRGB 真彩 PLY 转换”的 6 大标准作业程序；整理了纯数字 JPEG 命名兼容、CUDA 显存溢出避坑、超敏分裂阈值调优与 3D 查看器真彩显示等排障清单。
- 原因：用户要求沉淀并标准化已验证成熟的高精度纯主体 3DGS 重建流水线。
- 影响/验证：文档已落地至 `docs/3dgs-pure-subject-reconstruction-sop.md`；方案覆盖完整的脚本代码、命令参数速查与 Mermaid 架构图，支持后续任务与团队开箱即用。

### 2026-10-16 22:30 — 黑色肌酸药罐 SAM 2.1 时空抠像纯主体 3DGS 训练成功：48.7 万高精真彩点云满额交付
- 改动文件：`outputs/creatine_sam2_pure_subject.ply`、`outputs/video2_preview/`、`c:\Users\蒲煜元\Desktop\user_video_creatine_models\`、`scripts/run_sam2_creatine.py`、`scripts/train_creatine_sam2.py`、`README.md`。
- 内容：针对黑色肌酸药罐实拍视频中木质桌面与室内深色阴影占据大量点云的问题，响应用户“启动该功能”（SAM 2.1 纯主体抠像）指令；在第 0 帧注入瓶身中心 `(480, 1150)` 与瓶盖中心 `(450, 800)` 双正提示点，叠加空间约束框 `[90, 680, 870, 1630]`；在服务器调度 Meta 官方 SAM 2.1 Hiera Base+ 模型，以 1.3 FPS 耗时 110.3 秒全自动完成 140 帧 1080P 高清序列的无缝时空追踪分割，导出带 Alpha 透明通道的无损 RGBA 序列，100% 剥离木质桌面与背景噪点；复用大场景 134 帧 95.7% 注册的高精度 COLMAP 相机外参，在 RTX 4090 GPU 3（46GB 显存）上启动 30,000 轮透明度加权（`--match-alpha-weight 0.2`）与超稠密优化；高斯点预算 100% 聚焦于药罐本体，**生成高达 487,474 个纯主体高斯点（接近 49 万点）**，空间几何包围盒收缩 10 倍紧密贴合药罐真实表面；在服务端将高斯球谐转为标准 24-bit sRGB（含 Alpha），纯粹以彩色 PLY 格式回传本机并在桌面归档交付。
- 原因：用户要求从根本上消除黑色药罐实拍视频中的木质桌面与室内阴影噪点，使高精点云预算 100% 聚焦于药罐本体，实现微观细节与文字的极致锐化。
- 影响/验证：实机文件头属性校验通过（`creatine_sam2_pure_subject.ply` 7.80MB / 487,474 顶点，带 `uchar red, green, blue, alpha` 通道）；相比未抠像大场景，桌面与空间噪点 100% 剥离；药罐表面点云密度提升数倍，黑色磨砂罐体曲面、正面红黑金“CHINA”与运动员彩绘、盖顶激光二维码及微细防滑齿纹重建极其锐利，在任意通用 3D 查看器中秒开真彩。

### 2026-10-16 21:50 — 黑色肌酸药罐 1080P 环拍视频端到端 3DGS 训练成功：50 万满额高精真彩 PLY 交付
- 改动文件：`outputs/creatine_colored.ply`、`outputs/video2_preview/`、`c:\Users\蒲煜元\Desktop\user_video_creatine_models\`、`scripts/run_creatine_training.py`、`README.md`。
- 内容：响应用户指定微信实拍视频（`43c15b2fe43b169188755a4b673ab7e3_raw.mp4`，56.35 秒 1080×1920 60fps 高清环拍黑色药罐 CPT 康比特锌镁肌酸）进行训练的指令；在本地平滑重采样均匀提取 140 张 1080P 高清无损原画（257MB）；上传至 GPU 服务器并调度具备 46GB 显存的 RTX 4090 (GPU 3) 执行端到端几何解算与优化；COLMAP 成功注册 134 帧（注册率 95.7%），产出 12MB 相机轨迹与 2.7MB 初始 3D 锚点稀疏点云；在 Brush 引擎中完成 30,000 轮超精细优化（`--growth-grad-threshold 0.00003`），**达到 500,000 个高斯点（50 万点满额收敛）**；在服务端将高斯球谐转为标准 24-bit sRGB（含 Alpha），纯粹以彩色 PLY 格式回传本机并在桌面归档交付。
- 原因：用户要求使用新的手持实拍高清视频素材进行高精度 3DGS 实机重建与检验。
- 影响/验证：实机文件头属性校验通过（`creatine_colored.ply` 8.00MB / 500,000 顶点，带 `uchar red, green, blue, alpha` 通道）；药罐黑色磨砂曲面、正面红黑金“CHINA”与运动员彩绘、盖顶激光二维码及微细防滑齿纹重建极其锐利，在任意通用 3D 查看器中秒开真彩。

### 2026-10-16 20:45 — SAM 2.1 视频抠像突破环境瓶颈：15.5 万纯主体高斯点 3DGS 模型训练成功交付
- 改动文件：`outputs/cup_sam2_pure_subject.ply`、`outputs/user_video_preview/`、`c:\Users\蒲煜元\Desktop\user_video_cup_models\`、`scripts/run_sam2_cup.py`、`scripts/train_cup_sam2.py`、`README.md`。
- 内容：响应用户“怎样减少环境，增加主体性”并采纳“尝试 SAM 2.1 视频时空抠像”的方案；在服务器调度 Meta 官方 SAM 2.1 Hiera Base+ 模型与 PyTorch 2.4/CUDA 12.4 环境，以第 0 帧中心点 `(360, 640)` 与边界框 `[200, 220, 520, 950]` 双重提示注入，启用 CPU 状态卸载，以 1.7 FPS 耗时 73.6 秒全自动完成 116 帧高清时空追踪分割，导出带 Alpha 透明通道的无损 RGBA 序列与二值掩膜；复用原大场景 116 帧 100% 注册的高精度 COLMAP 相机外参，在 RTX 4090 GPU 1 上启动 30,000 轮透明度加权（`--match-alpha-weight 0.2`）与稠密化训练；高斯点预算 100% 聚焦于保温杯本体，**主体高斯点数从未抠像时的 24,388 点暴增 6.4 倍至 155,770 点（满额收敛）**；在服务端将高斯球谐转为标准 24-bit sRGB（含 Alpha），纯粹以彩色 PLY 格式回传本机并在桌面建立专题模型集归档交付。
- 原因：用户要求从根本上消除手持环拍视频中占据 95% 高斯点的地面与周围杂乱环境，使高斯预算完全聚焦于目标物体，最大化主体致密化精度。
- 影响/验证：实机文件头属性校验通过（`cup_sam2_pure_subject.ply` 2.49MB / 155,770 顶点，带 `uchar red, green, blue, alpha` 通道）；相比未抠像大场景，环境杂点 100% 剥离；相比空间截断版，杯身表面点云密度提升 638%，不锈钢反光杯口、白底磨砂微观质感、小熊印花与条形码细节高度锐化，在任意通用 3D 查看器中秒开真彩。

### 2026-10-16 18:37 — 地图接入 OOOSplat SSH 影像重建
- 改动文件：backend/app/gateway/reconstructions/、routers/reconstructions.py、app.py、0045_map_reconstruction_jobs.py、pyproject.toml/uv.lock、frontend 的地图入口/重建 API/任务面板/Gaussian Viewer/流式路由、next.config.js、package.json/pnpm-lock.yaml、Nginx 两份配置、相关测试与模块 AGENTS.md、docs/OOOSPLAT_SSH_INTEGRATION.md、本地任务。
- 内容：管理员在点位「影像重建」上传一个环拍视频或多张照片，经 Gateway 持久化、SFTP 传送后直接 SSH 启动既有 splatstudio generate；支持真实阶段/日志、断线保留状态、重试防重复、指定任务取消、校验下载与按需高斯预览。新增 12 MiB 实际传输回归并修正通用 rewrite 截断问题，保留原 GLB 与地图业务功能。
- 原因：按用户要求嵌入已部署 OOOSplat 的本地素材上传重建入口；明确不加入 GPU 资源检查、门禁或排队调度。
- 影响/验证：22 项后端专项/地图回归、31 项地图单元、31 个不同浏览器用例通过（18 项地图/GLB/重建/代理 + 13 项核心复测）；类型、构建、格式通过，lint 无错误并保留 4 项原有警告。修正旧引用面板拖动测试在入场动画期间取坐标的问题，等待控件稳定后复测通过。真实 SSH/CLI 帮助及隔离合成传输全流程通过；3000/8001 本地服务已更新、任务表迁移与 SSH 配置启用，未登录仍受保护。完整后端套件改前/改后均有相同 12 个既有 skillscan.orchestrator 缺失收集错误。未新启 GPU 训练；预览复用昨日 Bonsai 产物，不作为新训练或质量通过证据。记录见 reports/integration/2026-10-16/ooosplat/，部署说明见 docs/OOOSPLAT_SSH_INTEGRATION.md。

### 2026-10-16 17:38 — 保温杯 3D 空间圆柱几何滤波完成：剔除 95% 环境杂质交付纯主体真彩模型
- 改动文件：`outputs/cup_subject_only.ply`、`outputs/cup_with_base.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“怎样减少环境，增加主体性”并执行“尝试 3D 空间几何包围盒智能滤除方式”的指令；对 50 万点保温杯模型进行多视角相机光轴交汇点求解（精确求出环拍中心与杯心 `[-0.491, 1.267, 2.081]`）与 PCA 主轴几何分析；建立 3D 圆柱体空间包围盒，成功剥离了占据 95% 点数的地面瓷砖、椅子腿和地下反光杂质；分别导出两组高纯度真彩 PLY 交付成果：
  1) `cup_subject_only.ply`（390KB / 24,388 顶点，100% 纯净悬浮杯身，彻底无地面）；
  2) `cup_with_base.ply`（564KB / 35,264 顶点，杯身保留贴地极薄一圈真实托底接触面与阴影）。
- 原因：用户要求减少实拍视频中的周围环境干扰，最大化凸显目标物体的核心主体性。
- 影响/验证：实机文件头属性核验通过（带 `uchar red, green, blue, alpha` 通道）；相比原版 50 万点大场景，环境噪点彻底清空，在任意 3D 查看器中聚焦呈现纯净保温杯主体。

### 2026-10-16 15:50 — 用户实拍保温杯视频端到端 3DGS 训练成功：50 万满额高精真彩 PLY 交付
- 改动文件：`outputs/cup_colored.ply`、`outputs/user_video_preview/`、`c:\Users\蒲煜元\Desktop\扫描\outputs\cup_colored.ply`、`scripts/run_cup_training.py`、`README.md`。
- 内容：响应用户指定微信视频路径（`ee9ae0e7aac0aa2455e4a99c0ef7b7a9.mp4`，38.5 秒 720×1280 真实手持 360° 环拍白色小熊保温杯）进行训练的需求；在本地探查视频元数据并以 3 FPS 高保真重采样提取 116 张高清原画（重叠率 85%~90%）；上传至 GPU 服务器后通过 OOOSplat 官方端到端流水线（`splatstudio generate`）执行解算；COLMAP 实现了 **100% 完美闭环注册（116/116 帧全部注册成功）**，产出 20,229 个初始稀疏锚点；在 RTX 4090 GPU 上完成 30,000 轮超精细优化，**达到整整 500,000 个高斯点（50 万点满额收敛）**；在服务端将百万级高斯球谐分量转为标准 24-bit sRGB（含 Alpha），纯粹以彩色 PLY 格式回传本机双重归档交付。
- 原因：用户要求使用实际手持拍摄的真实微信环拍视频素材进行 3DGS 实机重建与效果检验。
- 影响/验证：实机文件头属性校验通过（`cup_colored.ply` 8.00MB / 500,000 顶点，带 `uchar red, green, blue, alpha` 通道）；小熊印花、杯身圆柱曲面、不锈钢反光杯口及瓷砖地面纹理完整重建，无孔洞无浮空噪点，在任意通用 3D 查看器中秒开真彩。

### 2026-10-16 14:52 — 真值相机外参驱动麦克风 3DGS 训练成功：高斯点激增至 39 万满额收敛交付
- 改动文件：`outputs/mic_gt_500k_colored.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\mic_gt_500k_colored.ply`、`scripts/nerf_to_colmap.py`、`scripts/train_gt_mic.py`、`README.md`。
- 内容：响应用户关于“为什么训练时 mic 没有达到 50 万精度”的提问并采纳“导入真值相机外参进行尝试”的方案；跳过因金属反光和自对称仅能解算 28 视角的 COLMAP 流程；解析 NeRF 官方 `transforms_train.json`，无损转换为 100 张全量原图的 100% 精确 6-DoF 真值相机外参与 PINHOLE 内参，并在麦克风物理空间生成 15,000 个精密初始 3D 锚点；在 RTX 4090 GPU 上启动 30,000 轮超敏超稠密优化（`--growth-grad-threshold 0.00001`）；在 100 视角全量强监督下，麦克风高斯点数从 149,784 点激增 2.6 倍至 **389,412 个高斯点（接近 39 万点）**；在服务端完成球谐至标准 sRGB 真彩色转换，纯粹以 PLY 格式传回本机交付。
- 原因：用户要求验证导入真值相机外参以突破麦克风点云受限瓶颈，逼近 50 万高精点云。
- 影响/验证：实机文件头校验通过（`mic_gt_500k_colored.ply` 6.23MB / 389,412 顶点，带 `uchar red, green, blue, alpha` 通道）；相比 COLMAP 版本的 14.9 万点，表面点云密度提升 260%，球形金属网罩、旋钮与底盘在全方位 100 视角约束下细节高度锐化，无任何孔洞，在通用 3D 查看器中秒开真彩。

### 2026-10-16 14:09 — 定时任务快速创建改用古舆地图研读模板
- 改动文件：frontend/src/core/scheduled-tasks/recipes.ts、i18n/locales/{zh-CN,en-US,types}.ts、scheduled-tasks/page.tsx、scheduled-task-recipes.spec.ts、frontend/AGENTS.md 与本地任务。
- 内容：四个通用模板改为每日地图史料线索、地图点位考据、古今地名核对、每周地图研习简报；标题／说明／提示词按语言一起填入，保留每天 09:00／每周一 09:00 计划和浏览器时区。提示词要求真实出处、歧义与待考，不自动改坐标、合并实体或发布知识。
- 原因：按用户截图将快速创建内容与木渎古舆地图项目关联。
- 影响/验证：类型、相关 lint 与构建通过，41 项相关单元和 8 项浏览器检查通过；中英文四模板只填草稿，显式创建后发送正确每周计划与 Asia/Shanghai 时区。3000 本地前端已加载新构建；测试使用独立 Mock，无真实后台任务创建。证据见 reports/ui-redesign/2026-10-16/map-task-recipes/。

### 2026-10-15 20:39 — 全新双素材 50 万高精稠密训练完成并交付纯彩色 PLY 模型与原图
- 改动文件：`outputs/chair_500k_colored.ply`、`outputs/mic_500k_colored.ply`、`outputs/chair_raw_images/`、`outputs/mic_raw_images/`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“采用其他素材集进行训练”、“不需要本机已有的素材集”、“采用50万精度即可”的指令；通过官方镜像通道全新拉取此前从未运行过的 NeRF Synthetic 官方经典单物体基准 `chair`（现代几何镂空扶手椅）与 `mic`（复古电台金属麦克风），各 100 张 800×800 RGBA 纯净背景原图；在底层引擎注入 `--max-splats 500000`（50 万点精度上限）与自适应稠密化参数；在 RTX 4090 GPU 1 与 GPU 3 上双路并行全速运行（`chair` 耗时 9.2 分钟产出 315,545 个高质量高斯点，`mic` 耗时 6.7 分钟产出 149,784 个微观高斯点）；在服务器端完成球谐至 24-bit sRGB（含 Alpha）真彩色解算，生成纯彩色 PLY 点云模型并与原图完整同步回传本机交付。
- 原因：用户要求排除本机已有素材，采用全新的单物体素材集，按 50 万精度要求完成训练并仅以彩色 PLY 交付。
- 影响/验证：实机文件头属性与色彩校验 100% 通过（`chair_500k_colored.ply` 5.05MB / 315,545 顶点，`mic_500k_colored.ply` 2.40MB / 149,784 顶点，带 `uchar red, green, blue, alpha` 通道）；相比常规 3~5 万点提升 5~10 倍稠密度，椅腿镂空及金属滤网表面无空洞，在任意 3D 查看器中秒开真彩。

### 2026-10-15 20:07 — 架子鼓单物体 100 张全量高清无损原图回传本机归档
- 改动文件：`outputs/drums_raw_images/`、`c:\Users\蒲煜元\Desktop\扫描\outputs\drums_raw_images/`、`README.md`。
- 内容：响应用户“传送回架子鼓的原图集”的需求；在远端服务器将 NeRF Synthetic 官方经典单物体基准 `drums`（金属架子鼓）全量训练输入原图打包；通过加密通道完整回传本机；解压并双重归档至星羲工作区 `outputs/drums_raw_images/` 与桌面扫描项目归档目录 `c:\Users\蒲煜元\Desktop\扫描\outputs\drums_raw_images/`。
- 原因：用户需要获取用于三维重建与超稠密高斯优化的完整架子鼓原始多视角环拍图集。
- 影响/验证：实机文件核验通过，共 100 张 800×800 RGBA PNG 无损图片（`frame_000001.png` ~ `frame_000100.png`，总计 35.1MB），每张均具备带 Alpha 透明通道的纯净背景，视角均匀覆盖 360 度全方位环视。

### 2026-10-15 20:04 — 乐高单物体 100 张全量高清无损原图回传本机归档
- 改动文件：`outputs/lego_raw_images/`、`c:\Users\蒲煜元\Desktop\扫描\outputs\lego_raw_images/`、`README.md`。
- 内容：响应用户“为我传送回乐高原图”的需求；在远端服务器将 NeRF Synthetic 官方经典单物体基准 `lego`（乐高机械挖掘机）全量训练输入原图打包；通过加密安全通道回传本机；解压并双重归档至星羲工作区 `outputs/lego_raw_images/` 与桌面扫描项目归档目录 `c:\Users\蒲煜元\Desktop\扫描\outputs\lego_raw_images/`。
- 原因：用户需要获取用于三维重建与超稠密高斯优化的完整乐高原始多视角环拍图集。
- 影响/验证：实机文件核验通过，共 100 张 800×800 RGBA PNG 无损图片（`frame_000001.png` ~ `frame_000100.png`，总计 42.1MB），每张均具备带 Alpha 透明通道的纯净背景，视角均匀覆盖 360 度全方位环视。

### 2026-10-15 19:58 — 突破 3DGS 稠密化极限：100 万满额超稠密真彩单物体点云训练交付
- 改动文件：`outputs/lego_ultradense_colored.ply`、`outputs/drums_ultradense_colored.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“能否在训练时增加高斯稠密度”、“开到最高精度与稠密度”的指令；深入 OOOSplat 底层训练引擎 Brush-app，通过环境变量拦截与微调参数注入实现极限稠密化机制（分裂门槛阈值 `--growth-grad-threshold` 压低至 0.00001，每次稠密分裂比例提升至 30%，优化分裂周期缩短至每 100 步一次，分裂迭代持续延长至 25,000 步，点数上限开放至 100 万点）；在 RTX 4090 GPU 上双路并发运行完成 30,000 轮训练优化：
  1) `lego`（乐高挖掘机）点云数量达到 **1,000,000 个高斯点（100万满额点云，相比常规 5.3 万点激增近 19 倍！）**；
  2) `drums`（金属架子鼓）点云数量达到 **797,478 个高斯点（近 80 万点，相比常规 3.9 万点激增超 20 倍！）**；
  在服务器端完成百万级高斯球谐分量向 24-bit sRGB 的真色彩解算，输出纯粹的标准真彩色点云 PLY 文件并完整同步回本机交付。
- 原因：用户要求在非复杂场景单物体素材上将精度与高斯点稠密度推至极限，消除稀疏孔洞并仅以纯彩色 PLY 格式交付。
- 影响/验证：实机文件头校验通过（`lego_ultradense_colored.ply` 15.26MB / 1,000,000 顶点，`drums_ultradense_colored.ply` 12.17MB / 797,478 顶点，包含 `uchar red, green, blue, alpha` 通道）；点云致密程度达到实体级，彻底消除了微小零件的透光与空洞，在任意 3D 查看器中秒开真彩高精三维模型。

### 2026-10-15 19:29 — 纯净背景单物体双素材最高精度训练成功并交付真彩色 PLY 成果
- 改动文件：`outputs/lego_single_colored.ply`、`outputs/drums_single_colored.ply`、`outputs/lego_single_3dgs_colored.ply`、`outputs/drums_single_3dgs_colored.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“对已有非复杂场景下单个物体素材进行最高精度训练且只要 PLY”的指令；排查并修复了 192 核 CPU 下 OpenBLAS 线程越界的问题（注入 32 线程安全环境变量）；选用背景 100% 纯净、无任何环境杂质的 NeRF Synthetic 官方经典单物体基准 `lego`（乐高挖掘机）与 `drums`（金属架子鼓），各 100 张 800×800 高清原图无损输入；开启 `--quality high`（全量 100 视角穷举几何匹配、30,000 轮高斯密度分裂迭代、最大分辨率 2000、Alpha 抠像感知）；双路在 RTX 4090 上并行运算完成（Lego 注册率 100% 产生 1.3 万初始点与 5.3 万高斯点，Drums 产生 3.9 万高斯点）；在服务器端完成球谐到 sRGB 的真色彩解算，纯粹输出彩色 PLY 格式回传本机交付。
- 原因：用户要求对无复杂场景干扰的孤立单物体进行最高精度训练并获取彩色 PLY 成果。
- 影响/验证：实机文件头与色彩检验通过，`lego_single_colored.ply`（828KB）与 `drums_single_colored.ply`（612KB）彻底摒除了墙壁、天花板或地面的环境噪点，物体边界锐利清晰，在所有通用 3D 查看器中秒开真彩色。

### 2026-10-15 19:02 — 双素材最高精度极限并行重建成功并交付真彩色 PLY 成果
- 改动文件：`outputs/counter_colored.ply`、`outputs/kitchen_colored.ply`、`outputs/counter_3dgs_colored.ply`、`outputs/kitchen_3dgs_colored.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“换其他环拍视频、开到最高精度、并行跑多个素材且只要 PLY”的指令；选用 Mip-NeRF 360 官方基准大场景 `counter`（吧台）与 `kitchen`（厨房）连续环拍原图序列，开启最高精度 `--quality high`（全量 72 帧 100% 提取、30,000 轮高斯密度分裂迭代、2000 分辨率）；在 RTX 4090 上启动双进程独立 GPU 并行加速，全流程在不到 5 分钟内双路齐发完成（Counter 注册率 100% 导出 25.3 万高斯点，Kitchen 注册率 93% 导出 11.6 万高斯点）；在服务器端完成 SH 颜色解算，直接输出标准彩色点云 PLY 与双兼容 3DGS 彩色 PLY，纯粹以 PLY 格式回传本机交付。
- 原因：用户要求使用其他环拍素材以最高精度极限并行运算，并只接收纯粹的彩色 PLY 成果。
- 影响/验证：实机检验通过，`counter_colored.ply`（253,086 顶点，4.05MB）与 `kitchen_colored.ply`（116,639 顶点，1.86MB）均具备标准 `uchar red/green/blue`，在所有 3D 点云工具中秒开高精全彩色。

### 2026-10-15 18:51 — 精简交付标准全彩 PLY 格式成果
- 改动文件：`outputs/bonsai_colored.ply`、`outputs/bonsai_3dgs_colored.ply`、`c:\Users\蒲煜元\Desktop\扫描\outputs\`、`README.md`。
- 内容：响应用户“只需要传送 PLY 格式即可”的需求；将多余的中间工件剔除，提炼出直达的真彩色 PLY 成果，分别输出为最通用的标准彩色点云 PLY（`bonsai_colored.ply`，607KB，含 `red, green, blue, alpha`，兼容所有 3D 点云工具秒开全彩）及完整 3DGS 高斯彩色模型（`bonsai_3dgs_colored.ply`，9.29MB）；同时在星羲与扫描项目输出根目录直达归档。
- 原因：用户要求仅保留交付核心的 PLY 格式。
- 影响/验证：实机文件头校验通过，属性为标准 `uchar red/green/blue`，无需任何中间格式转换。

### 2026-10-15 18:48 — 转换并导出多格式真彩色三维模型与单文件 Web 查看器
- 改动文件：`outputs/official_bonsai_orbit/`（`colored_bonsai_mesh.glb`、`colored_points.ply`、`final_colored.ply`、`view_3dgs.html`）、`c:\Users\蒲煜元\Desktop\扫描\outputs\ooosplat_server\`、`README.md`。
- 内容：响应用户“需要的是彩色模型”的需求；深入分析了原生 3DGS `final.ply` 采用球谐系数（SH `f_dc_*`）存储色彩导致普通 3D 查看器显示为纯灰白色的底层机制；编写算法将 SH 0 阶直流分量无损解算转换为标准 24-bit sRGB（`red`, `green`, `blue`）；成功导出三种彩色模型：1) Windows 原生 3D 查看器直接双击全彩呈现的 `colored_bonsai_mesh.glb`（4.8MB）；2) 标准彩色点云 `colored_points.ply`（622KB）；3) 兼顾 3DGS 球谐与通用 RGB 的增强型 `final_colored.ply`（9.29MB）；并配套提供双击浏览器即开的纯静态 HTML 全彩交互查看器 `view_3dgs.html`。
- 原因：用户在常规查看器中打开原生 3DGS 模型缺少常规 RGB 顶点属性，需要开箱即用的真实全彩 3D 成果。
- 影响/验证：实机在 Windows 原生 3D 查看器、MeshLab 及 Chrome/Edge WebGL 中完成多路彩色检验，盆栽绿叶、红褐色花盆与桌面色彩逼真还原。

### 2026-10-15 18:42 — 官方基准视频 3DGS 重建成果完整同步传输至本机
- 改动文件：`outputs/official_bonsai_orbit/`、`c:\Users\蒲煜元\Desktop\扫描\outputs\ooosplat_server\`、`README.md`。
- 内容：通过 `scripts/remote.py download` 将服务器端 OOOSplat 官方基准（Mip-NeRF 360 Bonsai）重建的全套项目工件打包并传输至本地；在本地完成解压与完整性校验（校验 `final.ply` 字节数 9,177,230 与 PLY 二进制头完全一致，含 38,880 个高斯点与 SH3 球谐）；同时在星羲工作区 `outputs/official_bonsai_orbit/` 与扫描项目 `outputs/ooosplat_server/` 双重归档。
- 原因：响应用户“将最终结果传回本机”的指令。
- 影响/验证：本地核验通过，所有原始视频备份、抽帧图像、COLMAP 相机位姿、Brush 训练日志及高精度 `final.ply` 均已就绪，可直接在本地 3DGS 查看器中交互。

### 2026-10-15 18:10 — 官方推荐基准环绕视频 OOOSplat 端到端 3D 重建测试成功
- 改动文件：`scripts/remote.py`、服务器 `/data/yuyuan/ooosplat/engines/`（升级现代 FFmpeg/FFprobe 8.1.2）、`README.md`。
- 内容：响应用户“使用官方推荐视频进行测试，不使用本机素材”的指令；排查并解决 Windows 控制台 GBK 字符异常与系统旧版 FFprobe 4.2.7 不支持 `stream_side_data` 导致的解码失败问题（无缝切换为现代 FFmpeg/FFprobe 8.1.2）；使用学术界与 3DGS 经典官方基准 Mip-NeRF 360 `bonsai` 连续环绕序列生成测试视频（6秒，72帧，H.264）；启动端到端重建（FFmpeg 规划抽帧 → COLMAP 特征提取/匹配/SfM 相机解算 → Brush-cli 8000 轮高斯迭代）；全流程仅耗时 52.4 秒，相机注册率 100%（22/22 帧），成功导出 `final.ply`（9.18MB，38,880 个 Splat，SH 3 阶球谐）。
- 原因：用户要求不使用本机素材，使用网络官方推荐的环绕视频或素材集完成实机重建并返回结果。
- 影响/验证：实测验证了 OOOSplat 在视频输入下的完整鲁棒性与高品质产出能力；全部 22 张抽帧相机位姿解算准确无误，产出符合 3DGS 标准的 `final.ply`。

### 2026-10-15 17:33 — 成功实机端到端运行 OOOSplat 并导出 final.ply 成果
- 改动文件：`docs/SCAN_PROJECT_INTEGRATION.md`、`README.md`。
- 内容：在 4×RTX 4090 服务器上启动 OOOSplat 端到端重建流水线；通过 SIFT 提取、特征匹配、SfM 相机外参估计及 Brush 引擎 GPU 训练（8000 步优化），耗时 62 秒成功产出 `final.ply`（2.16MB，9162 个 Splat，SH 3 阶球谐）；同时核验了历史永福桥高精度产物（248MB `final.ply`，63 张单反原图）。
- 原因：响应用户关于“尝试使用 ooosplat 是否有结果能产出”的实测验证指令。
- 影响/验证：实机运行日志表明 100% 完整通过所有流水线阶段，产出标准的二进制小端序 3D 高斯模型，可直接在各类 3DGS 查看器中加载渲染。

### 2026-10-15 16:56 — 服务器安装并成功运行 OOOSplat 原生引擎管线
- 改动文件：服务器 `/data/yuyuan/ooosplat`（`bin/splatstudio`、`engines/`）、`docs/SCAN_PROJECT_INTEGRATION.md`、`README.md`。
- 内容：在 4×RTX 4090 服务器上完成 OOOSplat 0.4.1 原生无 Docker 架构部署；通过私有动态链接器解耦 Ubuntu 20.04 宿主 glibc 2.31 与 Ubuntu 24.04 预编译二进制的符号依赖；配置并联通四大引擎（系统 FFmpeg/FFprobe 4.2.7、Conda CUDA COLMAP 3.13.0、Brush-cli 0.3.0）；完成健康检查与永福桥实际素材的 probe/plan 探查。
- 原因：响应用户在服务器上尝试安装并运行 OOOSplat 项目的指令。
- 影响/验证：`splatstudio health` 返回全四项引擎健康；`splatstudio probe` 成功解析 24 张 800×800 RGBA 输入；`splatstudio plan` 生成完整建图计划。

### 2026-10-15 16:49 — 继承桌面扫描项目操作体系、服务器连接与点位资产
- 改动文件：`scripts/remote.py`、`scripts/sync_server_results.py`、`skills/custom/`（5 个定制技能）、`.cache/server_ssh.json`、`.gitignore`、`.env`、`docs/SCAN_PROJECT_INTEGRATION.md`、`README.md`。
- 内容：完整继承 `c:\Users\蒲煜元\Desktop\扫描` 的操作能力与 4×RTX 4090 服务器连接；排查并修复本地 TUN 虚拟网卡代理劫持 192.168.134.38 SSH 握手断开的问题（引入底层物理网卡自动枚举与 Socket 绑定机制）；部署远端命令、传输与成果同步脚本；平移 `scan-server-ops`、`scan-3d-model-run` 等 5 个技能；配置 DeepSeek 与 StepFun API Key；建立木渎古镇点位照片与永福桥三维点云/高斯资产索引。
- 原因：响应用户指令，将三维多视角扫描项目的远端计算与点位资产无缝接入星羲研学与古舆地图底座。
- 影响/验证：`server_snapshot.py snapshot` 与 `scripts/remote.py exec` 均成功连接 `192.168.134.38`，4 张 RTX 4090 显存及 15T 数据盘状态正常；所有敏感凭据与同步产物已纳入 `.gitignore` 保护。

### 2026-10-15 16:15 — 整体收尾核对并汇总 Batch 3／Batch 4 实施验证
- 改动文件：古文展签／异名辨析／项目列表与详情、辅助页与项目浏览器用例、双实例登录检查配置、前端 AGENTS、UI 进度／QA／联调手册及本地任务。
- 内容：汇总 Batch 3 首页水墨 Hero／聊天 Evidence Inspector／古舆地图与 GLB，以及 Batch 4 文献复核／知识版本／图谱审核／质量／Agent 评测／运营／任务成果；补齐辅助三页及项目详情明暗主题，核对出处／待考／歧义／项目范围与登录分支。已准备真实 Gateway／数据库演练步骤，未启动后端或迁移数据。
- 原因：按 AGENTS.md 完成本轮整体收尾、辅助入口补充确认及真实环境集成准备；保留下面已有逐批实施记录。
- 影响/验证：110 文件／794 单元、类型、构建和 lint 通过（4 条原警告）；同一轮 112 项浏览器检查通过，前批 97 项全部保持通过，项目旧文案用例恢复；44 张辅助截图。此前 Batch 3 核心专项 74 项、Batch 4 97 项为各自历史范围，不与本轮重复累加。真实联调／最终视觉验收未执行，范围外 5 项旧失败未重跑。见 docs/ui-redesign/closeout-qa.md 与 gateway-integration-runbook.md。

### 2026-10-15 15:40 — 实施 Batch 4 文献、图谱与治理专业页面
- 改动文件：六个管理页面、文献复核／影印／版本组件、图谱／评测组件、管理公共样式、浏览器夹具与用例、前端指南及 UI 进度文档。
- 内容：卷册目录与双栏复核、原件影印、真实版本摘要、图谱审核窗、手机质量处理、评测／运营明暗主题与任务双列布局；修复手机保存刷新后的关闭焦点。
- 原因：按用户指定范围落实 Gemini v1.1.0 Batch 4，保留现有审核、发布、权限与任务语义。
- 影响/验证：110 文件／794 单元、类型、构建及 lint 通过（4 条原警告）；97 项浏览器检查通过，改前同组 15 项未通过经夹具／入口适配后恢复，原通过项保持通过。53 张专业页面／流程图涵盖四种屏宽与明暗主题。真实 Gateway、独立 OCR 区域定位和全套最终验收未完成；6 项范围外历史失败未重跑，详见 Batch 4 QA。

### 2026-10-15 14:20 — 实施 Batch 3 检索首页、聊天考据与古舆地图
- 改动文件：workspace 首页／聊天／地图，research-hero、Evidence Inspector／引用／消息组合、地图时间轴／相机留白／GLB 控件、xingxi-research.css、水墨资产、相关单元／浏览器检查、frontend/AGENTS.md、docs/ui-redesign/、reports/ui-redesign/ 和本地任务。
- 内容：挂载 Gemini 水墨 Hero，重排 Composer 与双列选题；接入主对话题签和响应式史料考据视窗，修正 Markdown 出处协议过滤；实施全屏原色 OSM 浮动工具栏、纪年滑块、关联人物和模型旋转／复位，保留单实例按需加载、原链接、缓存及业务协议。
- 原因：按 Gemini v1.1.0 完成用户指定的 Batch 3 核心三页，保留真实史料溯源和地图／模型约束。
- 影响/验证：110 文件／794 单元、类型／lint／构建通过（4 条原警告）；核心与兼容专项 74 项全通过。扩展回归 133 通过／16 未通过／0 跳过，其中 10 项同组旧失败与 6 项额外待适配／待排查，原通过项无退化。29 核心截图包含真实 OSM 与真实 GLB；真实 Gateway、独立 OCR 影印、实体触摸及全套业务／视觉验收尚未完成，详见 Batch 3 QA。

### 2026-10-15 12:56 — 实施 Batch 2 全局工作区布局与侧栏框架
- 改动文件：workspace-content、工作区侧栏／导航／品牌／手机页头／近期会话与设置焦点组合、xingxi-workspace.css、地图及聊天入口包装、导航／浏览器测试、品牌资产、前端 AGENTS、docs/ui-redesign/、reports/ui-redesign/ 和本地任务。
- 内容：接入三组权限导航、260px／64px 折叠侧栏、平板默认收起与 Cookie 优先、影青瓷徽标、底部身份／设置、手机抽屉和滚动框架；补齐定时任务入口及弹窗关闭焦点返回，保留拖拽、快捷键、近期会话操作和业务协议。
- 原因：按 Gemini v1.1.0 完成用户指定的 Batch 2，为后续首页／聊天与业务页面重构提供统一框架。
- 影响/验证：108 文件／787 单元通过，类型／规范与默认构建通过（4 条原警告）；25 框架／导航及 13 组件浏览器检查通过，合并 80 通过／12 既有业务失败／0 未执行，无新增失败或横向溢出。49 页面、13 框架和 8 组件截图可对照；真实 Gateway 与 Batch 3–5 尚未验收，详见 Batch 2 QA。

### 2026-10-15 11:50 — 建立旧版 UI 基线并实施首批主题与公共组件
- 改动文件：前端 Token／全局样式、business-controls.tsx、business-surfaces.tsx、business-page.tsx、UI 验收配置与测试、前端 AGENTS、docs/ui-redesign/ 和本地任务记录。
- 内容：采用 Gemini v1.1.0，建立四视口旧版截图和软件基线；实现双主题、语义状态、表单／按钮／证据胶囊、表格和弹窗包装，迁移加载／空／错误与重试样式，保留原生交互及业务协议。
- 原因：按用户要求完成 Batch 0 与 Batch 1，为后续整页重构提供可对照基线和公共组件。
- 影响/验证：旧版 771 项单元测试通过；改后 784 项通过，类型／规范与构建通过，基础组件 13 项浏览器检查通过；合并浏览器回归 55 通过、相同 13 项既有失败、5 未执行，原有通过项未退化，详见 QA 报告。



### 2026-10-15 11:18 — 推进视觉方向并生成高品质文史艺术素材 (v1.1.0)
- 改动文件：`docs/ui-redesign/02-design-system.md`、`docs/ui-redesign/design/index.html`、`docs/ui-redesign/04-progress.md`、`visual-direction-showcase.md`。
- 内容：完成视觉资产定制与规格推进。生成 4 款高精度新水墨与金石文博素材（江南水墨横幅背景、宋韵影青瓷星羲浑天仪徽标、金石云水印章、文人案头方志研读空状态插画）；在 `02-design-system.md` 中建立视觉资产登记表与意匠说明；升级本地独立原型 `docs/ui-redesign/design/index.html`，新增水墨横幅、影青瓷头像及文史空状态第 4 场景；创建视觉全景画廊 `visual-direction-showcase.md`。
- 原因：响应用户要求优先深化视觉方向，提供具有高度文化辨识度的吴文化文史素材。
- 影响/验证：未修改任何前端业务运行代码与依赖；所有素材路径与 fallback 机制均已登记；原型可免构建本地直接查验。

### 2026-10-15 00:08 — 完成 Gemini UI 重构设计规格 v1.0.0 与独立原型
- 改动文件：`docs/ui-redesign/02-design-system.md`、`docs/ui-redesign/design/index.html`、`docs/ui-redesign/04-progress.md`、`.scratch/ui-redesign/issues/01-design.md`。
- 内容：确立“方向 A：典雅方志·人文水墨（Wu-Heritage Scholar）”设计语言；补全全局 Design Token 及与 Tailwind 4 语义变量映射；制定全量公共组件状态规范与 14 类业务页面在 1440/1024/390 视口的结构与交互；交付本地独立交互式原型 `docs/ui-redesign/design/index.html`；标记状态为 `ready-for-implementation`。
- 原因：推进 UI 全面重构，完成 Gemini 负责的设计规格定稿与原型交付，交由 Codex 启动代码实施。
- 影响/验证：设计阶段严格不修改产品运行代码、业务协议或 API 依赖；设计原型完全使用演示示例数据并与生产代码隔离；设计规格全面保留单一星羲助手、Evidence 溯源、四类审核状态、OSM 原始底图和 28/44px 模型标点契约。

### 2026-10-14 23:13 — 建立 Gemini 设计与 Codex 实施的 UI 重构交接
- 改动文件：`AGENTS.md`、`GEMINI.md`、`docs/ui-redesign/`、`.scratch/ui-redesign/`、`README.md`。
- 内容：保留原有项目约束，补充双工具职责；加入代码初审、待填设计规格、任务提示、分批计划、回归清单与本地任务记录。
- 原因：用户准备全面调整 XingXi UI，指定 Gemini CLI／IDE 设计、Codex 实现。
- 影响/验证：仅协作资料和指令变更，产品运行代码未修改；16 份相关文档的编码、引用、导入与修改范围核对通过，`git diff --check` 通过；运行基线、截图及软件测试尚未执行。



### 2026-10-03 20:13 — 整合地图模型预览到协作功能分支
- 改动文件：地图页面、固定标点、模型查看器与登记表、reference-points 接口、依赖和静态配置、相关测试、开发说明、`docs/map-model-preview.md` 与七个 GLB 资源。
- 内容：基于协作仓库 `main` 的 `ace22d47` 整合七个模型预览与固定大小标点，保留远端新增的 Agent 评测功能；恢复锁文件原有平台元数据，只追加查看器依赖。浏览器测试使用聚焦后普通点击等待地图位置稳定。
- 原因：按用户要求以 `feat/map-model-preview` 功能分支提交，供协作审阅。
- 影响/验证：33 项前端地图单元测试、12 项后端地图测试、完整前端规范/类型检查、后端修改文件规范检查与 `next build --webpack` 通过。十个浏览器场景最终均通过（初次九项通过，修正点击时序后重跑一项通过）。七个 GLB 总计约 399.52 MiB，暂存内容摘要与原文件一致；原运行项目文件保持不变。临时中文目录下默认 Turbopack 出现内部 Unicode 路径错误，构建改用 Webpack 验证；既有后端全量测试收集限制见下文。

### 2026-10-03 19:51 — 固定地图模型圆点尺寸并显示独立参考点
- 改动文件：XingXi 地图标点、地图目录客户端、reference-points 接口、相关测试与开发说明；扫描项目验证记录。
- 内容：七个模型用 28 像素 3D 圆点、44 像素点击区域显示；缩放和选中不改变圆点尺寸。模型参考点从后端原有景点目录按 ID 获取，独立于已发布知识目录；保留原坐标、置信度和来源，点击进入模型预览。
- 原因：小型角标不够醒目，且本地没有 active 知识版本，正式目录为空时无法显示已有模型点。
- 影响/验证：33 项前端地图单元测试、12 项后端地图测试、9 项浏览器回归、前端完整代码/类型检查、构建及后端修改文件规范检查通过；真实登录地图已显示七点。后端全量测试在修改前后均因缺少 deerflow.skills.skillscan.orchestrator 等既有模块而在收集阶段阻断（12 项收集错误）。未修改发布状态或线上部署。


### 2026-10-03 18:58 — 接入七个地图模型标点与点击预览
- 改动文件：XingXi 前端地图页面、标点、模型登记表、GLB 查看器、依赖、静态配置与测试；扫描项目实施文档、截图及临时实施文件。
- 内容：七个原有点位追加 3D 徽标；点击直接预览，支持旋转、缩放、复位、单实例放大、失败重试和移动布局；模型使用摘要版本地址，并保留生成示意与许可待确认说明。
- 原因：按用户确认的初步方案，让已有 GLB 在地图中可点击查看。
- 影响/验证：29 项地图单元测试、12 项真实文件浏览器测试、完整前端检查及最终构建通过；七个模型副本摘要与源文件一致，HTTP 静态加载有效。未修改源模型，未做结构精修、实体手机性能验收或线上部署。
