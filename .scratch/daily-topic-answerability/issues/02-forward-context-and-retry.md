# Preserve daily-topic evidence through Gateway and retry empty keyword searches

Status: ready-for-human

## Scope

- Forward the daily-topic query, document IDs, and Evidence IDs through Gateway's
  runtime context whitelist, keeping the active Release server-authoritative.
- After an empty agent keyword search, retry once without standalone question
  wording such as `历史联系`, preserving the Release, source filters, and quoted
  phrases. Do not change the exact full-text API contract.
- Cover Gateway-to-tool evidence delivery and bounded retry behavior with tests.

## Comments

- 2026-09-09: Run `3faca737-e3e0-4782-a351-29379bd883f6` searched
  `陆玩 灵岩寺 历史联系` once and received an empty EvidencePack. Its active
  Release already contains the cited passage in `（民國）宋平江城坊考`.
  Gateway's context whitelist drops all `daily_topic_*` retrieval fields.
- 2026-09-09: User authorized the fix. `../PROJECT_PLAN.md` is absent in this
  checkout; use the existing domain guides and daily-topic PRD for this repair.
- 2026-09-09: Implementation complete and available for review. The three
  daily-topic retrieval keys now reach ToolRuntime. Empty ordinary searches
  retry once with subject keywords, preserving the frozen Release and filters.
  The direct full-text fallback now retains structured filters as well.
- 2026-09-09: 128 focused unit tests and one SQL integration test pass; Ruff
  lint and formatting checks pass. Read-only replay against the current corpus
  returns the bound Evidence for the daily topic and five Evidence items for
  the ordinary question. See `../validation.md` for limits and reproduction.
