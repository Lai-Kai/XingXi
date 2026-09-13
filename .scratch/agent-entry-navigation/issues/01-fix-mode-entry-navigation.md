# Unify Xingxi chat entry navigation

Status: ready-for-human

## Scope

Use one canonical new-chat entry and keep model choice in the configured model
selector. Prevent stale research-project fields in local settings from causing
the new-chat entry-context synchronization effect to update without converging.

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
- 2026-09-12: The empty dynamic chat URL still failed in the deployed runtime
  because `/workspace/chats/new` had no explicit route segment or matching chat
  provider layout. The primary actions now use the explicit static new-chat
  route (`?mode=pro` or `?mode=flash`), which reuses the canonical chat page and
  providers. A real prompt still replaces that entry with the created thread
  URL; direct refreshes retain the mode query.
- 2026-09-12: Product direction changed after review: model strength is selected
  by the existing configured-model picker, not by separate `pro` and `flash`
  pages. The agent and research entry surfaces now generate only the canonical
  `/workspace/chats/new` route. Legacy `pro`, `flash`, and `ultra` query links
  normalize to that route while retaining prompt and evidence scope; `mode=skill`
  remains reserved for the skill-creation composer behavior.
- 2026-09-13: Follow-up diagnosis confirmed that the route and RSC response were
  healthy. A stale `research_project_id` made the new-chat effect compare the
  stored project to an absent `projectScope`, then write the unchanged full
  runtime context on every settings-store notification. The effect now compares
  mode, project, and daily-topic targets separately, clears project fields for
  entries without `project_id`, and writes only changed fields. Playwright
  coverage preloads the stale project, exercises both standard links and browser
  back navigation, and verifies a current project replaces the stale scope.
- 2026-09-13: TypeScript, full ESLint, Prettier, diff checks, Playwright test
  collection, and direct mode-mapping assertions pass. The system Node is
  18.20.8 while Next.js/Rstest require Node 20+; using the Node 24 bundled with
  VS Code Server passes that version gate, but the sandbox denies Rstest's
  `127.0.0.1:3000` listener with `EPERM`. Chromium also exits from
  `sandbox_host_linux.cc:41` with `Operation not permitted`. A Node 24 production
  build was stopped after Turbopack remained in its compile phase without output
  or CPU activity. Run the browser regression in the normal Node 22 frontend
  environment.
- 2026-09-13: Product direction was confirmed again: professional and lightweight
  behavior are model choices, not separate pages. The two mode URLs and buttons
  were replaced by one `/workspace/chats/new` entry. Generated links no longer
  contain `mode`; old `pro`, `flash`, and `ultra` links redirect to the canonical
  URL while preserving other parameters. The stale project-scope convergence
  fix remains in place.
