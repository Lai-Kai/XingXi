# Manage automatic evaluation questions

Status: ready-for-human

Expose the automatic evaluation questions and their methods from the Agent
evaluation dashboard. Governance readers can inspect full questions and rules;
administrators can add questions using an existing replay method and remove or
restore questions without editing source code.

Persist custom questions and built-in activation overrides in SQL. New runs
freeze the enabled catalog; historical batches and reruns retain their original
case snapshots. Counts must follow the enabled catalog. Keep scripted replay,
synthetic corpus isolation, admin-only writes, and the existing execution lease.
This change does not introduce live-model evaluation or executable user rules.

Validate CRUD/permissions, SQL persistence, frozen executions, migration, API
transport, and the visible management flow. The referenced parent project plan
is absent in this checkout; existing repository/domain guides remain applicable.

Implementation is complete. The native 12026 Gateway still needs a restart to
load the routes and apply migration 0046. The launcher state directory is
outside this session's writable roots, and service sockets/browser startup are
restricted here. Browser and async SQL/HTTP integration acceptance remains
pending in the running environment; see the issue validation record.
