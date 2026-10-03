# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with the DeerFlow frontend. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

## Project Overview

The Xingxi frontend is a Next.js 16 interface for the Wu-culture and Mudu regional-history agent. It reuses DeerFlow's thread streaming, artifacts, sidecar, and settings infrastructure internally. Product routes must present Xingxi directly; do not expose the generic Agent gallery/creation flow or DeerFlow branding.

Xingxi uses one canonical new-chat route. `core/threads/xingxi-entry.ts` carries optional prompt and evidence scope, but it does not encode model strength as a route mode. The shared composer loads configured models, persists the selected `model_name`, and sends it in run context. Reasoning controls remain composer state rather than separate product pages. Entry context synchronization on the new-chat page must clear stale project scope when no `project_id` is present and must update settings only when the targeted project or topic fields differ.

The workspace “今日选题” tab loads `/api/research-feed/daily` through `core/research-feed/api.ts`, renders the backend generation date, and schedules a refresh at the returned Shanghai midnight. The backend feed is evidence-gated: yesterday's aggregated real-query popularity is preferred and current-Release RAG topics fill missing slots. A card carries its server-verified retrieval query, document IDs, Evidence IDs, and informational Release ID through `xingxiChatHref`; the new-chat page converts those values into `daily_topic_*` runtime context, while the Gateway remains authoritative for the active Release. `search_sources` loads authorized attached Evidence first and otherwise constrains retrieval to the verified query and document scope. It must show loading/error/retry/empty states; the bundled degraded seed pool is allowed only because every entry names a real local document, Chunk, and Evidence identity, and it must never contain zero-evidence demo cards. Its “more” action expands in place through `/api/research-feed/history`, showing current and previous-day grounded feeds; it must not navigate or switch to another workspace tab.

The `/workspace/map` MapLibre canvas uses the Gateway catalog's OpenStreetMap Mapnik raster as an opaque modern base. The current reachable default is `tile.openstreetmap.de`; keep OSM attribution. Do not apply opacity, filters, blend modes, paper overlays, or automatic historical-range rendering to the base map. Initial bounds prioritize evidence points around Mudu and Lingyan Mountain so distant reference points do not make road labels unreadable. Historical and speculative extents are opt-in layer controls; selecting a point opens the docked detail surface without implicitly enabling its extent.

The Stage 10 source uploader lives in `components/workspace/source-upload-dialog.tsx`, with transport and validation in `core/source-files/`. It loads server limits and registered sources, uses `XMLHttpRequest.upload` for real per-file progress, and retains each `SourceUploadTask` so cancel and retry remain independent. Browser validation is only an early UX check; the Gateway remains authoritative for type, size, count, and source binding. The server-provided extension list now includes TXT and Markdown for Stage 12; keep the file input `accept` value derived from that response instead of hard-coding formats.

When no SourceDocument exists, the file picker remains enabled so an administrator may prepare the queue before registration. The dialog must show a prominent first-source registration action; only the actual upload action stays disabled until a source ID exists. The Gateway remains authoritative and never accepts an unbound source file.

Stage 11 conflict actions use `SourceUploadError.existingFile` plus `sourceConflictActions`: byte duplicates offer `reference_existing` and `new_version`, while same-name/different-byte conflicts offer only `new_version`. Keep those rules in `core/source-files/queue.ts`; components must not invent additional duplicate actions.

Stage 16 upload responses include `ingestion_job` and optional `ingestion_error`. `core/source-files/api.ts` owns Job/Step types plus polling, cancel, and failed-step retry calls. `source-upload-dialog.tsx` retains the Job on its queue item, polls only pending/running jobs while open, displays backend progress and the current pipeline stage, and stops polling terminal or `awaiting_review` jobs. Never infer progress from upload bytes after the file upload reaches 100%.

Stage 17 review UI lives in `components/workspace/source-review-dialog.tsx` and opens from the document row. It always loads a real ChunkSet and its exact page/Chunk queue, never prototype records. Preserve page/chunk segmented modes, stable comparison dimensions, batch checkboxes, required comments for rejected/disputed decisions, immutable history, and explicit finalize. Raw text and clean text remain side-by-side on desktop and stack on narrow screens.

