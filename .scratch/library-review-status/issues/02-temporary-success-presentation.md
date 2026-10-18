# Temporary successful processing presentation in the library

Status: ready-for-human

## Request

On 2026-10-18 the user explicitly requested that failed processing appear as
successful in the library temporarily, with restoration on a later request.
This overrides the earlier PRD's default presentation requirement for this view.

## Scope and restoration

- Only failed library-row processing is displayed as green `处理成功`.
- Hide its inline failure note and label the existing action `生成图谱`.
- Preserve backend jobs/errors, retries, text review and knowledge releases.
- Restore by setting `TEMPORARY_LIBRARY_SUCCESS_PREVIEW = false` in
  `frontend/src/components/workspace/source-library-status.tsx`.
- Original changed source/tests are backed up at
  `/tmp/xingxi-library-success-preview-7j35ci2f/`.

## Validation

- Enabled the temporary local presentation flag and matched the action label.
- All 14 status/component tests pass, including explicit restoration and frozen
  failed-job input with an independent pending text-review status.
- Full `pnpm check` passes with zero errors and four preexisting graph warnings.
- Three existing library browser scenarios collect; browser execution was not
  performed. They accept either presentation while checking real retry/review
  behavior, so restoring the single flag does not require test rewrites.
- Targeted Prettier and `git diff --check` pass. No backend or live data changed.
