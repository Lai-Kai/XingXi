# Integrate map functionality and resolve local overlaps

Status: ready-for-human

Import only the map dependency closure from `feat/ui-redesign`, merge the local
compact timeline, join the migration branches, and validate API/UI compatibility.

## Comments

- Baseline: 33 map frontend unit tests and 12 map backend tests passed earlier in
  this session. TypeScript passed; ESLint reported four existing graph warnings.
- Full backend baseline stops with 12 collection errors for the absent
  `deerflow.skills.skillscan.orchestrator` module.
- The seven existing GLBs are real files; branch LFS pointers must not replace
  them. Remote branch data is now available locally after the owner's fetch.
- Implementation is integrated into the working tree. Five map timeline conflicts
  are resolved; both migration histories join at `0047_merge_map_reconstruction`.
- Registered map table metadata in the harness to prevent future autogeneration
  from deleting the new tables; the regression failed before this fix.
- Validation: 88 backend tests and 53 frontend unit tests pass. Ruff and formatting
  pass; full ESLint has only the four preexisting graph warnings. All seven static
  GLBs retain matching SHA-256 content hashes. Browser collection finds 33 cases.
- Remaining external prerequisite: install the declared frontend dependencies in
  the owner's normal terminal. Offline cache lacks Spark and Three.js type packages;
  the build reports the missing Spark module. Await installation before the final
  TypeScript/build check. Browser execution needs an environment allowing ports.
- Full backend collection retains the same 12 preexisting skillscan errors. The
  broader legacy bootstrap OCR-column ordering failure also reproduces in an
  isolated pre-integration copy; map migration upgrade/preservation checks pass.
- See `docs/map-ui-redesign-integration.md` for installation and verification scope.
- The owner's install reached an EACCES creating `/data/.pnpm-store/v10`.
  Set `frontend/.npmrc` to use `../.pnpm-store`, matching the existing writable
  store recorded in `node_modules/.modules.yaml`; no elevated permissions needed.
- Verified `pnpm store path` resolves to
  `/data/laikai/deer-flow/.pnpm-store/v10`. Retried frozen installation: the store
  permission error is resolved, but registry downloads fail with DNS EAI_AGAIN
  in this coding environment (first missing tarball reported: `fflate@0.8.3`).
  The owner can rerun the original install command in the normal terminal.
- The owner completed frozen installation with pnpm 10.26.2; Spark 2.3.1,
  Three.js 0.183.2 and its types 0.183.1 are installed. Full `pnpm check` passes
  (zero errors, the same four existing graph warnings). All 53 map/config unit
  tests also pass with the installed packages. Production build is in progress.
- Final validation complete: `pnpm build --webpack` exits successfully, including
  TypeScript, all 81 generated pages, `/workspace/map` and both streaming upload
  route handlers. Dependency and build blockers are resolved. Implementation is
  ready for review; the 33 collected browser scenarios remain unexecuted because
  this environment cannot bind local service ports. No commit or deployment.
