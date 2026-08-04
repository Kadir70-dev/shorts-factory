# Render optimization — resume note

Stopped at the 30-minute budget with 3 of 6 checkpoints landed and validated.
Nothing is half-applied: every commit below is self-contained and the tree is
clean.

## Landed

| Commit | What | Evidence |
|---|---|---|
| `8f7c4fa` | Scene clip encode: `_HOLD` + `_INTERMEDIATE` presets | 208.31s → 81.05s, clips byte-identical (prior session) |
| `76dd93b` | Packaging stream-copy + QA reuse; finalizer moved into engine | wrapper import chain verified, resolves Fashion data_dir |
| `5599bd0` | Kokoro `--manifest` batch + content-addressed narration cache | 11.0s → 0.044s, WAV byte-identical (sha256) |
| `8ff14f8` | dataviz/motiongfx content cache + frames off the event loop | 14.57s → 0.0003s, byte-identical, seed-sensitive; 55ms worst loop stall |

Item 6 (ffmpeg) needed no new work: `_DELIVERY` is already veryfast/CRF20 and
packaging no longer re-encodes, so the delivered file has exactly one video
encode.

## Not started

**4. Incremental scene rendering.** The hard part already exists and is unused:
`pipeline/production_optimizer.py` has `scene_fingerprint`, `changed_scenes`,
`preview_manifest` and `render_changed_scenes` (lines 240-262). What is missing
is the wiring — `render_ffmpeg.render()` does not consult a manifest, and no
stage persists one to the job folder. Plan: write `manifest.json` beside
`scene_graph.json` at render time, and have `_scene_clip` skip regeneration when
the fingerprint matches AND the existing clip's checksum matches what the
manifest recorded (the checksum is what rejects stale artifacts; the fingerprint
alone cannot detect a truncated or half-written clip).

**5. Official asset engine.** `pipeline/providers.py` is 1112 lines and was left
alone deliberately — it is the one item here that cannot be validated without
live network calls, and it carries the licensing/provenance records. Sub-items:
drop providers with no live adapter, reject PDFs pre-download by content-type,
dedupe downloads by content hash, persist query results with a TTL, parallelize
the single retry pass.

## Benchmark — NOT run

No timing in this note comes from a full Short. The per-stage numbers above are
real and measured, but the requested matrix (cold / warm / one-scene-edit wall
time, CPU time, peak RSS, cache hit rates, QA and packaging time) requires three
full renders and was not run.

Input is ready: `data/demos/kasai_zara_speed.json`, prior job at
`data/jobs/vid_kasai_zara_speed`.

```
cd /home/kadir/Fashion-Shorts
.venv/bin/python scripts/produce_fashion.py --preset fashion_business \
    --from-json data/demos/kasai_zara_speed.json --keep
.venv/bin/python scripts/finalize_short.py --job vid_kasai_zara_speed
```

Run it cold (clear `data/cache/narration` and `data/cache/{dataviz,motiongfx}`),
then warm unchanged, then with one scene's narration edited.

## Watch for on resume

- The narration cache lives under `data/cache/narration` in the WRAPPER repo, so
  Fashion-Shorts and any other wrapper keep separate caches. That is intended.
- `batch_kokoro` writes `kokoro_manifest.json` into the job's `vo/` dir and
  unlinks it in a `finally`. A killed process can leave it behind; harmless.
- The `_CPU_RENDER` semaphore is module-global in `brand/raster.py` and now also
  gates `finance_motion`, which shares `write_video`. Intended, but it means a
  chart and a finance beat no longer overlap freely.
