# Daily topic answerability

Status: Complete

## Problem

The daily-topic feed can publish a source-bound card while the linked Xingxi
conversation searches with an unrelated expanded query and returns no evidence.
The card-to-chat handoff currently drops the topic's retrieval query, document
IDs, and Evidence IDs.

## Acceptance criteria

- A seed is publishable only when its canonical retrieval query returns evidence
  from its bound Chunk(s) in the active Release.
- Daily-topic links carry the verified query and source scope into the new chat.
- `search_sources` uses that verified query and intersects requested documents
  with the daily-topic scope while the conversation is active.
- Source links remain inspectable and tests cover the feed gate and handoff.
