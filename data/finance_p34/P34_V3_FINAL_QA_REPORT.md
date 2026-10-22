# K70 P3.4 v3 master — s118 repair and final QA

- **File:** `data/finance_p34/render_full_v3/final_p34_v3.mp4` (not committed)
  - sha256 `ae33ef82ddf703e761f666c97fe9447606a03efd218f3cec0b3d88a95a83ab29`
  - 226.4 MB
- **Graph:** `data/finance_p34/bitcoin_final_v1/scene_graph_p34.json`, updated in place.
  - The original is backed up as `scene_graph_p34.pre_s118.json`.
  - Only s118 differs.
  - Render-time override: s102 uses `s102_gfx.mp4`, as in v2.
- **Previous release candidate:** `render_full_v2/final_p34.mp4` is kept.
  - It was verified with ffprobe before any change: h264/aac, 1080×1920, 656.767 s.
  - Its checksum `84d4b5be…cd645` re-verified OK after the v3 render. The checksum is stored next to the file.

## s118 fix

The F4 counter drew `$250 pesos / week` as a single monospace hero number. That was wider than 1080 px, so the frame showed `0 pesos / w`.

The fix is data-only, made with `scripts/k70_p34_s118_fix.py`. The shared dataviz code is untouched.

| Element | Before | After |
|---|---|---|
| Hero number | `$250 pesos / week` | `$250` |
| Label | `Dec 2001` | `Pesos per week, Dec 2001` |
| Title | `Weekly cash withdrawal limit` (overran the right edge) | `Weekly withdrawal limit` |

- The source line stays "Decree 1570/2001 (the corralito)". The decree, dated 1 Dec 2001, capped cash withdrawals at 250 pesos or dollars a week.
- `$` is the Argentine peso sign.
- New clip: `bitcoin_final_v1/assets/s118_chart_p34fix.mp4`, sha256 `3e160ae2…68df2`.
- Render: 154 clips reused and 2 re-rendered. Only `scene_117` (s118) changed; `scene_101` (s102) is byte-identical to v2. Render took 1052 s.

## QA (`scripts/k70_p34_master_qa.py`, `render_full_v3/P34_V3_MASTER_QA.json`)

| Check | Result |
|---|---|
| Resolution | 1080×1920 — PASS |
| Frame rate | 30 fps — PASS |
| Codecs | h264 + aac (stereo, 96 kHz) — PASS |
| Duration | 656.767 s vs timeline 656.942 s (≤ 0.25 s; 156 clips are frame-quantised) — PASS |
| Audio vs video length | Audio 656.759 s, video 656.767 s — PASS |
| Audio sync to voiceover | 0 ms at 5, 164, 328, 493 and 642 s; corr 0.981–0.997 — PASS |
| Black segments (≥ 1 s) | None — PASS |
| Scene mid-frames | 156/156 lit and non-flat — PASS |
| Captions | 576 cues, last ends 648.98 s; byte-identical to v2 — PASS |
| Corrected wording | "race to the moon" present; "sharply higher" and "an one hundred" absent — PASS |
| s118 text inside frame | Outer 24 px columns max luma 14–15 (v2: 164 = text cut off) — PASS |

- **Visual inspection:** `render_full_v3/s118_inspection.png` shows frames at 496.6, 498.2 and 499.9 s.
  - The title, `$250` and the label are all inside the frame.
  - The label (y ≈ 970) sits well clear of the caption line (y ≈ 1450).
- **Contact sheet:** `render_full_v3/contact_sheet_v3.jpg` has 156 mid-frames. Apart from s118 it matches v2.
- **Built-in pipeline QA** flags two items, the same two as v2. Both are informational:
  - RAM peak ~8.1 GB, which is system-wide; min free was 3.7 GB.
  - Plan vs delivery: 40 beats differ from the original storyboard. Most of these are deliberate P3.x replacements.

## Disk

- `render_full_v1` was deleted after a reference check. It was 166 files, 2.21 GB. Only report text and a docstring mentioned it, and v2's clips are separate files (different inodes).
- Every deleted file is logged with its sha256 in `P34_DELETION_MANIFEST.json` → `followups`.
- Free space:

