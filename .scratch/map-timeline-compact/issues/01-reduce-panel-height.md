# Reduce the map timeline's vertical footprint

Status: ready-for-human

## Scope

Replace the 260–340 pixel event canvas minimum and tall event cards with compact
summaries and a bounded scrollable panel. Keep the map as the primary surface
on desktop and mobile.

## Comments

- 2026-10-17: The user reported that the historical timeline obscures the map.
  The existing expanded panel combines a 48-pixel header with an event canvas
  at least 260 pixels tall. Implementation reduces both and bounds the complete
  panel, including dense or undated event lists.
- 2026-10-17: Implemented a fixed visible header, independent two-axis scrolling,
  responsive panel caps, 56-pixel event lanes, and compact period/year summaries.
  Full event titles remain in accessible labels, tooltips, and event details.
- 2026-10-17: `pnpm check` passed with the four existing graph-overview warnings.
  Direct checks against the compiled timeline module passed for empty, single,
  dense, mixed-year/same-year, and undated inputs, including year-coordinate,
  event-fit, and dynasty-band separation checks. Existing desktop/mobile
  browser regressions now check panel height, map space, and collapse/reopen.
- 2026-10-17: Rstest could not initialize because its port probe receives
  `listen EPERM`. The two focused Playwright cases could not launch Chromium
  because the execution sandbox denies its socket operation. No browser
  assertions ran; live rendering still needs verification outside this sandbox.
