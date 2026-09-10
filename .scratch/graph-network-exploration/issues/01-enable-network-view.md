# Connect the graph page to multi-hop queries

Status: ready-for-human

## Scope

Expose query scope metadata, pass Release IDs through the client, and use the
existing graph traversal for selectable one-to-three-hop exploration.

## Comments

- 2026-09-09: The page hard-codes `max_depth=1`, its hydration discards remote
  edges when catalog edges exist, and a second filter removes peripheral edges.
  These restrictions cause a local view despite existing backend support.
- 2026-09-09: Implemented default two-hop exploration and direct/two/three-hop
  controls using the existing query endpoint. The client keeps server nodes,
  peripheral relations and Evidence, pins refocusing/depth requests to the
  returned Release, and keys its cache by scope. Loading gates overlapping
  depth/refocus actions; failed depth changes restore the previous selection.
  Added route scope regression, client scope/cache regression, and browser
  regression covering remote records absent from the catalog, Evidence, depth
  switching, failure/retry, and refocusing. README, module guides, and API docs
  now describe the final behavior.
- 2026-09-09: Completed available verification; 20 focused backend tests pass,
  frontend lint/types/format pass, and real read-only SQL traversal confirms
  peripheral growth through three hops. Full backend collection still fails on
  the pre-existing missing skillscan module; the frontend test runner cannot
  bind its port in this sandbox. No live service reload/deployment verified.
  `ready-for-human` marks the reviewable handoff; implementation is complete.
