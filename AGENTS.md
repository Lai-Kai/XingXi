# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

## Agent skills

### Issue tracker

Project implementation work is tracked as local Markdown; never publish Xingxi work to the upstream ByteDance GitHub repository. See `docs/agents/issue-tracker.md`.

### Triage labels

Local issues use the five canonical triage role names without aliases. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context Xingxi product repository; use `../PROJECT_PLAN.md` as the current domain and phased-delivery source of truth, then consult any future `CONTEXT.md` and `docs/adr/` records. See `docs/agents/domain.md`.

It is the **monorepo orientation layer**: it maps the whole repo and points to the
module guides that own the depth. For anything inside a module, read that module's
guide rather than expecting full detail here:

- **[backend/AGENTS.md](backend/AGENTS.md)** — backend depth: harness/app split, agent &
  middleware chain, sandbox, MCP, skills, memory, IM channels, persistence/migrations,
  config system, test layout.
- **[frontend/AGENTS.md](frontend/AGENTS.md)** — frontend depth: Next.js App Router layout,
  thread/streaming data flow, code style, commands.

## What is Xingxi

Xingxi is a Wu-culture and Mudu regional-history product built by refactoring the DeerFlow
source tree. `xingxi` is the only public assistant and graph. DeerFlow's sandbox, memory,
subagent, tool, streaming, and persistence modules are internal engine capabilities; do not
reintroduce the generic Agent gallery, Agent creation flow, or DeerFlow branding into product
routes.

## Service Topology

A single `make dev` / Docker stack runs the cooperating services below:

| Service         | Port   | Role                                                                 |
| --------------- | ------ | ------------------------------------------------------------------- |
| **Nginx**       | `2026` | Unified reverse-proxy entry point — open this in the browser        |
| **Gateway API** | `8001` | FastAPI REST API + embedded LangGraph-compatible agent runtime      |
| **Frontend**    | `3000` | Next.js web interface                                               |
| **PostgreSQL**  | `5432` | Production database; Docker-internal only in PostgreSQL mode        |
| **Provisioner** | `8002` | Optional — only when sandbox is configured for provisioner/K8s mode |

Nginx is the single public entry: it serves the frontend and proxies `/api/langgraph/*`
to the Gateway's LangGraph runtime, rewriting it to Gateway's native `/api/*` routes; all
other `/api/*` go straight to the Gateway REST routers. See
[backend/AGENTS.md](backend/AGENTS.md) for the runtime and router detail.

Production Docker loads `docker-compose.postgres.yaml` only when `config.yaml` selects `database.backend: postgres`. PostgreSQL has no host port; `scripts/deploy.sh` persists its password under `DEER_FLOW_HOME` and its data in a named volume.

## Repository Map

```
deer-flow/
├── Makefile                        # Root orchestration: drives the full stack (dev/start/stop, docker, setup)
├── config.example.yaml             # Template → copy to config.yaml (gitignored) at repo root
├── extensions_config.example.json  # Template → copy to extensions_config.json (gitignored): MCP servers + skills
├── backend/                        # Python backend — see backend/AGENTS.md
│   ├── Makefile                    # Per-module backend commands (dev, gateway, test, lint, migrate-rev)
│   ├── packages/harness/           # deerflow-harness package (import: deerflow.*) — agent framework
│   └── app/                        # FastAPI Gateway + IM channels (import: app.*)
├── frontend/                       # Next.js frontend (pnpm) — see frontend/AGENTS.md
├── docker/                         # docker-compose files, nginx config, provisioner
├── skills/                         # Agent skills: public/ (committed), custom/ (gitignored)
├── contracts/                      # Cross-component JSON contracts (e.g. subagent status, skill review)
├── scripts/                        # Root orchestration scripts invoked by the Makefile (check, configure, doctor, support_bundle, serve, nginx, docker, deploy, setup_wizard)
├── tests/                          # Root-level tests (currently tests/skills/ — public skill tests)
└── docs/                           # Cross-cutting docs, plans, and design notes
```

Runtime config lives at the **repo root**: copy `config.example.yaml` → `config.yaml`
(main app config) and `extensions_config.example.json` → `extensions_config.json` (MCP
servers + skills). Both real files are gitignored and may be edited at runtime via the
Gateway API. Config schema and resolution order are documented in
[backend/AGENTS.md](backend/AGENTS.md).

Skill quality review note:
- `skills/public/skill-reviewer/` is the built-in read-only skill quality reviewer.
  It uses the harness-layer `review_skill_package` tool and contracts in
  `contracts/skill_review/`. Model-visible review data is compact and
  tag-neutralized; full raw payloads stay in tool artifacts. See
  [backend/AGENTS.md](backend/AGENTS.md) for the non-activation, SkillScan, and
  `skill-creator` ownership boundaries.

