# Fix Xingxi mode-entry navigation

Status: ready-for-human

## Scope

Replace the primary mode-entry anchor fallback with App Router commands, enter
the existing workspace composer with a validated mode, reuse the canonical
Xingxi URL builders, expose the selected mode in page titles, and provide a
route-segment error boundary.

## Comments

- 2026-09-11: Both primary entries used `next/link` around a locally duplicated
  URL builder. Their server-rendered anchor fallback could leave the application
  in a WebView or incomplete-hydration path even though the dynamic `chats/new`
  route itself exists. The original destinations were
  `/workspace/chats/new?mode=pro` and `/workspace/chats/new?mode=flash`.
- 2026-09-11: Both commands now call `router.push` with `xingxiChatHref`; empty
  prompts are omitted. The chat page derives its visible/document title from the
  validated mode and retains the existing mode-to-runtime-context mapping.
- 2026-09-11: Added unit and Playwright regressions for exact URLs, client-only
  navigation, mode UI, persisted context, submitted run context, and browser
  back. The repository contains no Electron/Tauri or file-protocol packaging
  layer, so no alternate router was introduced.
- 2026-09-11: Full frontend ESLint and TypeScript checks pass, formatting and
  diff checks pass, and direct bundled assertions pass for both URL/context
  mappings. Playwright collects both new cases, but Chromium cannot start under
  the current seccomp profile (`sandbox_host_linux` reports `Operation not
permitted`), so interactive browser execution remains for a normal Node 22
  development environment.
- 2026-09-11: Follow-up testing showed that changing the anchor to
  `router.push` did not fix the destination: the buttons still opened the empty
  dynamic chat URL. Primary mode selection now enters the already implemented
  `/workspace` composer (`?mode=pro` or `?mode=flash`); only submitting a real
  prompt opens `/workspace/chats/new`. The workspace keeps URL, selected mode,
  document title, and downstream run context synchronized.
