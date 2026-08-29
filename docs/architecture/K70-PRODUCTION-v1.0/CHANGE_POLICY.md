# K70 Change Policy — CURRENT WORKING ARCHITECTURE IS FROZEN

Version: K70-PRODUCTION-v1.0
Reference master: `national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4`

## Future agents / future work MAY, without further architecture approval

- Change the documentary topic, script, or content for a NEW episode.
- Replace assets *within* an existing layer (new footage, new chart data, new Pika
  clips) as long as the layer's engine, purpose, input/output contract, and position
  in the pipeline are unchanged.
- Generate new episode-specific charts (L02 PURE_CODE_VISUALS with new data).
- Generate new episode-specific Pika footage (L09, same integration method: normalize
  -> alpha-fade -> segment-replace over an already-composited base, same watermark
  handling, same no-readable-text QC rule).
- Update narration content for NEW episodes (L10, same VoiceManager pipeline).

## Future agents MUST NOT, without EXPLICIT USER AUTHORIZATION

- Add architecture layers.
- Delete architecture layers.
- Merge layers.
- Split layers.
- Reorder layer responsibilities (e.g. moving caption generation before Pika
  integration, or making captions depend on a captioned base instead of the clean one).
- Replace rendering systems (e.g. swapping the Blender vector renderer for a different
  engine, or replacing PIL-rendered captions with a different typography stack).
- Change visual semantics (AI/PIKA=FEEL, CHARTS/DATA=PROVE, SKETCH/VECTOR=UNDERSTAND,
  REAL FOOTAGE/DOCUMENTS=TRUST).
- Change compositing architecture (cross-dissolve grammar, overlay order, output codec
  spec).
- Reintroduce OLD_SELECTIVE_CAPTIONS (`build_14layer_v3_captions.py`) as an active
  caption layer, or build any new selective/partial caption pass as the default.
- Modify or overwrite any protected master (see `LOCKED_COMPONENTS.md`).
- Silently change the production pipeline (any of the above without saying so and
  getting explicit sign-off first).

## Scope of "architecture-level change"

A change is architecture-level if it alters *which systems exist*, *what depends on
what*, *in what order they run*, or *the protected output contract* — not if it changes
*what those systems produce for a given episode*. When in doubt, treat it as
architecture-level and ask first.

## Drift protection

Run `architecture_freeze/check_architecture_drift.py` before any release. It fails
loudly on missing locked files, modified critical scripts, a changed layer count, a
changed dependency definition, a changed `ARCHITECTURE_LOCK.json`, or the deprecated
caption pipeline reappearing in an active build path. It intentionally does NOT fail
on episode-specific content changes (new footage, new data, new narration, new charts).
