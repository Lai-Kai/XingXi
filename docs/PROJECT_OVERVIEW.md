# Xingxi（星羲弦沚）项目整体介绍

本文按当前仓库代码、配置和产品约束说明项目的组成、主要业务链路及地图中的 GLB 三维资产接口。它描述的是现有实现；规划中的能力会明确标出，不把接口占位误写成已经完成的功能。

## 1. 项目定位

Xingxi 是一个围绕吴文化和木渎区域历史建设的知识问答与资料研究产品。用户通过唯一的公开助手「星羲」提出问题；回答应由本地文献检索结果支撑，并提供可追溯的引文。空间地图、人物关系图、历史时间线和文献工作台是围绕同一知识库提供的研究界面。

DeerFlow 留在项目内部，承担 LangGraph 运行时、模型调用、工具适配、持久化记忆、子任务、沙箱和流式通信等引擎能力。它不是另一个公开助手，也不应把通用 Agent 展示或创建流程重新带入 Xingxi 产品界面。

## 2. 服务结构

一次本地开发或部署会启动多个协作服务：

| 服务 | 默认端口 | 作用 |
| --- | ---: | --- |
| Nginx | 2026 | 浏览器统一入口；提供前端并转发 API |
| Gateway | 8001 | FastAPI REST API、运行管理和嵌入式 Agent Runtime |
| Frontend | 3000 | Next.js 产品界面 |
| PostgreSQL | 5432 | 生产数据库；PostgreSQL 部署时通常只在 Docker 网络内可见 |
| Provisioner | 8002 | 可选沙箱资源供应服务，仅在相应沙箱模式下启动 |

浏览器通常只需要访问 Nginx。它把 `/api/langgraph/*` 改写并转发到 Gateway 的运行时路由；其他 `/api/*` 请求直接转发给 Gateway。开发入口是仓库根目录的 `make dev`，Docker 生产入口由根 Makefile 和部署脚本管理。

## 3. 代码分层与各分支

### 仓库根目录与部署

- `Makefile`：编排安装、配置检查、开发启动、停止和 Docker 操作。
- `config.example.yaml`：主运行配置模板；实际 `config.yaml` 位于仓库根目录，通常被 Git 忽略。
- `extensions_config.example.json`：MCP 服务和技能配置模板；实际 `extensions_config.json` 位于根目录。
- `docker/`、`deploy/`：Nginx、Docker Compose、Helm 和可选 Provisioner 部署资源。
- `scripts/`：doctor、部署、配置向导、支持包、服务管理等运维脚本。
- `docs/`：架构、计划、操作说明及本项目介绍文档。

### `backend/app`：产品 API 层

FastAPI Gateway 将产品能力组织为 REST 路由，负责身份与权限检查、请求/响应校验、连接领域服务和数据库，并承载 IM 渠道集成。重点路由包括：

| 路由模块 | 主要职责 |
| --- | --- |
| `runs.py`、`thread_runs.py`、`threads.py` | 创建和管理运行、会话、消息及流式交互 |
| `knowledge_search.py`、`public_knowledge.py` | 知识搜索、证据详情与公开知识访问 |
| `source_documents.py`、`corpus_imports.py` | 来源登记、源文件上传及历史语料导入 |
| `knowledge_releases.py` | 知识版本发布、激活、回滚与准备状态 |
| `knowledge_graph.py`、`entities.py` | 实体、关系、事件、图谱查询和审核 |
| `map_points.py` | 地图目录、点位、图层、事件、人物轨迹、路线规划 |
| `scheduled_tasks.py`、`research_projects.py`、`research_feed.py` | 定时任务、研究项目和每日研究动态 |
| `models.py`、`mcp.py`、`channels.py` | 模型、MCP 扩展和消息渠道管理 |
| `operations.py`、`quality` 相关路由 | 运行运维、质量队列与质量审核 |

Gateway 是 API 边界，不是历史知识规则的唯一归属地。请求模型、鉴权和 HTTP 状态码在这里；历史领域不变量应落在下述 `wu_culture` 包。

### `backend/packages/wu_culture`：吴文化领域层

这是不依赖 `app.*` 或 `deerflow.*` 的领域包，负责领域数据模型、规则和服务。主要子域如下：

