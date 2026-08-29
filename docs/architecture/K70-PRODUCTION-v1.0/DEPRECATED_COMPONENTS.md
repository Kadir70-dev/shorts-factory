# K70 Deprecated / Forbidden Components — national_debt_ep01

## OLD_SELECTIVE_CAPTIONS — STATUS: DEPRECATED / FORBIDDEN

- **Script:** `scripts/build_14layer_v3_captions.py`
- **What it did:** composited 18 hand-picked phrase-based caption cues onto V2 to produce
  `national_debt_14layer_preview_v3.mp4` (`14layer_v3/caption_manifest.json`).
- **Why deprecated:** superseded by `FULL_CAPTION_SYSTEM` (L13) — 131 cues covering
  99.12% of narration across all 31 shots vs. 18 selective phrase cues (~1 every 21s
  with long uncaptioned stretches).
- **Forbidden action:** this script, or any equivalent selective/partial caption pass,
  must never be re-run against a protected master or against any future episode's
  default pipeline without EXPLICIT user authorization. It must never "automatically
  return" as the active caption layer.
- **Physical residue:** the 18 old cues remain baked into the pixels of
  `national_debt_14layer_preview_v3.mp4`, `..._v3_pika.mp4`, and
  `..._v3_pika_fullcaptions.mp4` (non-clean). Those files are protected masters and are
  left as-is (not retroactively edited). The reference master
  (`..._v3_pika_fullcaptions_clean.mp4`) was rebuilt from the pre-caption V2 master
  specifically so the old cues never enter its pipeline at all.

## Excluded from this freeze (not deprecated — simply out of scope)

- `14layer_v4_audit/*` — audit/planning only; V4 was never implemented
  (`14layer_v4_audit/IMPLEMENTATION_BLOCKED.md`: "BLOCKED before any file was created or
  rendered... there is no V4").
- `14layer_v4_pika_audit/*` — planning artifacts for the same never-implemented V4.
- `14layer_v4_voice_package/*` — unfinished voice-cloning work; narrator identity
  `k70_host_v1` not reproducible on this machine. Explicitly excluded from freeze scope
  per user instruction ("DO NOT... start voice work").

None of the above are counted in the 14 working layers, and none require a lock entry —
they are dormant/blocked, not active production layers.