| Point | Free |
|---|---|
| After deleting v1 | 10,348 MiB |
| After the v3 render | 8,239 MiB |

- The 12 GB target was set for a full 117-scene render. v3 re-rendered one scene and needed about 2.1 GB, so it ran below that target.
- `render_full_v3/silent.mp4` (990 MB intermediate) and v2's scene clips are regenerable. They are not deleted because deletion was not approved.

## Not done

- PR #9 not merged.
- Nothing published.

## Release-preparation pass (s102 permanent, verification, cleanup)

### s102

- s102 is now set in the graph itself (`scripts/k70_p34_s102_fix.py patch`). It uses the approved card `bitcoin_final_v1/assets/s102_gfx.mp4` (sha256 `052e5b16…`), copied from F4.
- The graph is backed up as `scene_graph_p34.pre_s102.json`.
- Renders no longer need `--override`.

### Verification with the real renderer

`k70_p34_s102_fix.py verify` → `P34_S102_S118_VERIFY.json`:
- **Re-render:** s102 and s118 were re-rendered through `render_ffmpeg._scene_clip`. Both are **byte-identical** to V3's `scene_101` and `scene_117`.
- **Other scenes:** the render context matches V3's manifest. The only fingerprint change is s102, because its asset path moved. A rebuild from this graph therefore reuses the other 154 V3 clips unchanged, and narration, captions and timing stay as they are.

### Cleanup

- `render_full_v3/silent.mp4` (990 MB) was deleted. It is a concat intermediate that every render re-creates. Only report text referred to it, and fuser/lsof showed no open handles. It is logged in the deletion manifest.
- V3 scene clips (156) are kept.
- V2 and V3 finals are kept, and their checksums re-verified OK.
- Free space is now 9,129 MiB.

### Credits

The s102 Pexels line was removed from `FINAL_VIDEO_CREDITS.md`, because the clip is no longer used.

### New blocker: chart titles overflow

- QA now has `--edge-type dataviz`, which checks every chart.
- 8 of 22 charts fail: s51, s61, s66, s120, s125, s134, s140, s144.
- The titles run to or through the right edge. s140 and s144 are visibly cut.
- This is a pre-existing F4 chart issue.
- The fix proposal and the human checklist are in `P34_V3_VIEWING_CHECKLIST.md`.
- **V3 is not ready for upload review until this is fixed (v4) or explicitly accepted.**

## v4: chart-title fix (approved)

- **Master:** `data/finance_p34/render_full_v4/final_p34_v4.mp4`
  - sha256 `2900ebf096c14193d739fdf9c7a14cf1d43e4fea0028c9c8dca0f9e373cd0133`
  - 226.5 MB
  - Not committed.
- **Fix:** `scripts/k70_p34_chart_titles_fix.py`.
  - Shortened 8 titles: s51, s61, s66, s120, s125, s134, s140, s144.
  - Each new title was measured with the real title font: widest 830 px against a 922 px plot width.
  - Only those charts were re-rendered. Each new clip's outer-edge luma is ≤ 23.
  - Graph backup: `scene_graph_p34.pre_titles.json`.
- **Render:** 147 clips reused and 9 rendered, 1051 s.
  - Only the 8 chart clips differ from v3.
  - s102 is byte-identical. It re-rendered only because its asset path moved.
  - The captions file is byte-identical to v3.
- **QA:** 11/11 PASS (`render_full_v4/P34_V4_MASTER_QA.json`).
  - 656.767 s; sync 0 ms ×5.
  - No black segments; 156/156 mid-frames OK.
  - 576 captions.
  - text_inside_frame passes on all 22 charts (max edge luma 15).
  - Contact sheet: `render_full_v4/contact_sheet_v4.jpg`.
- **Built-in pipeline QA:** the same two informational flags as v2 and v3:
  - RAM peak 7.5 GB system-wide; min free 4.4 GB.
  - Plan vs delivery.
- **V2 and V3 masters:** kept; checksums re-verified OK.
