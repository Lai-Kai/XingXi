# Explore relationships beyond the current subject

Status: ready-for-human

The graph endpoint already supports one to three hops, but the page always
requests one hop and replaces returned edges with catalog-only direct edges.
The user wants the surrounding relationship network to be visible.

Acceptance:
- Default to two hops, with explicit direct/two-hop/three-hop controls.
- Preserve remote nodes, peripheral edges, and their Evidence locators.
- Pin depth changes and subject exploration to the returned knowledge Release.
- Distinguish server truncation from display pagination and retain review labels.
- Existing subject navigation, filters, dragging and Evidence inspection work.

`../PROJECT_PLAN.md` is absent; use the existing module/domain guides for this fix.

Implementation is complete in the worktree. See `VALIDATION.md` for passed
checks, real read-only data verification, and environment-limited checks.
Deployment and a live browser acceptance run are not verified.
