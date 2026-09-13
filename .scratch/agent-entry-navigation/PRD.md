# Unify Xingxi chat entry

Status: ready-for-human

The primary action on `/workspace/agent` enters the shared
`/workspace/chats/new` composer through Next App Router navigation. Model
capability is selected by the configured model selector and is not encoded as a
product route mode. Browser back returns to the Xingxi agent page.

Acceptance:

- The primary action uses the canonical `/workspace/chats/new` URL without a
  model-strength query parameter.
- Legacy `pro`, `flash`, and `ultra` query parameters normalize away while
  preserving prompts and evidence scope.
- The selected configured model is submitted as `model_name` in run context.
- A normal entry clears stale research-project scope; a project entry retains
  its current project and documents.
- A chat render failure presents in-app retry and return actions.
