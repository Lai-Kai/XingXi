# Simple manual evaluation demo

Status: ready-for-human

Use the user's provided Lingyan Mountain answer to create one transparent manual observation. Keep archived cases and prior results. Present saved results before inputs, explain failures, block empty submissions, and place case creation and automated replay under collapsible sections.

## Acceptance

- The demo is visibly a recorded observation, with no claim of a new model call or factual accuracy.
- Only active cases appear in the input area.
- The one active refusal case permits zero citations and does not require exact wording.
- The complete user-provided answer is retained. Unverified supplementary source names are not counted as validated citations.
- Saved results and an offline HTML preview can be inspected directly.

## Comments

- 2026-10-01: The two conflicting prior cases were archived in the local database; their records remain intact.
- 2026-10-01: Saved the complete 552-character user-provided answer as manual run `027774f9-8009-4f03-a4bc-4fcbd1714b1e`, graded 1/1 with zero citations and no exact-word requirement. No new model run or business knowledge was created.
- 2026-10-01: The revised frontend view and self-contained interactive preview are complete. Preview: `reports/testing/simple-demo/index.html`. TypeScript, focused ESLint, formatting, diff checks, and five Node assertions passed. Full ESLint also found a pre-existing import-order error in the knowledge-graph page. Rstest could not bind its local server (EPERM), and Chromium could not launch under the sandbox. Docker management is denied by the current environment, so the new view is not deployed to the running containers; the database record is available to the current service.
