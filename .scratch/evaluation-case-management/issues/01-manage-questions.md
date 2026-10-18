# Add evaluation question management

Status: ready-for-human

## Acceptance

- View complete built-in/custom questions, method descriptions and rule checks.
- Add questions with a whitelisted method, mode and declarative expected terms.
- Delete and restore questions; preserve every existing batch and rerun snapshot.
- Persist changes in SQL; update run counts and execution selection dynamically.
- Require governance reads and administrator mutations in the backend.
- Include backend, transport/browser regressions and synchronized documentation.

## Comments

- 2026-10-17: The user requested a visible interface and add/delete controls for
  the currently hard-coded automatic evaluation questions.
- 2026-10-17: Implemented the question/method Sheet, persisted custom questions
  and built-in activation overrides, reversible deletion, dynamic catalog/counts,
  and single-question execution. Existing batch and rerun snapshots stay frozen.
  Custom questions explicitly retain the chosen synthetic replay script.

## Validation

- Backend TDD red: importing the new case dependency failed before implementation.
- Focused backend unit/migration/rule/API permission tests: **21 passed**.
  Includes replay of a custom question, inactive/duplicate/empty selection,
  bounded input fields, admin/governance restrictions, historical table/data
  preservation and the migration head. The strengthened migration history test
  also passed on its subsequent focused run.
- Ruff format and check passed for the touched Python files.
- Frontend `pnpm check` passed (four existing graph hook warnings).
- Backend full-suite baseline and post-change collection both stop at the same
  existing missing `deerflow.skills.skillscan.orchestrator` module.
- New async SQLite/HTTP integration tests timed out after 45 seconds, with the
  event loop waiting and the aiosqlite worker idle; no completed integration
  verdict. Original TestClient API tests were also not completed during the
  earlier combined run. PostgreSQL was unavailable.
- Rstest could not start: `listen EPERM 127.0.0.1:3000`.
- Both new Playwright scenarios were collected but Chromium failed before page
  execution: `sandbox_host_linux.cc ... shutdown: Operation not permitted`.
- `git diff --check` passed. Existing unrelated changes were preserved.

Logs: `/tmp/evaluation-cases-unit-final.log`,
`/tmp/evaluation-cases-focused.log`,
`/tmp/evaluation-case-management-final-full.log`,
`/tmp/evaluation-cases-frontend-check-final.log`,
`/tmp/evaluation-case-management-rstest.log`,
`/tmp/evaluation-case-management-playwright.log`.

## Activation remaining

The 12026 native launcher is `/data/laikai/heikesong/deerflow-native/start.sh`;
its Gateway runs without reload and its state is outside writable roots. This
session has not restarted it or migrated the business database. A native
stop/start loads the new backend and performs the normal automatic migration;
then open `/workspace/evaluations` and inspect **测试问题与方法**. Frontend source
changes can use the existing dev hot reload. Complete SQL/HTTP and browser
acceptance in an environment that allows the normal test runtime.
