# K70 PRODUCTION ARCHITECTURE FREEZE

**Status: FROZEN**
**Architecture family:** K70
**Version:** K70-PRODUCTION-v1.0
**Job:** `k70_national_debt_ep01`
**Reference master:** `national_debt_14layer_preview_v3_pika_fullcaptions_clean.mp4`
**Frozen on:** 2026-08-29

## What this freeze covers

The real, currently-working production architecture behind the approved reference
master was discovered programmatically (scripts, manifests, output directories,
docstrings, integration manifests) — not assumed from the "14-layer" job name.

**Discovered working layer count: 14.** This was not forced to match the job's name;
it fell out of directly inspecting the pipeline: 8 visual-rendering layers (code,
3D, real footage, real image, sketch, vector, paper collage, AI/Pika), 3 audio layers
(narration, music, SFX), 1 typography layer (full captions), and 2 structural layers
(timeline orchestration, compositing/transitions). See `WORKING_LAYERS.json` for the
full per-layer record (purpose, input, output, script, dependencies, status).

### Provenance of the "14-layer" name

The job's own naming convention is not a coincidence: `scripts/build_14layer_preview.py`
documents a pre-existing "14-LAYER DOCUMENTARY ENGINE" director-role framework
(L1 Research Director, L4 Voice Director, L5 Visual Director, L8 Cinematography,
L9 VFX/Compositing, L10 Typography, L11 Sound, L12 Edit/Retention, L14 Master QA — the
only roles independently named as scripts/artifacts in the repo; L2/L3/L6/L7/L13 exist
only as gaps in that numbering with no dedicated script or artifact found). That
role-based framework and this freeze's technical/implementation-based 14-layer
breakdown are two valid partitions of the same system at different altitudes — this
freeze documents the latter because it is the one that is independently scriptable,
verifiable, and lockable.

## Semantic rules (preserved, not redesigned)

- **AI / PIKA = FEEL**
- **CHARTS / DATA = PROVE**
- **SKETCH / VECTOR = UNDERSTAND**
- **REAL FOOTAGE / DOCUMENTS = TRUST**

## Caption system status

- **FULL_CAPTION_SYSTEM (131 cues, 31/31 shots, 99.12% narration coverage) is
  AUTHORITATIVE.**
- **OLD_SELECTIVE_CAPTIONS (18 cues) is DEPRECATED / FORBIDDEN** and must never
  automatically return as the active caption layer. See `DEPRECATED_COMPONENTS.md`.

## Pika integration status

The approved 4-insert Pika integration (P101, P102, P103, P104; 25.93s / ~4.88% of
runtime) is FROZEN as-is. No regeneration, no re-audit, no timing/transition changes,
no increase in AI footage share, no replacement of factual visuals with AI. See
`WORKING_LAYERS.json` L09 and `LOCKED_COMPONENTS.md`.

## Protected masters

V1, V2, V3, V3-Pika, V3-Pika-Fullcaptions, and V3-Pika-Fullcaptions-Clean are all
protected — never modified or overwritten by this freeze or by future work without
explicit user authorization. See `LOCKED_COMPONENTS.md` for the exact filenames.

## Files in this package

- `ARCHITECTURE_FREEZE.md` — this file
- `WORKING_LAYERS.json` — machine-readable per-layer record (14 layers)
- `LAYER_DEPENDENCY_MAP.md` — dependency graph between layers
- `PIPELINE_MAP.md` — file-by-file script provenance, stage by stage
- `LOCKED_COMPONENTS.md` — locked scripts, protected masters, locked config values
- `DEPRECATED_COMPONENTS.md` — old selective captions + out-of-scope V4 artifacts
- `CHANGE_POLICY.md` — what future agents may/must-not do without authorization
- `BASELINE_HASHES.json` — SHA256 of every critical script/manifest/master
- `ARCHITECTURE_LOCK.json` — machine-readable freeze state
- `check_architecture_drift.py` — lightweight validator (protects the engine, not
  episode content)

## No video was rendered to produce this freeze

This freeze is discovery, documentation, hashing, and locking only. No render,
re-audit, or code change was made to any working script or master.
