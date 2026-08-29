# K70 Locked Components — national_debt_ep01

All 14 discovered working layers are LOCKED as of this freeze (K70-PRODUCTION-v1.0).
See `WORKING_LAYERS.json` for full per-layer detail. Summary:

| ID | Layer | Locked script(s) |
|---|---|---|
| L01 | TIMELINE_ORCHESTRATION | scripts/build_national_debt_documentary.py, scripts/edit_national_debt_v2.py |
| L02 | PURE_CODE_VISUALS | apps/api/app/pipeline/pure_code_engine.py, pure_code_director.py |
| L03 | THREEJS_VISUALS | apps/api/app/pipeline/hft_threejs.py |
| L04 | REAL_FOOTAGE | apps/api/app/pipeline/broll.py |
| L05 | REAL_IMAGE | apps/api/app/pipeline/broll.py |
| L06 | SKETCH_RENDERER | scripts/render_national_debt_sketch_v1.py |
| L07 | VECTOR_RENDERER | scripts/render_national_debt_vector_v3.py, tools/k70_scene_engine/blender/vector_shot.py |
| L08 | PAPER_COLLAGE_RENDERER | scripts/render_national_debt_collage_v1.py |
| L09 | PIKA_AI_INSERTS | 14layer_v3_pika/build_v3_pika.py, 14layer_v3_pika/finalize_v3_pika.py |
| L10 | NARRATION_VOICE | app.voice.manager.VoiceManager |
| L11 | MUSIC_BED | scripts/build_national_debt_documentary.py (mix), scripts/edit_national_debt_v2.py (ducking) |
| L12 | SFX | scripts/build_national_debt_documentary.py, scripts/_retry_national_debt_v3_sfx.py |
| L13 | FULL_CAPTION_SYSTEM | 14layer_v3_pika_fullcaptions/build_fullcaptions.py, build_fullcaptions_clean.py |
| L14 | COMPOSITING_TRANSITIONS | scripts/build_national_debt_documentary.py, scripts/edit_national_debt_v2.py, finalize_v3_pika.py, build_fullcaptions_clean.py |

## Protected master files (NEVER modify or overwrite)

- `national_debt_14layer_preview_v1.mp4`
- `national_debt_14layer_preview_v2.mp4`
- `national_debt_14layer_preview_v3.mp4`
- `national_debt_14layer_preview_v3_pika.mp4`
- `national_debt_14layer_preview_v3_pika_fullcaptions.mp4`
- `national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4` **(REFERENCE MASTER)**

## Locked configuration values

- Output spec: 1920x1080, 30fps, h264 (crf16-18, preset medium, yuv420p), aac audio, +faststart
- Cross-dissolve grammar: 0.5s between ordinary shots
- Pika insert alpha cross-dissolves: 0.25-0.50s (per-insert, see integration_manifest.json)
- Caption typography: Georgia (serif), 46px, 1200px safe column, 84px edge margin, sentence
  case, gaussian-blur halo, gradient scrim, band=upper only for shots h1/d3
- Semantic rule mapping: AI/PIKA=FEEL, CHARTS/DATA=PROVE, SKETCH/VECTOR=UNDERSTAND,
  REAL FOOTAGE/DOCUMENTS=TRUST (PAPER_COLLAGE and THREEJS follow the UNDERSTAND family)
