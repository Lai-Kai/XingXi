# Integrate the map changes from feat/ui-redesign

Status: ready-for-human

Source: `origin/feat/ui-redesign` at `2f952d5f`.

Integrate the map UI, persistent custom points, PLY/GLB asset import and preview,
SSH reconstruction and optional FLUX3 preprocessing into the current workspace.
Preserve existing local work, the compact timeline and the seven real GLB files.
The other workspace pages and the global redesign are outside this integration.

Acceptance:

- Floating map controls, responsive details and lazy model tabs work with the
  existing shell; timeline stays within its desktop/mobile/short-window caps.
- New API routes retain authentication, administrator writes and streaming upload
  behavior; custom points do not publish knowledge or change existing evidence.
- Both migration histories converge to one Alembic head without rewriting any
  existing revision, and upgrading from either history preserves its records.
- Import the branch regressions, run map checks and document environment limits.

The pre-integration working files and checks are saved under
`/tmp/xingxi-ui-map-integration-h5nm0gpj/`. The domain plan referenced by AGENTS.md
is absent from this checkout; existing module contracts remain authoritative.
