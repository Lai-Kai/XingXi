# Keep desktop sidebar resizing recoverable

Status: ready-for-human

The desktop workspace sidebar must resize with Pointer Events, collapse below a
defined threshold, and remain draggable from its right edge after collapse.
Every drag exit path must release capture and clear temporary visual and body
state. The existing trigger, navigation, scrolling, and mobile sheet behavior
must remain unchanged.

Acceptance:

- Repeated resize, collapse, and drag-to-expand cycles work.
- Pointer release outside the rail, pointer cancellation, capture loss, window
  blur, and Escape cannot leave resizing state behind.
- The rail remains above workspace content with a transparent hit target in
  icon mode.
- Mouse interaction leaves no resize line; keyboard-only focus may use
  `:focus-visible`.
