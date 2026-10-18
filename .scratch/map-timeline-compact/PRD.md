# Compact the historical map timeline

Status: ready-for-human

The expanded timeline on `/workspace/map` takes too much vertical space away
from the map. Keep the timeline visible by default with compact event summaries
and independent scrolling.

Acceptance:

- Cap the complete timeline at 200 CSS pixels on desktop, 176 on mobile, and
  28 percent of the viewport height on short windows.
- Keep playback and collapse controls visible while events scroll.
- Preserve year positioning, same-year groups, event details, and undated events.
- Update the existing layout and browser regressions and the map documentation.
