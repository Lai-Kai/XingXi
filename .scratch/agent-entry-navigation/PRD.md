# Keep Xingxi mode entry inside the application

Status: ready-for-human

The two primary actions on `/workspace/agent` must enter the existing
`/workspace` composer through Next App Router navigation. Professional research
selects `pro`; lightweight Q&A selects `flash`. The route, visible mode,
new-thread title, and run context must agree, and browser back must return to
mode selection.

Acceptance:

- Neither primary action exposes an anchor fallback or triggers a document
  reload.
- Professional research enters `/workspace?mode=pro`.
- Lightweight Q&A enters `/workspace?mode=flash`.
- `/workspace/chats/new` is opened only after the user submits a prompt.
- New-thread titles and submitted run context remain mode-specific.
- A chat render failure presents in-app retry and return actions.
