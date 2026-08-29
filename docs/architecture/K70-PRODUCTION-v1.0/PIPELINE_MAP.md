# K70 Pipeline Map — national_debt_ep01

## Render/assembly pipeline (file-by-file provenance)

| Stage | Script | Reads | Writes |
|---|---|---|---|
| 1 | `scripts/build_national_debt_documentary.py` | script.md, data_manifest.json, asset_manifest.json | `final.mp4`, `publish_master.mp4`, `audio/*.wav`, `voiceover_manifest.json`, `shot_manifest.json` |
| 2 | `scripts/render_national_debt_sketch_v1.py` | shot_manifest.json (c1,co2,d5,m2) | `sketch_v1/*_sketch_final.mp4` |
| 3 | `scripts/render_national_debt_vector_v3.py` | shot_manifest.json (c2,co3,d4,m3) | `vector_v3/*_vector_final.mp4` |
| 4 | `scripts/render_national_debt_collage_v1.py` | shot_manifest.json (c4,cj1,i1,m1) | `collage_v1/*_collage_final.mp4` |
| 5 | `scripts/build_14layer_preview.py` (+ `report_14layer.py`) | sketch/vector/collage outputs, `edit_national_debt_v2.py` body assembly | `national_debt_14layer_preview_v1.mp4`, `14layer_v1/*` |
| 6 | `scripts/edit_national_debt_v2.py` | V1 assembly, editor report | `national_debt_14layer_preview_v2.mp4`, `14layer_v2/*` |
| 7 | `scripts/build_14layer_v3_captions.py` **(DEPRECATED)** | V2 | `national_debt_14layer_preview_v3.mp4`, `14layer_v3/*` (18 selective caption cues) |
| 8 | `14layer_v3_pika/build_v3_pika.py` + `finalize_v3_pika.py` | V3, `pika_footage/*` | `national_debt_14layer_preview_v3_pika.mp4`, `14layer_v3_pika/*` |
| 9 | `14layer_v3_pika_fullcaptions/build_fullcaptions.py` | shot_manifest.json (all 31 shots) | `14layer_v3_pika_fullcaptions/_caps/*.mov` (131 cues, reusable asset — not itself a final video) |
| 9a | `14layer_v3_pika_fullcaptions/build_fullcaptions.py` (composite step) | V3-Pika + 131 cues | `national_debt_14layer_preview_v3_pika_fullcaptions.mp4` (captions scrim-composited over V3-Pika; old 18 cues remain baked underneath) |
| 9b | `14layer_v3_pika_fullcaptions/build_fullcaptions_clean.py` | **V2** (not V3) + reused Pika inserts (`14layer_v3_pika/_work/ins_*.mov`) + reused 131 cues | **`national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4`** — REFERENCE MASTER (old 18 cues never enter this pipeline) |

## Active vs. deprecated at each fork

- Stage 7 (`build_14layer_v3_captions.py`) is **DEPRECATED / FORBIDDEN** going forward —
  its 18-cue output is superseded by Stage 9/9a/9b's 131-cue full-transcript system.
- Stage 9a (`_fullcaptions.mp4`, non-clean) is kept as a historical intermediate; it still
  contains the old cues baked underneath the new ones (scrim-occluded, not source-removed).
  It is a protected master (never overwritten) but is **not** the reference master.
- Stage 9b (`_fullcaptions_clean.mp4`) is the **current reference master** — the only
  render where OLD_SELECTIVE_CAPTIONS is absent at the source.

## Compositing order (within COMPOSITING_TRANSITIONS, per render)

1. Base video track assembled shot-by-shot per `shot_manifest.json` timing, using whichever
   engine (L02-L08) is authoritative for that shot, joined with 0.5s cross-dissolves.
2. Chapter music beds (L11) mixed under narration, 2.0s crossfades between beds.
3. SFX (L12) mixed at event timestamps, narration held at unity gain.
4. Narration (L10) muxed as the primary audio layer.
5. (V3-Pika onward) Pika inserts (L09) segment-replace 4 video windows via alpha
   cross-dissolve; audio untouched (`-c:a copy`).
6. (Fullcaptions-clean onward) Full-caption cues (L13) overlaid 0:0 with per-cue
   `enable='between(t,start,end)'`; audio untouched (`-c:a copy`).
