# P3.4 Final Three.js Report: K70 Bitcoin Ep. 1

- **Result: 20/20 Three.js scenes upgraded from 360×640 to 1080×1920 and validated.** No scene failed.
- **New graph:** `data/finance_p34/bitcoin_final_v1/scene_graph_p34.json`, built from the **P3.3 graph**. Only the 20 Three.js `asset_path` / `decision_reason` fields changed; `scripts/k70_p34_threejs_final.py build` enforces this.
- **Untouched:** the preview clips in `data/finance_p0/threejs_restore/clips/` and every earlier graph.

## Staged rendering

- Renders used `scripts/k70_p0_threejs_restore.py --quality final --only <ids>`, in 4 batches of 4–5 scenes, each in its own folder under `data/finance_p34/threejs_final/batch_N/`.
- s72 reuses the P3.3 benchmark clip. Before reuse, its file (sha256 `b784fedc…`), probe (1080×1920, 103 frames, 3.433 s) and render report (status `rendered`) were checked.
- A gate ran before each batch: at least 3 GB free disk and at least 2.5 GB available RAM. The driver stops on a render failure or a failed validation. Neither happened.

- batch_1: wall 457.37 s, Python max RSS 368 MB
- batch_2: wall 384.49 s, Python max RSS 367 MB
- batch_3: wall 340.62 s, Python max RSS 368 MB
- batch_4: wall 218.08 s, Python max RSS 377 MB

Total render time was about 23 minutes for 92.5 s of 3D (plus the 47.6 s s72 benchmark). The browser worker peaked at about 1.6 GB per scene.

## Validation (`scripts/k70_p34_threejs_final.py validate`)

| Check | Rule |
|---|---|
| Resolution | exactly 1080×1920 |
| Duration | within one frame (1/30 s) of the scene duration |
| Frames | every frame decodes, and the decoded count equals the probed count |
| Black frames | none: every frame's mean luma (YAVG) is at least 16 |
| Flat or broken frames | none: every frame's luma range is at least 2 |
| Labels, coastlines, borders | SSIM of the downscaled final against the validated preview (same seed and template) is at least **0.95**; the same scene scores about 0.99 and a different globe scene about 0.82 |
| Render report | status `rendered` or `cache_hit`, no error |

The SSIM threshold was first set at 0.80. A negative test (s72 final against the s73 and s116 previews scored 0.824) showed that was too lax, so it was raised to 0.95 and **every batch was re-validated**.
A contact sheet of the 20 mid-frames was also inspected by eye: every place label, highlighted region, coastline and border is present.

| Scene | Label | Resolution | Frames | Duration (clip / scene) | Min YAVG | SSIM vs preview | Render | Worker peak | Result |
|---|---|---|---|---|---|---|---|---|---|
| s7 | Maryland | 1080×1920 | 120 | 4.000 / 4.004 | 37.2 | 0.9927 | 61.6 s | 1418 MB | PASS |
| s14 | New Hampshire | 1080×1920 | 269 | 8.967 / 8.953 | 38.4 | 0.988 | 119.6 s | 1438 MB | PASS |
| s17 | Germany | 1080×1920 | 140 | 4.667 / 4.665 | 40.2 | 0.9919 | 68.1 s | 1148 MB | PASS |
| s22 | India | 1080×1920 | 153 | 5.100 / 5.092 | 41.2 | 0.9933 | 71.2 s | 1405 MB | PASS |
| s31 | Japan | 1080×1920 | 132 | 4.400 / 4.388 | 40.4 | 0.9924 | 79.1 s | 1496 MB | PASS |
| s37 | France | 1080×1920 | 146 | 4.867 / 4.879 | 39.7 | 0.9912 | 77.3 s | 1507 MB | PASS |
| s47 | United States Of America | 1080×1920 | 198 | 6.600 / 6.585 | 40.4 | 0.9868 | 84.3 s | 1290 MB | PASS |
| s62 | Ohio | 1080×1920 | 171 | 5.700 / 5.689 | 36.5 | 0.9936 | 96.4 s | 1740 MB | PASS |
| s72 | Thailand | 1080×1920 | 103 | 3.433 / 3.428 | 40.9 | 0.992 | 47.6 s | 1640 MB | PASS |
| s73 | Indonesia | 1080×1920 | 124 | 4.133 / 4.132 | 41.8 | 0.9913 | 54.8 s | 1261 MB | PASS |
| s74 | Russia | 1080×1920 | 107 | 3.567 / 3.577 | 44.6 | 0.9917 | 39.5 s | 1318 MB | PASS |
| s76 | New York | 1080×1920 | 146 | 4.867 / 4.879 | 37.4 | 0.9921 | 63.7 s | 1198 MB | PASS |
| s86 | Netherlands | 1080×1920 | 152 | 5.067 / 5.071 | 40.7 | 0.9909 | 63.7 s | 1342 MB | PASS |
| s87 | Switzerland | 1080×1920 | 98 | 3.267 / 3.279 | 40.5 | 0.9902 | 39.4 s | 1721 MB | PASS |
| s90 | California | 1080×1920 | 199 | 6.633 / 6.628 | 37.4 | 0.9921 | 83.3 s | 1530 MB | PASS |
| s104 | Florida | 1080×1920 | 152 | 5.067 / 5.071 | 36.8 | 0.9922 | 62.2 s | 1273 MB | PASS |
| s116 | Argentina | 1080×1920 | 115 | 3.833 / 3.833 | 38.2 | 0.9922 | 53.7 s | 1257 MB | PASS |
| s124 | Zimbabwe | 1080×1920 | 96 | 3.200 / 3.193 | 41.0 | 0.9903 | 38.6 s | 1144 MB | PASS |
| s128 | Hungary | 1080×1920 | 128 | 4.267 / 4.281 | 40.4 | 0.9917 | 50.2 s | 1161 MB | PASS |
| s131 | United Kingdom | 1080×1920 | 128 | 4.267 / 4.281 | 40.8 | 0.9895 | 57.3 s | 1362 MB | PASS |

## P3.4 graph validation

- 156 scenes; total 656.942 s; every duration identical.
- Captions, audio (voiceover and music), SFX and meta are identical to P3.1.
- Every transition is identical to P3.3.
- The 8 rights-cleared cinematic inserts and every historical repair are identical to P3.3. The s35/s67 sourced charts are identical to P3.1.
- Every media path exists, and all 20 Three.js clips probe at 1080×1920.
- Two scenes (s14, s131) were rendered through the real `render_ffmpeg._scene_clip` from the P3.4 graph: 1080×1920 at the correct durations, label and coastline crisp.

## Editorial note (unchanged, for review)

The places come from the authored graph. Most match the narration (Maryland/Camp David, New Hampshire/Bretton Woods, Bangkok, Moscow, Buenos Aires, Zimbabwe, Newcastle, Florida/e-gold). Two are worth an editor's glance, though neither was changed: s22 shows **India** under "ONE PROMISE", and s31 shows **Japan** under "DOLLARS OUT".

## Disk

Free space is **5.7 GB**. See `../P34_DISK_CLEANUP_REPORT.md`; **reaching at least 12 GB needs the user to approve cleanup**. Nothing was deleted.

## Remaining blockers before the full render

1. Approve the disk cleanup (Option 4 in the cleanup report) to reach at least 12 GB free.
2. Optional editorial review of s22 and s31, and of the weak stock scenes listed in the P3.3 audit.
3. Run the full master render of `scene_graph_p34.json` (awaiting approval), then do human frame-by-frame QA.
4. At upload: paste `FINAL_VIDEO_CREDITS.md` (P3.3) and decide on the synthetic-voice disclosure.