- `models/`、`repositories/`：来源、文件、Chunk、Evidence 等领域记录及仓储接口/内存仓储。
- `parsing/`、`ocr/`、`cleaning/`、`chunking/`：文档解析、扫描件 OCR、文本清洗和结构化切分。
- `ingestion/`、`review/`：入库 Job 状态机与文本/图谱审核规则。
- `authorization.py`：来源的可见范围、授权用途、有效期等访问判定。
- `retrieval/`、`fulltext/`、`vectors/`、`hybrid/`、`ranking/`：词法检索、向量检索、混合召回与可信度重排。
- `structured_search/`、`filters/`、`aliases/`：结构筛选、实体别名消歧与受控查询扩展。
- `citations/`、`evidence_pack/`、`conflicts/`、`compare/`：引文校验、证据组织、冲突分析和来源比较。
- `entities/`、`relations/`、`events/`、`geo/`、`graph/`、`spacetime/`：实体、人物关系、历史事件、地理要素、知识图谱及人地时空信息。
- `releases/`：不可变知识 Release 的领域规则和状态模型。
- `gloss/`、`person_qa/`、`qa_loop/`、`refusal/`：古文阅读辅助、人物问答、证据问答流程及无证据时的拒答策略。

### `backend/packages/harness/deerflow`：内部 Agent 引擎

Harness 把 Xingxi 领域服务装配到通用运行时中：

- `agents/lead_agent`、`agents/xingxi`：通用主 Agent 装配和 Xingxi 专用 Agent/工具适配。
- `agents/middlewares`：运行期上下文、工具、限制和结果处理链。
- `runtime/`：运行管理、状态与流式事件桥接；Gateway 的交互式和后台任务应复用此生命周期。
- `tools/`、`mcp/`、`subagents/`：内置工具、MCP 工具和受控子任务能力。
- `sandbox/`：命令、文件操作等隔离执行接口及其实现。
- `memory/`、`skills/`、`models/`：内部记忆、技能发现和模型构造。
- `persistence/`：SQLAlchemy 模型、数据库引擎、领域仓储适配器及 Alembic 迁移。

Xingxi 对用户暴露的 Agent 工具由服务端控制，核心历史回答依赖 `search_sources`；增强模式可以使用来源比较能力。Harness 中存在的沙箱、MCP、通用 Agent 或技能能力，不代表它们都会开放给 Xingxi 用户。

### `frontend`：产品交互层

Next.js App Router 页面负责用户流程，`src/core/` 放 API 客户端、类型、状态和领域前端逻辑，`src/components/` 放界面组件。主要产品分区包括：

- 星羲对话与会话历史：创建问题、选择服务端允许的模型档位、接收流式答复及证据引用。
- 文献库与入库审核：登记来源、上传文件、查看解析/OCR/清洗/Chunk 进度、对原文和清洗文进行复核。
- 知识版本与质量管理：查看 Release 状态，管理审核队列及适用的审核操作。
- 知识图谱：浏览人物、地点、实体关系、图谱总览和审核状态。
- 古舆地图：显示地图点位、历史图层、时间线、人物轨迹、资料证据和路线规划。
- 研究项目、研究动态、定时任务、名物/术语辅助和运行运维等工作台。

前端 `core` 类型一般把 Gateway 的 snake_case JSON 字段转换为 camelCase 页面对象。例如地图 API 在 `src/core/map/api.ts` 中完成字段转换，`src/core/map/types.ts` 定义页面使用的地图模型。

### `tests`、`skills` 与 `contracts`

- `backend/tests/`：Gateway、领域服务、仓储和运行时测试；迁移相关测试也在此处。
- `frontend/tests/`：按 unit 与 e2e 分层的前端测试。
- 根目录 `tests/`：目前用于公共技能等跨模块测试。
- `skills/public/`：随仓库维护的公共 Agent 技能；`skills/custom/` 是本地自定义目录。
- `contracts/`：跨组件 JSON 合约，例如子任务状态和技能审核结果。

## 4. 核心业务链路

### 有证据约束的问答

