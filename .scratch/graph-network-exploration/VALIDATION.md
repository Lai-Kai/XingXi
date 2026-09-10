# Graph network exploration validation

Date: 2026-09-09

## Passed

- Backend regression: 20 tests across `test_knowledge_graph_router.py`,
  `test_xingxi_graph_tool.py`, `test_graph_persistence.py`, and
  `test_relations_events_geo_graph.py`. The new route test failed on missing
  `release_id` before the implementation and passes afterward. SQLite async
  tests used a test-process-only 10 ms event-loop tick to work around worker
  wakeups in the sandbox; no application event-loop policy was changed.
- Ruff check and format check for the changed router and route tests.
- Frontend full ESLint and `tsc --noEmit`, rerun after the final failure-state
  and loading-control changes.
- Prettier check for the page, graph API/types, and graph unit/browser tests.
- Playwright discovers both graph tests successfully (`--list`). This is only
  test discovery; it is not a browser acceptance pass.
- Scoped `git diff --check`.

Frontend commands use Node 22 from `/tmp/node-v22.14.0-linux-x64/bin` and the
existing `frontend/node_modules/.bin` executables because the default Node is
18 and `pnpm` is not on PATH.

## Real data, read-only

Queried the actual SQL repository and graph service against
`backend/.deer-flow/data/deerflow.db` using SQLite `mode=ro`; no migrations,
initialization, review, ingestion, or database mutations were performed.
The active Release was `release-2c7aafe43b4247fa86ab0d6b951590e7`.

| Center | Hops | Nodes | Relations | Peripheral relations | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: |
| 灵岩山 | 1 | 4 | 3 | 0 | 2 |
| 灵岩山 | 2 | 8 | 7 | 4 | 2 |
| 灵岩山 | 3 | 11 | 10 | 7 | 3 |
| 木渎 | 1 | 4 | 3 | 0 | 2 |
| 木渎 | 2 | 8 | 7 | 4 | 2 |
| 木渎 | 3 | 10 | 9 | 6 | 3 |

All six queries returned `supported` and `truncated=false`. Peripheral means
neither endpoint is the selected center. Counts establish available graph
data, not human review or historical truth of every record.

## Incomplete checks and runtime status

- The full backend suite was attempted before and after the graph change.
  Collection fails at `tests/blocking_io/test_skills_reload.py` with
  `ModuleNotFoundError: deerflow.skills.skillscan.orchestrator`, an existing
  unrelated checkout issue.
- Rstest cannot start because its server-port probe fails with
  `listen EPERM: operation not permitted 127.0.0.1:3000`. A middleware-mode
  configuration did not remove that probe and the unsuccessful helper was
  removed. Graph unit tests are present but were not executed by Rstest.
- Normal Playwright requires a local Next.js server, also blocked by the
  sandbox's port restriction. Browser interaction tests were added and
  discovered, but not executed.
- No verified live reload or deployment. The change is in the workspace.
