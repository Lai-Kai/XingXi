# Issue tracker: Local Markdown

Xingxi implementation issues and PRDs live under `.scratch/`. Do not publish them to the configured upstream ByteDance GitHub repository.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- The PRD is `.scratch/<feature-slug>/PRD.md`.
- Implementation issues are `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Triage state is a `Status:` line near the top of each issue.
- Conversation history is appended under `## Comments`.

When a skill says to publish or fetch a ticket, use this local structure unless the project owner explicitly selects another tracker.