Scheduled-task note:
- The scheduled-task MVP adds a workspace page at `/workspace/scheduled-tasks` plus a background scheduler service gated by `config.yaml -> scheduler.enabled`.
- Scheduled background runs are intentionally non-interactive: they execute through the normal run lifecycle, but the lead-agent toolset excludes `ask_clarification` when `context.non_interactive=true`. The key is honored only for internally-authenticated callers (the scheduler launch path); client-supplied `context.non_interactive` is dropped.

Historical-source ingestion note:
- Stage 13 scanned-source OCR is an admin ingestion surface under `/api/source-documents`. It renders PDF/PNG/JPEG page images, uses one configured `supports_vision` model through an OpenAI-compatible endpoint, persists append-only page attempts and normalized regions, exposes failed-page retry and a low-confidence review queue, and reuses canonical file results. It does not clean OCR text, create retrieval chunks, or index content.
- Stage 14 cleaning is a separate admin ingestion step. It preserves OCR raw text and hash, appends versioned clean generations with complete rule-policy snapshots and positional changes, and exposes raw/clean comparison plus page history. Clean output is never a human-review decision and remains outside retrieval until later stages.
- Stage 15 creates immutable, versioned ChunkSets from the latest clean pages. It preserves volume/item/paragraph/page structure, raw/clean traceability, stable IDs and window policy. These rows share `wu_text_chunks` with the evidence domain but are not searchable until later indexing/review stages explicitly admit them.
- Stage 16 creates one persistent ingestion Job after a successful source upload. Job, ordered Step, and append-only Event rows track parse/OCR/clean/chunk/review/index progress. Claims use a database-wide concurrency budget plus DeerFlow-style worker leases and heartbeat renewal; restart recovery requeues only expired leases. The workflow stops at `awaiting_review` after chunking and cannot auto-index or publish before Stage 17 review.
- Stage 17 human review uses immutable `wu_review_records` plus materialized current status on exact clean page generations and Chunks. Admin-only batch decisions are atomic; rejected/disputed decisions require comments. A ChunkSet review can finalize only when every Chunk and every referenced clean page is reviewed, then advances its ingestion Job to index pending. It does not create a knowledge release.
- Stage 18 knowledge releases use immutable `wu_knowledge_releases` and exact manifest items plus one optimistic `wu_knowledge_release_state` active pointer and append-only switch events. Publish validates Chunk/page review inside the same transaction, and activate/rollback changes only the pointer. Gateway run creation overwrites client-supplied release metadata with the active Release ID/version/hash. No full-text or vector index is created in this stage.
- Stage 19 full-text search uses release-scoped `wu_fulltext_documents` and `wu_fulltext_index_states`. SQLite FTS5 trigram and PostgreSQL pg_trgm GIN are storage adapters for the same exact lexical contract. Production Release publication injects `SqlFullTextRepository`, so index rows and readiness are written before the active pointer in one transaction; activate/rollback requires a matching ready index. `search_sources` uses the Release ID frozen in Run metadata, applies current source authorization dynamically, and never performs semantic/vector recall.
- Stage 20 vector search uses versioned `wu_vector_index_versions`, `wu_vector_embeddings`, and `wu_vector_index_states`. SQLite delegates cosine KNN to sqlite-vec dimension tables; PostgreSQL uses pgvector with dimension-specific partial HNSW indexes. A build persists as `building`, embeds in configured batches, validates every vector, and switches the active index only after the complete write. Model, explicit compatibility version, and dimensions must match at query time. Dynamic source authorization remains authoritative, and lexical/vector fusion is intentionally deferred to Stage 21.
- Stage 21 hybrid search resolves one Release ID before starting both channels, runs full-text and vector retrieval concurrently with independent deadlines, rejects cross-Release responses, and applies deterministic RRF by Chunk ID. Responses expose channel status, ranks, native scores, and each RRF contribution. A healthy channel remains usable when the other times out, errors, or is not configured. Do not add source-level or review-status weights here; Stage 22 owns trust-aware reranking.
- Stage 22 reranks the Stage 21 candidate pool with an explicit versioned policy. It normalizes fused relevance, adds configured source-authority/review/verified-temporal components, then greedily applies a document-repeat penalty before truncating to `top_k`. Every hit retains its component values, reasons, and low-authority/disputed/temporal-conflict warnings. Unknown time is neutral and must never be inferred from free text. D/E and disputed candidates remain visible; the tool status becomes `inferred` or `conflicting` where appropriate.
- Stage 23 structured retrieval uses one Pydantic whitelist shared by Gateway and `search_sources`, with a matching frontend contract/client. Release/Chunk metadata lives in `wu_search_filter_metadata`; multi-valued dynasty/entity facets live in normalized `wu_search_filter_facets`. Filters compile through SQLAlchemy columns and correlated `EXISTS`, with OR within a category and AND across categories. Cursor payloads bind the Release and request fingerprint. Never infer or populate missing facets from free text; later entity/time stages own those values.
- Stage 24 alias expansion is query-time and Release-scoped. `wu_alias_index`, `wu_alias_dynasties`, and `wu_alias_evidence` preserve entity candidates, periods, review state, and real Evidence foreign keys. Only one reviewed, evidence-backed, period-compatible candidate may rewrite a query. Ambiguous aliases return candidates and block automatic replacement; missing-evidence/unreviewed/period-mismatch records remain explanatory only. Alias creation and final entity linking remain owned by later extraction/review stages.
- Evidence-bound derived knowledge may be bootstrapped from `backend/data/fuxianzhi_knowledge_seed.json`. The loader validates active-Release membership, writes deterministic `pending` entities/relations/events/GeoFeatures idempotently, and preserves any record already moved out of `pending` by human review. Map and graph clients must distinguish those drafts from reviewed records.
- Relation/event review is repeatable across all four statuses. Working-row status changes append `wu_graph_review_records` atomically; rejected/disputed decisions and changes from an existing conclusion require notes. Only administrators may use the explicit `include_rejected` list parameter or read review history. Ordinary graph/tool reads exclude rejected rows, and published Release metadata, active pointers, and asset snapshots are not changed by review.