1. 用户在 Xingxi 对话中提问，Gateway 创建 Run，并固定本次运行使用的知识 Release。
2. Xingxi Agent 调用领域搜索工具；检索先处理已授权的关联 Evidence，再在当前 Release 和来源访问规则内查询。
3. 搜索候选由词法、向量或混合检索通路提供，重排会考虑相关性、来源权威性、审核状态和时间信息。
4. Agent 的回答通过引文合约进行校验并流式回传。没有明确文献支持时，产品需要说明未核验，而不能把“没有搜到”说成历史上不存在。

### 历史资料入库

主干流程为：来源登记 → 原始文件上传与去重 → 文档解析或扫描件 OCR → 清洗版本 → 结构化 ChunkSet → 人工审核 → 知识 Release → 搜索索引。

- 原始文件按内容哈希识别重复文件；重复引用可指向规范文件，显式新版本关系单独记录。
- OCR 尝试、清洗生成、ChunkSet 和人工审核历史均保留版本或追加记录，不直接覆盖历史。
- 入库 Job、Step 和 Event 持久化处理进度；worker 通过租约和数据库并发额度领取任务。
- 入库会在需要人工复核的阶段停止。审核、索引准备、Release 发布是分开的门槛，不允许 OCR 或清洗结果自动成为公开知识。
- 来源授权会在查询时动态判定。索引存在并不能覆盖授权撤销、可见范围限制或授权过期。

### 搜索与知识图谱

搜索有多个协作阶段：Release 限定 → 词法/向量召回 → 混合结果融合 → 可信度重排 → 结构化筛选 → 别名消歧 → Evidence 和引用输出。词法与向量通道分别有索引状态和模型约束；混合召回允许一个通道故障时保留另一个健康通道的结果。

图谱实体、关系、事件和地理要素应绑定真实 Evidence。新生成记录可以处于待审核状态；地图和图谱界面要区分已复核记录与草稿。审核历史追加保存，驳回记录默认不出现在普通读接口中。

## 5. 数据、Release 与权限

- 数据库由 Gateway 配置选择；生产 PostgreSQL 通过相应 Compose 配置运行，开发和测试还会使用 SQLite 等轻量后端。
- 迁移位于 `backend/packages/harness/deerflow/persistence/migrations/versions/`，实体模型及仓储适配器位于 `persistence/`。
- `SourceDocument` 表示文献来源；`SourceFile` 表示原始文件；解析页、OCR 尝试、清洗页和 Chunk 表示不同处理产物；`Evidence` 是检索、引用和图谱记录的证据锚点。
- Knowledge Release 是可追溯的知识快照。发布时生成精确清单并准备搜索索引及地图/图谱等资产；激活和回滚改变活动指针，不重写旧版本内容。
- Gateway 创建 Run 时以当前活动 Release 覆盖客户端提交的 Release 元数据，因此一次对话不会在中途悄悄切换语料版本。
- 用户角色、来源用途授权、内容可见范围和具体审核能力是不同的权限边界。前端隐藏按钮只改善交互，Gateway 仍必须对每次写操作做服务端授权。

## 6. 地图 API 与地图页面

地图路由前缀为 `/api/map`，地图目录优先读取活动 Release 对应的已持久化地图快照。没有活动 Release 时，目录为空；快照缺失或校验失败时，接口会返回可重试的服务错误，而不是把失败伪装成空资料。

| 接口 | 输入 | 返回/作用 |
| --- | --- | --- |
| `GET /api/map/catalog` | 无查询参数 | 一次返回 `updated_at`、数据说明、点位、图层、事件、关系、人物轨迹和研学路线 |
| `GET /api/map/points` | `entity_type[]`、`dynasty[]`、`min_confidence`、`heritage_status[]`、`query`、`year`、`include_unknown_time` | 根据类别、朝代、置信度、遗产状态、名称/地址/摘要和年代筛选点位 |
| `GET /api/map/layers` | 无 | 地图底图和可选历史图层目录及来源/校准说明 |
| `GET /api/map/events` | 可选 `year_start`、`year_end` | 按时间区间筛选历史事件 |
| `GET /api/map/trajectories` | 无 | 人物的时空轨迹及不确定性说明 |
| `GET /api/map/routes` | 可选 `duration=half_day\|full_day` | 研学路线及停靠点 |
| `POST /api/map/route-plan` | JSON 路线请求；需要已登录用户 | 调用路线服务；不可用时返回点位顺序直线并明确标记未生成道路导航 |

