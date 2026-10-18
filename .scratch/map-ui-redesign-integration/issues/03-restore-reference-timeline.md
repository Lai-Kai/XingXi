# Restore the sourced reference chronology and keep event tracks visible

Status: ready-for-human

## Problem

After the native restart, both map endpoints return 200. The active v2 map asset
contains zero events and points. Model reference points are supplemented separately,
but the five existing evidence-backed reference events are not. The added year
slider also precedes the event tracks inside a panel capped at 176/200 pixels,
which pushes the event nodes below the initial viewport.

## Acceptance

- Expose the existing curated reference events separately from knowledge Releases.
- Supplement only events with real provenance bound to exact visible reference
  point IDs. Keep corpus event identity, release and review status authoritative.
- Keep a failed optional reference request from discarding the base map.
- Show event tracks first within the existing compact height caps.
- Add source/API and browser regressions, and record native activation steps.

## Comments

- Read-only inspection confirms active Release v2 has an empty map snapshot.
  Native logs confirm the previous restart applied `0047_merge_map_reconstruction`
  and custom-point/catalog requests now return 200. No live records were modified.
- Added `/api/map/reference-events` for the five original sourced records. The
  client supplements only exact visible reference points, preserves released
  event IDs/status, and isolates optional failures with a three-second deadline.
  Event tracks precede the year slider; reference details show a provenance badge.
- Regression proof: the new backend tests first failed (two failures), then the
  26-test catalog/reference/custom-point suite passed. The frontend API regression
  first failed (one failure); all 64 map/config tests now pass.
- Full `pnpm check` passes with zero errors and four existing graph warnings.
  Webpack production build passes, including TypeScript and all 81 generated
  pages. Ruff and targeted Prettier checks pass.
- All 36 browser scenarios in six files collect successfully. Browser execution
  still requires host ports. Native activation and authenticated desktop/mobile
  verification remain: stop/start the host launcher as documented in
  `docs/map-ui-redesign-integration.md`, then refresh `/workspace/map`.
- Full backend collection has the same 12 baseline errors before and after this
  fix, caused by the missing `deerflow.skills.skillscan.orchestrator` module.
  Verification logs are under `/tmp/xingxi-ui-map-integration-h5nm0gpj/timeline-*`.