## Commands: Root vs. Module

**Root `make` targets drive the whole stack** (run from the repo root):

```bash
make setup       # Interactive setup wizard (recommended for new users)
make doctor      # Check configuration and system requirements
make support-bundle  # Generate redacted troubleshooting summary, AI issue draft, and optional zip
make config      # Generate local config files from the examples
make check       # Check that required tools are installed
make install     # Install all dependencies (frontend + backend + pre-commit hooks)
make dev         # Start all services with hot-reload (Gateway + Frontend + Nginx)
make start       # Start all services in production mode (local, optimized)
make stop        # Stop all running services
make up / down   # Build/stop the production Docker stack (browser at localhost:2026)
make docker-start / docker-stop / docker-logs   # Docker development environment
```

Run `make help` for the full list.

**Per-module commands drive a single module** (run inside that module):

```bash
# Backend (see backend/AGENTS.md for the full set)
cd backend && make dev        # Gateway API with reload (port 8001)
cd backend && make test       # Backend test suite
cd backend && make lint       # ruff check
cd backend && make format     # ruff format

# Frontend (see frontend/AGENTS.md for the full set)
cd frontend && pnpm dev       # Dev server with Turbopack (port 3000)
cd frontend && pnpm check     # Lint + type check (run before committing)
cd frontend && pnpm test      # Unit tests
```

Rule of thumb: **root `make` = the full application**; **`backend/Makefile` and `frontend/`
(`pnpm`) = per-module work.**

## Where to Go Next

- Backend work → **[backend/AGENTS.md](backend/AGENTS.md)**
- Frontend work → **[frontend/AGENTS.md](frontend/AGENTS.md)**
- Setup & install → **[Install.md](Install.md)**, **[CONTRIBUTING.md](CONTRIBUTING.md)**
- Project overview & usage → **[README.md](README.md)** (translations: `README_zh.md`,
  `README_ja.md`, `README_fr.md`, `README_ru.md`)
- Security policy → **[SECURITY.md](SECURITY.md)**
- Changes → **[CHANGELOG.md](CHANGELOG.md)**
- Cutting a release → **[RELEASING.md](RELEASING.md)**

## Cross-Cutting Conventions

These apply repo-wide; module guides own the module-specific detail.

- **Documentation update policy** — keep docs in sync with code: update `README.md` for
  user-facing changes and the relevant `AGENTS.md` for development/architecture changes in
  the same change set.
- **Test-driven development** — features and bug fixes ship with tests. Backend tests live
  in `backend/tests/` (TDD is mandatory there; see [backend/AGENTS.md](backend/AGENTS.md));
  frontend tests live in `frontend/tests/`.
- **Format before pushing** — run `make format` (backend) / `pnpm check` (frontend). Backend
  CI enforces `ruff format --check`, so formatting must be clean before a push.
