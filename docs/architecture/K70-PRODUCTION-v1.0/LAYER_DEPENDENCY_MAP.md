# K70 Layer Dependency Map — national_debt_ep01

Reference master: `national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4`

## Dependency graph (upstream -> downstream)

```
L10 NARRATION_VOICE (script.md -> audio/*.wav)
   |
   v
L01 TIMELINE_ORCHESTRATION (shot_manifest.json: start/end per shot)
   |
   +--> L02 PURE_CODE_VISUALS      (25 shots)
   +--> L03 THREEJS_VISUALS        (1 shot: d1)
   +--> L04 REAL_FOOTAGE           (4 shots: h3, w1, w4, e2)
   +--> L05 REAL_IMAGE             (0 active shots; engine proven, unused this episode)
   +--> L06 SKETCH_RENDERER        (4 shots: c1, co2, d5, m2)
   +--> L07 VECTOR_RENDERER        (4 shots: c2, co3, d4, m3)
   +--> L08 PAPER_COLLAGE_RENDERER (4 shots: c4, cj1, i1, m1)
   +--> L11 MUSIC_BED              (8 chapter beds, chapter-aligned)
   +--> L12 SFX                    (event cues tied to L02/L03/L06/L07/L08 visual moments)
   |
   v
L14 COMPOSITING_TRANSITIONS  (stitches L02-L08 into one video track,
   |                          0.5s cross-dissolve grammar, muxes L10-L12 audio)
   |                          -> national_debt_14layer_preview_v3.mp4 (V3; OLD_SELECTIVE_CAPTIONS
   |                             baked in here by the now-deprecated build_14layer_v3_captions.py)
   v
L09 PIKA_AI_INSERTS  (segment-replaces 4 windows of V3's video track;
   |                  audio copied verbatim; depends on L14's V3 output as base)
   |                  -> national_debt_14layer_preview_v3_pika.mp4
   v
L13 FULL_CAPTION_SYSTEM  (depends on L01 timing + L10 narration text;
                          REUSES L09's Pika insert clips and L14's V2 base
                          directly -- does NOT depend on OLD_SELECTIVE_CAPTIONS
                          or on V3/V3-Pika's baked pixels)
   -> national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4  [REFERENCE MASTER]
```

## Key dependency facts (verified, not assumed)

- **L13 does not depend on OLD_SELECTIVE_CAPTIONS.** The clean reference master is built
  from `national_debt_14layer_preview_v2.mp4` (pre-caption master) plus the reused Pika
  insert clips (`14layer_v3_pika/_work/ins_*.mov`) plus the reused 131 full-caption clips
  (`14layer_v3_pika_fullcaptions/_caps/*.mov`) in a single ffmpeg pass. OLD_SELECTIVE_CAPTIONS'
  script (`build_14layer_v3_captions.py`) is never invoked in this path.
- **L09 (Pika) and L13 (captions) are independent of each other.** Confirmed: none of the
  4 Pika insert windows overlap any of the 18 old caption cue windows, and the 131 new
  caption cues do not touch Pika's visual content — they only overlay text in the safe
  margins. Freezing one does not constrain re-approval of the other.
- **Audio (L10+L11+L12) is decoupled from every visual layer.** Verified MD5-identical
  audio stream across V2, V3, V3-Pika, and both fullcaptions renders
  (`ea7fceeeffd0813f9f0c70db61c8b6bb`). No visual-layer change has ever touched audio.
- **L05 REAL_IMAGE is a proven-but-currently-unused engine**, not a dead one: it produced
  m1's original render, later superseded editorially by L08 PAPER_COLLAGE. It stays
  locked/available for future episodes, not deleted.
