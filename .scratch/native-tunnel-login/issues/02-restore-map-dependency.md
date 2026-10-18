# Restore the native frontend's locked model-viewer dependency

Status: ready-for-human

The map route failed to compile because `@google/model-viewer` was declared in
both the manifest and lockfile but absent from the native `node_modules` tree.

## Acceptance

- Restore the locked dependency without changing package versions or application data.
- Keep the existing native deployment and public entry on port 12026.
- Verify TypeScript, the map viewer, and authenticated Tunnel access.

## Comments

- 2026-10-15: Installed the existing lockfile with pnpm 10.26.2, `--frozen-lockfile --prefer-offline --store-dir /data/laikai/deer-flow/.pnpm-store`. The explicit store reuses the installed dependency tree's configured store and avoids the unwritable default `/data/.pnpm-store`. Restored `@google/model-viewer` 4.3.1 and its missing transitive dependencies. No manifest, lockfile, application code, accounts, or corpus data changed.
- 2026-10-15: `pnpm check` passes with zero errors and four pre-existing graph-overview warnings. Ten focused unit test files pass (36 tests), covering map contracts, assets, viewer slot, and development origins.
- 2026-10-15: The existing browser regression "a failed GLB can be retried and a point without a model keeps its overview" passes against the live native entry. It uses a short-lived existing-account session for server-side access, mocked test APIs, and the real local GLB; the temporary session file was deleted after the test.
- 2026-10-15: The public Tunnel `/workspace/map` returns 200, renders seven model badges, and reads the real authentication API with status 200. Its development WebSocket connects; there are no page errors or failed same-origin responses. Reports, screenshot, and reproducible verification script are under the native launcher's private `.runtime/` directory. The frontend recovered through automatic recompilation without a service restart.