The knowledge Release UI lives in `components/workspace/knowledge-release-dialog.tsx`. It publishes the latest real ChunkSet for each selected library document and renders server-owned `preparing`, `ready`, `failed`, and `active` states. Only an `active` row matching the active pointer is current; failed rows show the preparation reason and retry action, and rollback is limited to older ready rows. Keep optimistic `state_version` on publish/retry/rollback and never infer preparation success or mutate version history in browser state.

The quality workspace separates visibility from mutation. `quality:read` exposes the queue and detail pane; only `quality:review` renders status, review-note, and save controls. `quality:admin` is reserved for destructive or policy controls. Client gating is UX only, and the Gateway must enforce the same capability on every write.

**Stack**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26.2. Requires Node.js 22+ and pnpm 10.26.2+.

### Core dependencies

- **LangGraph SDK** (`@langchain/langgraph-sdk` ^1.5.3) — Agent orchestration and streaming
- **LangChain Core** (`@langchain/core` ^1.1.15) — Fundamental AI building blocks
- **TanStack Query** (`@tanstack/react-query` ^5.90.17) — Server state management
- **UI**: Shadcn UI, MagicUI, React Bits, and Vercel AI SDK elements (generated from registries — see Code Style)

`components/workspace/manual-evaluations.tsx` owns the simple manual evaluation view. It displays saved answers and rule outcomes before the input form, excludes inactive cases from submission, explains stored failure reasons, and blocks empty observations. Case creation and automatic replay are collapsible. Manual success is a rule match, never proof of historical accuracy or a new model execution.

## Commands

