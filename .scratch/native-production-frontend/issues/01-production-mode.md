# Remove frontend compilation from native page requests

Status: ready-for-human

## Acceptance

- Establish the source of delay from native request logs.
- Prepare a host-launcher patch that builds before serving production pages and
  retains explicit development mode.
- A build failure must stop startup before any new service is launched.
- Add offline regressions and document activation and rollback.

## Comments

- Recent requests: projects 26.7s / 26.5s Next.js, glossary 24.6s / 24.4s Next.js,
  library 4.0s / 3.8s Next.js and 18ms on its repeated request. These are route
  response timings, not full browser load measurements or API latency benchmarks.
- Evidence and launcher backup: `/tmp/xingxi-workspace-loading-zm12kzj9/`.
- Prepared `docs/patches/native-launcher-production-frontend.patch`: production
  is the default, build precedes all service launches, and explicit development
  mode remains available. Added activation, verification and rollback notes in
  `docs/native-frontend-performance.md`; linked README and demo preparation.
- All 10 offline native-launcher regressions pass (six frontend-mode tests and
  four existing address-reuse tests). Ruff check/format, relative documentation
  links and `git diff --check` pass. The patch dry-runs against the actual host
  launcher with zero fuzz, and its SHA-256 remains unchanged.
- Host application/restart and authenticated browser measurements remain. The
  launcher is outside writable roots; no deployment or live data was changed.
