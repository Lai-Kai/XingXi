# Ground daily topics through the linked chat

Status: Complete

## Scope

Fix the evidence gate and preserve the verified daily-topic retrieval scope from
the workspace card through Xingxi tool execution.

## Comments

- 2026-09-06: Reproduced with the Zhu Maichen topic. The active Release contains
  the cited Chunk and a direct `朱买臣` search succeeds, but the card link drops
  all source scope and the agent's expanded AND query returns zero hits.
- 2026-09-06: Added exact-Chunk feed grounding, source-scoped chat handoff, and
  server-side attached-Evidence loading. A direct runtime replay now returns the
  bound `（康熙）吳縣志` Evidence at pages 1639-1645 even when the model submits
  the previously failing expanded query.
- 2026-09-06: Verified the live Gateway feed returns six cards with HTTP 200,
  the browser renders all six without a loading or demo-data state, and the
  new-chat stream context contains the verified query, document ID, and
  Evidence ID. Focused backend, frontend unit, and browser tests plus the
  production frontend build pass.