点位坐标使用 WGS84 经纬度。`confidence` 为 `exact`、`approximate` 或 `speculative`；几何类型包括 `point`、`uncertainty_radius` 和 `historical_area`。近似/推测记录必须显示不确定范围，不能把置信默认半径误解为真实历史边界或统计置信区间。当前现代底图来自 OpenStreetMap，必须保留署名；历史图层是否可用由目录的 `available` 和校准说明决定。

### 路线规划请求

`POST /api/map/route-plan` 请求体：

```json
{
  "profile": "driving",
  "coordinates": [
    { "lon": 120.51, "lat": 31.25, "name": "木渎古镇" },
    { "lon": 120.52, "lat": 31.26, "name": "灵岩山" }
  ]
}
```

`coordinates` 必须包含 2 到 12 个点，至少两个坐标不同；经度范围 `-180..180`，纬度范围 `-90..90`。`name` 可省略，当前 `profile` 只接受 `driving`。成功时结果包含道路几何、`distance_meters`、`duration_seconds`、`provider` 和 `routing_status: "routed"`。OSRM 不可用或请求受限时，接口会返回输入停靠点构成的直线，`routing_status` 为 `unavailable`、`route_kind` 为 `stop_order`，并附说明；这不是道路导航结果。可通过 `XINGXI_ROUTING_BASE_URL` 设置 OSRM 服务地址。

## 7. 3D / GLB 接口现状

### 先区分两个接口

当前代码里与三维有关的是两个不同层次：

1. 地图证据媒体字段：后端 `MapEvidenceMediaOut` 允许 `media_type: "model"`，和 `url`、`caption` 一起作为证据媒体元数据返回。前端地图证据区目前把它作为普通外链呈现。
2. `GlbViewerSlot` 组件：前端地图页中的 GLB 资产展示插槽，接收 `GlbAssetDescriptor`。它不是 HTTP API，也没有在本页连接 `MapEvidenceMediaOut`。

仓库当前没有独立的三维 REST 路由，也没有实际加载 GLB 的 Three.js、`model-viewer` 或其他 3D 渲染引擎。地图页面当前调用 `GlbViewerSlot` 时传入 `asset={null}`，因此不会显示模型面板。组件注释把它标记为未来授权 GLB 资产的接口预留。

### `GlbViewerSlot` 接收参数

组件位于 `frontend/src/components/workspace/map/glb-viewer-slot.tsx`。它的 props 是 `{ asset: GlbAssetDescriptor | null }`：

| 字段 | 类型 | 必填 | 当前含义与效果 |
| --- | --- | --- | --- |
| `asset` | `GlbAssetDescriptor \| null` | 是 | 整个资产描述对象；为 `null` 时组件不渲染任何内容 |
| `id` | `string` | 是 | 资产标识；ready 状态写入 `data-glb-id` 便于定位 |
| `title` | `string` | 是 | 资产标题，显示在各状态面板中 |
| `src` | `string` | 否 | 模型资源地址；当前仅用于判断地址是否缺失和写入 `data-glb-src`，不会下载或渲染模型 |
| `poster` | `string` | 否 | 预览图地址；类型已定义，但组件当前不读取或展示它 |
| `license` | `string` | 是 | 授权/许可说明，ready 状态显示原文 |
| `evidenceIds` | `string[]` | 是 | 支撑该资产的 Evidence ID；ready 状态只把 ID 拼接显示，不会查询证据详情 |
| `sizeBytes` | `number` | 否 | 文件字节数；传入数字时显示为 MB，保留一位小数 |
| `provenance` | `"surveyed" \| "reconstructed" \| "speculative"` | 否 | 资产来源分类；只有 `speculative` 会出现“推测复原、不可作为现状或史实证据”的提示 |
| `status` | `"ready" \| "loading" \| "failed"` | 否 | 状态，默认 `ready`；控制缺源/失败、加载中或 ready 信息面板 |

示例（这是 React 组件属性，不是可直接 POST 的 API JSON）：

```tsx
<GlbViewerSlot
  asset={{
    id: "yan-family-garden-model-v1",
    title: "严家花园三维资产",
    src: "/assets/yan-family-garden.glb",
    poster: "/assets/yan-family-garden-preview.webp",
    license: "馆藏方授权，限本项目展示",
    evidenceIds: ["evidence-survey-001", "evidence-photo-014"],
    sizeBytes: 8423940,
    provenance: "surveyed",
    status: "ready",
  }}
/>
```

