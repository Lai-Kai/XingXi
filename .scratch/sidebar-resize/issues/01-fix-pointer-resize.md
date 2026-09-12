# Fix desktop sidebar pointer resizing

Status: ready-for-human

## Scope

Unify the desktop sidebar width limits in its provider and make the permanent
sidebar rail own pointer capture, resizing, collapse/expand transitions, and
cleanup.

## Comments

- 2026-09-11: The rail was only a click target. Its hover `::after` painted the
  green-tinted vertical line, while no pointer lifecycle or resizable width
  state existed. The rail also sat inside a lower stacking context than the
  workspace header.
- 2026-09-11: Added clamped provider width state and Pointer Events with capture.
  A single cleanup path handles pointer up/cancel, capture loss, window blur,
  Escape, and unmount; Escape restores the drag-start state. The icon-mode rail
  remains mounted and can reopen the sidebar above the expansion threshold.
- 2026-09-11: Added Playwright regressions for repeated collapse/reopen, release
  over main content, maximum width, Escape rollback, blur cleanup, body styles,
  and the rail pseudo-element. TypeScript, ESLint, Prettier, and `git diff
--check` pass. Rstest and Chromium cannot start in the current sandbox because
  it provides Node 18 and denies the required listen/socket syscalls; run the
  focused browser spec under the project's supported Node 22 environment.
