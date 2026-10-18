# Keep the map usable when supplementary custom-point loading fails

Status: ready-for-human

## Problem

The native Gateway returns 200 for `/api/map/catalog` and 404 for the newly added
`/api/map/custom-points`. The launcher runs Uvicorn without hot reload; the running
process has not loaded the new routers. `Promise.all` makes the optional request
failure discard the successful catalog and replaces the whole map with an error.

## Acceptance

- Render the main catalog without waiting for custom points.
- Keep custom-point failures visible with a separate retry action and retain
  previously loaded points on a transient failure.
- Preserve fatal catalog errors, cancellation, successful creation and exact IDs.
- Explain how to restart the existing native deployment and apply migrations.

## Comments

- Confirmed in the native Gateway and Nginx logs on 2026-10-18. The deployed
  database remains at `0046_agent_evaluation_cases` with no map tables. Host
  processes and ports are isolated from this coding environment.
- Extracted `core/map/use-map-catalog.ts` so the two requests settle separately.
  The page shows an independent custom-point retry without replacing the map;
  local creations survive an older list response and retry preserves controls.
- Regression proof: four of seven tests fail against the original combined
  loading behavior; all seven pass after the fix. The map/config suite passes
  all 60 tests. Full `pnpm check` passes with only four existing graph warnings.
- Browser collection passes for all 35 scenarios in six files, including two
  new failure/delay scenarios. Execution still needs host ports. The native
  launcher's existing address-reuse patch is present; documented stop/start/status
  commands activate the backend routes and run the map migrations.
- Final Webpack production build succeeds, including TypeScript and all 81
  generated pages. Implementation and checks are complete. Host restart and
  authenticated browser verification remain external activation steps; no host
  process was stopped and no live database was changed from this environment.
- Subsequent host restart succeeded: native logs confirm the map migrations
  applied and both catalog/custom-point endpoints return 200. The later timeline
  follow-up is tracked in `03-restore-reference-timeline.md`.
