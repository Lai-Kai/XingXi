# Update the company demo script for the integrated map

Status: ready-for-human

## Request

Update `docs/xingxi-company-demo-script.md` so the 古舆地图 section matches the
integrated map and restored reference chronology.

## Result

- Revised section 7 to cover point details, reference event chronology, on-demand
  3D preview, administrator point/model creation, and study-route export.
- Kept reference chronology distinct from released knowledge and existing model
  previews distinct from optional remote reconstruction.
- Updated preparation, duration, fallback wording, Q&A and source links.
- Checked UI labels and actions against the current components and README.
  This documentation-only update does not require software test runs.
- Verified all 22 Markdown link targets and passed `git diff --check`.

## Comments

- Implementation is complete. On-host rehearsal and loading the reference-event
  endpoint remain deployment/demo preparation steps described in the script.
- Original script backed up at
  `/tmp/xingxi-demo-script-map-ehiq177n/before.md`.