### 组件当前具体做什么

- `asset === null`：返回 `null`，不占页面空间。
- `src` 缺失或 `status === "failed"`：显示标题和错误/缺地址提示；此判断先于 loading 判断，因此 loading 状态也应提供 `src` 才会显示加载提示。
- `status === "loading"` 且有 `src`：显示标题和加载中的占位信息。
- 其他情况：作为 ready 面板展示标题、许可、资源 URL、Evidence ID、可选文件大小。
- `provenance === "speculative"`：显示推测复原警告，提醒不能当成现状或史实证据。
- 面板带 `data-glb-state`、ready 时的 `data-glb-id`/`data-glb-src` 属性，可供自动化测试或宿主页面识别状态。

上述行为是资产元数据与状态展示，不等于三维查看器功能。当前不会解析 GLB 文件、校验授权、显示 `poster`、显示模型画布、控制镜头/缩放/旋转、读取动画或执行证据 ID 解析；`src` 也没有被组件 fetch。只有在接入真实渲染器并确认模型来源、访问权限和许可证之后，才能把它描述为可交互的三维预览。

### 地图目录中的模型媒体

证据媒体响应形状为：

```json
{
  "url": "/assets/yan-family-garden.glb",
  "media_type": "model",
  "caption": "严家花园复原模型"
}
```

这是 `MapEvidenceOut.media[]` 中的一项媒体描述。它目前没有 `id`、`license`、`evidenceIds`、`provenance`、`status`、`sizeBytes` 等 `GlbAssetDescriptor` 字段，也没有前端适配器把该媒体对象变成 `GlbAssetDescriptor`。地图证据区只显示媒体标题链接，不会因此启动 3D 预览。不要把 `GET /api/map/catalog` 误认成 GLB 文件接口：它返回目录元数据，不负责模型上传、授权签发或模型字节流。

### 若要继续实现三维查看器

接入时应在已有证据关系上定义服务端可信的资产描述和访问策略，再由前端把明确授权的 GLB 交给选定的渲染器。至少需要约定：稳定资产 ID、模型 URL/下载权限、许可文本、关联 Evidence、来源类别、文件大小、预览图和可观测的加载状态；还需要决定格式/大小限制、跨域与鉴权、加载失败重试、低端设备降级和键盘/触控操作。历史复原模型必须持续标明“实测/复原/推测”，不得仅靠模型外观暗示史实。上述是后续设计事项，不是当前已经存在的 API 合约。

## 8. 开发与运行

从仓库根目录开始：

```bash
make setup       # 交互式本地初始化
make doctor      # 检查配置和依赖
make dev         # 启动 Gateway、Frontend、Nginx 开发服务
make stop        # 停止根目录管理的服务
```

只启动单个模块时，后端在 `backend/` 使用 `make dev`、`make test`、`make lint`；前端在 `frontend/` 使用 `pnpm dev`、`pnpm check`、`pnpm test`。更完整的配置、开发规范和测试布局以根目录 `AGENTS.md`、`backend/AGENTS.md`、`frontend/AGENTS.md` 为准。

## 9. 阅读代码的入口

| 想了解 | 入口 |
| --- | --- |
| Gateway 路由和服务装配 | `backend/app/gateway/app.py`、`backend/app/gateway/routers/` |
| Xingxi Agent 和工具 | `backend/packages/harness/deerflow/agents/xingxi/` |
| 领域模型与业务规则 | `backend/packages/wu_culture/wu_culture/` |
| SQL 模型、仓储和迁移 | `backend/packages/harness/deerflow/persistence/` |
| 地图接口 | `backend/app/gateway/routers/map_points.py` |
| 地图 API 类型转换 | `frontend/src/core/map/api.ts`、`frontend/src/core/map/types.ts` |
| 地图页面与底图 | `frontend/src/app/workspace/map/page.tsx`、`frontend/src/components/workspace/map/` |
| GLB 资产展示插槽 | `frontend/src/components/workspace/map/glb-viewer-slot.tsx` |
| 产品和模块约束 | `AGENTS.md`、`backend/AGENTS.md`、`frontend/AGENTS.md` |