| Command          | Purpose                                           |
| ---------------- | ------------------------------------------------- |
| `pnpm dev`       | Dev server with Turbopack (http://localhost:3000) |
| `pnpm build`     | Production build                                  |
| `pnpm check`     | Lint + type check (run before committing)         |
| `pnpm lint`      | ESLint only                                       |
| `pnpm lint:fix`  | ESLint with auto-fix                              |
| `pnpm format`    | Prettier check (`pnpm format:write` to apply)     |
| `pnpm test`      | Run unit tests with Rstest                        |
| `pnpm test:e2e`  | Run E2E tests with Playwright (Chromium)          |
| `pnpm typecheck` | TypeScript type check (`tsc --noEmit`)            |
| `pnpm start`     | Start production server                           |

Unit tests live under `tests/unit/` and mirror the `src/` layout (e.g., `tests/unit/core/api/stream-mode.test.ts` tests `src/core/api/stream-mode.ts`). Powered by Rstest; import source modules via the `@/` path alias.

E2E tests live under `tests/e2e/` and use Playwright with Chromium. They mock all backend APIs via `page.route()` network interception and test real page interactions (navigation, chat input, streaming responses). Config: `playwright.config.ts`.

## Architecture

```
Frontend (Next.js) ──▶ LangGraph SDK ──▶ Xingxi Graph (assistant_id: xingxi)
                                              ├── Sub-Agents
                                              └── Tools & Skills
```

The frontend is a stateful chat application. Users create **threads** (conversations), send messages, set thread-scoped `/goal` completion conditions, and receive streamed AI responses. The backend orchestrates agents that can produce **artifacts** (files/code), **todos**, and goal state updates.

### Source Layout (`src/`)

- **`app/`** — Next.js App Router. Routes include `/` (landing), `/workspace/chats/new` and `/workspace/chats/[thread_id]` (the shared chat page), `/workspace/agents/[agent_name]` and `/workspace/agents/new` (custom agents), `/blog/…`, the `(auth)/{login,setup,auth/callback}` flow, `/[lang]/docs/…`, and `/api/…` route handlers (e.g. `/api/memory`).
- **`components/`** — React components:
  - `ui/` — Shadcn UI primitives (auto-generated, ESLint-ignored)
  - `ai-elements/` — Vercel AI SDK elements (auto-generated, ESLint-ignored)
  - `workspace/` — Chat page components (messages, artifacts, settings)
  - `landing/` — Landing page sections
  - `docs/` — Docs / MDX rendering components
- **`core/`** — Business logic, the heart of the app. Domains include `threads/` (creation, streaming, state), `api/` (LangGraph client singleton), `agents/` (custom agents), `auth/` (authentication), `artifacts/`, `channels/` (IM connections), `i18n/` (en-US, zh-CN), `settings/`, `memory/`, `skills/`, `messages/`, `mcp/`, `models/`, `input-polish/` (pre-send draft rewrite API), `voice-input/` (browser speech-recognition helpers), `suggestions/`, `tasks/`, `todos/`, `tools/`, `workspace-changes/` (run-scoped changed-file summaries and diff fetching), `config/`, `notification/`, `blog/`, plus rendering helpers (`rehype/`, `streamdown/`) and `utils/`.
- **`hooks/`** — Shared React hooks
- **`lib/`** — Utilities (`cn()` from clsx + tailwind-merge)
- **`content/`** — MDX content (blog posts, docs) rendered by the app
- **`styles/`** — Global CSS with Tailwind v4 `@import` syntax and CSS variables for theming
- **`typings/`** — Ambient TypeScript declarations
- Root files: `env.js` (env validation), `mdx-components.ts` (MDX component map)

### Data Flow

1. Optional composer helpers such as `core/input-polish` can rewrite the local draft before submission, and `core/voice-input` can transcribe browser microphone input into that same local draft; confirmed user input then flows to thread hooks (`core/threads/hooks.ts`) → LangGraph SDK streaming
2. Stream events update thread state (messages, artifacts, todos, goal)
3. `useThreadHistory` loads persisted conversation pages from `GET /api/threads/{id}/messages/page`, preserving the backend's thread-global event `seq`; rendering overlays checkpoint/live copies at their matching canonical identities (a summarized checkpoint may contain a protected early input plus a recent tail), suppresses checkpoint/transient prefixes whose canonical position is still behind an unloaded cursor page instead of collapsing that unknown gap before a recent anchor, then adds optimistic messages without timestamp re-sorting. History invalidation preserves already-loaded pages so their established ordering positions are not discarded.
4. Stop actions call the LangGraph SDK stream stop path; `core/threads/hooks.ts` invalidates current-thread, thread-history, token-usage, and sidebar/search caches immediately and schedules one follow-up refetch because SDK stop may finish via abort + fire-and-forget cancel before backend title finalization commits
5. TanStack Query manages server state; localStorage stores user settings
6. Components subscribe to thread state and render updates

`/goal` and `/compact` are built-in composer commands, not skill activations. `src/components/workspace/input-box.tsx` intercepts `/goal`, `/goal clear`, and `/goal <condition>` before normal chat submission, calling Gateway `GET/PUT/DELETE /api/threads/{thread_id}/goal`. Setting `/goal <condition>` also submits the condition text as the next user task so the agent starts running immediately; status and clear do not start a run. Goal and compact requests are tied to the current `threadId` with an `AbortController`, so switching threads or unmounting the composer aborts in-flight requests and stale responses cannot update the new thread's composer state. The chat pages render `GoalStatus` above the composer from `AgentThreadState.goal`, with local optimistic state until the next stream `values` update arrives. `/compact` calls `POST /api/threads/{thread_id}/compact` to summarize older active context while leaving the full visible chat history intact; it is skipped on new/empty threads and blocked server-side while a run is in flight.

Human input requests are a structured message protocol layered on normal chat history. The backend writes request payloads to `ToolMessage.artifact.human_input`, `src/core/messages/human-input.ts` owns the runtime validators/types, and `src/components/workspace/messages/human-input-card.tsx` renders the reusable card. `MessageList` owns answered/latest/pending state for visible cards, but derives answered responses from raw `thread.messages` because replies are hidden; pending cards clear when the hidden reply appears, when dispatch is dropped, or when a new `thread.error` reports an async stream failure. Page-level submit callbacks must send a normal human message and put `hide_from_ui: true` plus the response payload in the fourth `sendMessage(..., options)` argument as `options.additionalKwargs`; the third argument remains run context such as `{ agent_name }`. Composer entry points should disable normal bottom input while `hasOpenHumanInputRequest(...)` is true so users answer through the card and preserve response metadata.

Tool-calling AI messages can contain user-visible text as well as `tool_calls`. `core/messages/utils.ts` keeps these turns in an `assistant:processing` group, and `components/workspace/messages/message-group.tsx` must render the visible text as a processing step instead of treating the message as only tool metadata. This preserves provider text such as error explanations or "trying another approach" notes during tool-heavy runs.

### Key Patterns

- **Server Components by default**, `"use client"` only for interactive components
- **Thread hooks** (`useThreadStream`, `useSubmitThread`, `useThreads`) are the primary API interface
- **LangGraph client** is a singleton obtained via `getAPIClient()` in `core/api/`
- **Environment validation** uses `@t3-oss/env-nextjs` with Zod schemas (`src/env.js`). Skip with `SKIP_ENV_VALIDATION=1`
- **Subtask step history and runtime metadata** (`core/tasks/`) — the subtask card shows a subagent's full step timeline (#3779): its assistant reasoning turns interleaved with the tools it ran. `Subtask.steps[]` is accumulated live from `task_running` events (appended via `mergeSteps`, not overwritten) and backfilled on expand for historical runs by `fetchSubtaskSteps`, which pages the events endpoint scoped to one task (GET `/runs/{runId}/events?event_types=subagent.step&task_id=…&after_seq=…`) until a short page, so the run-wide limit can't truncate the timeline. `task_started` carries the effective `model_name`; `task_running` carries a cumulative usage snapshot after each completed LLM call. `core/tasks/lifecycle.ts` normalizes these additive events, and `computeNextSubtask` keeps the largest cumulative total so replayed or late SSE frames cannot double-count or roll the folded card backward. Terminal ToolMessage metadata (`subagent_model_name` / `subagent_token_usage`) restores the same values from normal history after reload; no per-card event fetch is needed. `core/tasks/steps.ts` is the pure step model: `messageToStep` (live), `eventsToSteps` (reload), `mergeSteps` (dedup by `message_index`), and `stepsForDisplay` (what the card renders — keeps tool steps + AI steps with text, drops the trailing final-answer AI step when completed since it's shown as `result`). `core/tasks/context.tsx`'s `useUpdateSubtask` applies updates against a `tasksRef` mirroring the latest state (not a closure snapshot), so a late-resolving `fetchSubtaskSteps` backfill merges into current state instead of clobbering SSE steps or sibling subtasks that arrived meanwhile. The owning `run_id` is carried onto history content messages in `buildVisibleHistoryMessages` so the card can resolve the events endpoint.

### Interaction Ownership

- `src/app/workspace/agent/page.tsx` owns the primary Xingxi chat-entry link.
  It opens the existing `/workspace/chats/new` composer without encoding model
  strength in the URL. The configured model selector in `input-box.tsx` owns
  `model_name`; do not add model-specific product routes.
- `src/components/workspace/resizable-sidebar.tsx` owns desktop workspace sidebar
  width limits and the Pointer Events resize lifecycle. Keep its rail mounted in
  icon mode and keep resize behavior out of the generated `components/ui/sidebar.tsx`.
- `src/app/workspace/chats/[thread_id]/page.tsx` owns composer busy-state wiring.
- `src/app/workspace/chats/[thread_id]/page.tsx` owns branch-from-turn submission and navigation; sidecar `MessageList` instances do not receive the branch action.
- `src/app/workspace/chats/[thread_id]/page.tsx` and `src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx` own active-goal display state for their composer overlays.
- `src/components/workspace/messages/message-list.tsx` owns human-input card answered/latest/pending gating; entry pages only translate a submitted card response into `sendMessage` calls.
- `src/core/threads/hooks.ts` owns pre-submit upload state and thread submission.
- `src/core/projects/api.ts` owns the research-project wire type and normalizes legacy SQLite `0`/`1` archive flags to booleans; `src/app/workspace/projects/page.tsx` owns active/archived counts and tab filtering. `tests/unit/core/projects/api.test.ts` and `tests/e2e/research-project-workspace.spec.ts` own the corresponding API and rendered-list regressions.

## Code Style

- **Imports**: Enforced ordering (builtin → external → internal → parent → sibling), alphabetized, newlines between groups. Use inline type imports: `import { type Foo }`.
- **Unused variables**: Prefix with `_`.
- **Class names**: Use `cn()` from `@/lib/utils` for conditional Tailwind classes.
- **Path alias**: `@/*` maps to `src/*`.
- **Components**: `ui/` and `ai-elements/` are generated from registries (Shadcn, MagicUI, React Bits, Vercel AI SDK) — don't manually edit these.

## Environment

Backend API URLs are optional; an nginx proxy is used by default:

```
NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8001
NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:8001/api
```

Leave these unset for the standard `make dev` / Docker flow, where nginx serves the public `/api/langgraph/*` prefix and rewrites it to Gateway's native `/api/*` routes.

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Core Concepts](https://js.langchain.com/docs/concepts)
- [TanStack Query Documentation](https://tanstack.com/query/latest)
- [Next.js App Router](https://nextjs.org/docs/app)

## Contributing

When adding features:

1. Follow the established `src/` structure
2. Add TypeScript types and proper error handling
3. Write unit tests under `tests/unit/` (`pnpm test`) and E2E tests under `tests/e2e/` (`pnpm test:e2e`)
4. Run `pnpm check` before committing
5. Update this `AGENTS.md` when architecture, commands, or conventions change

## Xingxi Knowledge Graph Surface

`src/app/workspace/knowledge-graph/page.tsx` has two graph modes: bounded
subject exploration and a full catalog overview. The overview must use the
release-scoped catalog already loaded by `core/knowledge-graph/api.ts`, retain
every visible connected component, and lay disconnected components out in
separate regions. Clicking a node or an overview entry returns to bounded
multi-hop exploration; preserve the returned Release ID, Evidence locators,
review labels, and server truncation state while doing so. The `all`/`people`
control filters relationship scope inside either mode and must not be treated
as a control for selecting connected components.

Relation/event cards always render the four review labels through `core/knowledge-graph/review.ts`; admins retain `components/workspace/graph-review-controls.tsx` after every decision. The controls hide the current status, disable approval without Evidence, require notes for rejection/dispute or changes from non-pending status, and retain state/note/error on failed requests. PATCH sends `expected_status` and adopts the returned record and invalidates caches; older in-flight responses cannot repopulate an invalidated graph cache. Privileged catalog requests explicitly use `include_rejected` and bypass the ordinary shared cache. The admin-only rejected filter shows a dedicated relation review list without a graph canvas; all/draft filters exclude rejected rows. Review tab/filter choices and the corrected relation's subject persist in URL parameters across reloads. Event lists follow every offset page. `tests/e2e/knowledge-graph-review.spec.ts` uses mutable server mocks to cover repeated decisions and reloads for both object types.

## Xingxi Map Surface

`src/app/workspace/map/page.tsx` loads the read-only catalog through `src/core/map/api.ts`; product data must never be reintroduced as `DEMO_*` browser constants. `src/core/map/types.ts` owns client filtering and timeline contracts, while `components/workspace/map/maplibre-canvas.tsx` owns the OSM canvas, confidence-distinct markers, study-route lines, and explicitly uncertain trajectory lines.

The map catalog client keeps a five-minute session cache and shares an in-flight
catalog request, so navigating back to the map or mounting multiple map views
must not reload the same payload. Filtering, timeline playback, route selection,
and detail panes operate on the cached catalog and must not trigger a catalog
request.

Timeline autoplay is event-driven. The Gateway marks curated records with `featured` and `importance`; `featuredTimelineEvents` sorts only dated featured records by year and stable ID, while the page owns `activeEventId` and the playback timer. The canvas focuses that exact event so multiple events in one year remain distinct, renders one pulsing Marker bubble, and preserves corpus review status in the bubble. Marker DOM must update even when raster tiles fail; only MapLibre style-backed line layers may wait for the style `load` event.

Live visitor location uses `navigator.geolocation.watchPosition`, not one-shot lookup. Start/stop and permission state belong to the page; the canvas owns one reusable user Marker and updates it independently from corpus markers so GPS updates do not rebuild every historical point. The Marker remains visible in both explore and route modes, and route mode may draw an explicitly dashed user-to-first-stop connector until a real road geometry is returned. Geolocation failures must identify the HTTPS/localhost secure-context requirement without weakening browser permissions.

Keep public provenance visible in the details pane. Historical event selection opens the event details pane with its period, place, people, description, and Evidence links; the place-details action returns to the associated map point. On narrow viewports the map and timeline appear before filters and details, with event and point details opening in bottom Sheets; on desktop the three columns scroll independently. A map source marked unavailable must remain a reference link rather than being rendered as an overlay. The GLB slot remains independent from this two-dimensional data surface.

## Operations Surface

`app/workspace/evaluations/page.tsx` owns the standalone **Agent 评测** workspace, exposed alongside map/graph through `workspace-nav-chat-list.tsx` only to governance readers and admins. The operations regression tab keeps manual evaluation and links to this route. `components/workspace/agent-evaluations.tsx` owns automatic replay batches, controls, current-batch KPI cards and table filters; `agent-evaluation-detail.tsx` owns the accessible trajectory Sheet, append-only review and exact Evidence locators. `core/operations/evaluations.ts` owns the wire contract, authenticated API calls and portable exports. Pure metrics/filter/distribution/sequence projection lives in `core/operations/evaluation-dashboard.ts`; the SVG charts in `agent-evaluation-charts.tsx` plot real planned/passed counts and only terminal pass rates, with hover/focus tooltips. History time filters and charts cover only the current server page (20 batches), not the complete database. KPI scope stays at the selected batch when the table is filtered; missing durations remain unavailable and measured sample counts are visible. Do not invent failure causes or same-condition version comparisons from these aggregates.

Polling queries are scoped by batch ID; drawer identity includes both batch and case; reruns preserve their parent and reviews append without changing the original verdict. Never render missing/empty/unfinished runs as all passed, classify expected timeout cancellation as failure, expose internal chain of thought, or describe scripted replay as real-model quality. Execution controls are admin-only; server permission checks remain authoritative. Fixtures live only in `tests/fixtures/agent-evaluations.ts`, never in the product UI. Playwright emits HTML+JSON and retains first-failure trace/screenshots/video; Rstest emits JSON when `TEST_REPORT_DIR` is set. See `../docs/agent-evaluation-testing.md`.

`src/app/workspace/operations/page.tsx` is the governance-only continuous-improvement workspace. It must use real `/api/operations` data for metrics, regression observations, corrections, and asset versions; do not add demo KPI values. `src/core/operations/api.ts` also owns fire-and-forget interaction collection for final answers, citations and map points. Missing rates render as unavailable rather than `0%`, and the three-dimensional load rate remains unavailable until the GLB pipeline is real.

## Fuxianzhi Import Surface

`src/components/workspace/corpus-import-dialog.tsx` is the source-manager view for persisted corpus batches, items, and page-level quality issues from `/api/corpus-imports`. It never scans server paths in the browser. Review pages and evidence details show physical page and optional folio separately; original files open only through the protected source-file content endpoint assembled by `sourceFileContentUrl`.

Source-level contracts include `U` for unrated internal material. Knowledge Release contracts include `scope: "public" | "internal"`; internal Releases must be visibly labelled as working versions and must never be presented as reviewed public editions. Agent citations may use `evidence://<id>`; `core/citations/sources.ts` parses that protocol and routes it to the library Evidence detail surface rather than opening it as an external URL.

Map contracts include `corpus_evidence`, `record_kind`, `review_status`, and `release_id`, but the client only renders catalog records returned by the Gateway. It must not geocode corpus names or synthesize coordinates in the browser. The map provides separate formal/draft filters, renders draft markers distinctly, and lets users select among server-derived person trajectories. Searchable fuxianzhi text, corpus drafts, and reviewed map points are deliberately different completion states.

The graph workspace provides an evidence-bound, mixed-entity relationship view centered on one subject, with direct/two-hop/three-hop controls (default two), review filters, an ordered event timeline, Evidence links, and a map handoff. It must not render a full subject index as the main graph surface. The catalog provides only an initial one-hop preview; the graph query response replaces that preview and must retain nodes and peripheral edges absent from the catalog. Refocusing can preview already-loaded graph records and Evidence, then queries the selected depth. Depth changes and refocusing reuse the Gateway's returned `release_id`; query cache keys include Release, depth, and node limit. Loading disables depth/refocus controls, and a failed depth change preserves the previous result and selection. Network views fit the returned graph and page at 80 edges (direct view: 18), while the sidebar keeps all loaded relations and their Evidence. Server truncation is distinct from display pagination. Edge labels follow the stored subject-to-object direction; clicking an edge opens its corresponding sidebar Evidence.
