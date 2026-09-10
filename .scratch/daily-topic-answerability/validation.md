# Validation — 2026-09-09

The reported run was `3faca737-e3e0-4782-a351-29379bd883f6`. Before the fix,
Gateway discarded all three daily-topic retrieval fields, and the agent's
single `陆玩 灵岩寺 历史联系` query produced an empty EvidencePack.

## Regression checks

- New tests first failed on the missing Gateway fields and absent retry:
  3 failed, 4 passed.
- After the fix, 128 tests passed across `test_gateway_services.py`,
  `test_search_keyword_retry.py`, `test_fulltext_search.py`,
  `test_hybrid_search.py`, and `test_project_search_scope.py`.
- The SQL integration test in `test_fulltext_sql_repository.py` passed. Its
  daily-topic context now passes through the actual Gateway whitelist before
  loading Evidence, rather than being injected directly into the tool.
- Ruff check and format check passed for all eight modified Python files.
- Full-suite attempts before and after the fix stop during collection because
  the existing `deerflow.skills.skillscan.orchestrator` module is missing.

## Read-only corpus replay

From `backend/`, run:

```sh
PYTHONPATH=. .venv/bin/python ../.scratch/daily-topic-answerability/verify_retrieval.py
```

The script uses SQLite `mode=ro` and calls Gateway's context merger, the actual
search tool, and SQL repositories. It does not call a language model or change
knowledge/review records. Periodic event-loop polling compensates for missing
SQLite worker-thread wakeups in the restricted runner; the SQL integration test
used the same polling workaround without changing application code.

Both cases use the active Release
`release-2c7aafe43b4247fa86ab0d6b951590e7`:

| Entry | Effective query | Evidence items | Result |
| --- | --- | --- | --- |
| Daily topic | 陆玩 灵岩山 | 1 | Loaded attached Evidence from `（民國）宋平江城坊考`, Chunk pages 275–278 |
| Ordinary question | 陆玩 灵岩寺 历史联系 → 陆玩 灵岩寺 | 5 | Includes that exact bound Evidence, plus four other local sources |

Both results remain `inferred`: the corpus records retain source level `U` and
review status `pending`. The fix does not promote them to reviewed facts.

Container inspection was denied by the runner's Docker socket restrictions,
so loading of the changes by the running Gateway has not been verified.
