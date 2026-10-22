# P3.4 Full Render & QA Report: K70 Bitcoin Ep. 1

## Final master

- **File:** `data/finance_p34/render_full_v2/final_p34.mp4` (sha256 `84d4b5bef94fffed…`).
- **Spec:** 1080×1920, 30.0 fps, h264 + aac 2 ch at 96000 Hz.
- **Length:** 656.767 s (timeline 656.942 s). The audio track is 656.759 s.
- **Size:** 226.4 MB.
- **Graph:** `data/finance_p34/bitcoin_final_v1/scene_graph_p34.json`, with one render-time override: s102 uses the motion_gfx card `s102_gfx.mp4`. This is the same override P0 V2 used, because the Pexels clip is near-black. The source graph is unchanged; the effective graph is saved as `render_full_v2/scene_graph.json`.

## Render history

1. **`render_full_v1/final_p34.mp4`:** full render in 1242.8 s (39 scenes reused, 117 rendered). QA failed on **s102 near-black** (luma 1.4). Kept for reference, not for release.
2. **`render_full_v2/final_p34.mp4`:** v1's clips plus the s102 override (155 reused, 1 rendered); 862.6 s. **Release candidate.**

## Prerequisites (all passed before rendering)

- **Disk:** 5.15 GB deleted (162 files; see `P34_DELETION_MANIFEST.json`, with sha256 of each file). Free space went from 8.41 GB to **13.23 GB**, above the 12 GB target.
  - Deleted: the three `silent.mp4` intermediates, the 156 F4-cinematic scene clips, 2 orphan cache videos and the Whisper model.
  - Kept because a cross-project scan (219,147 text files) found real references: `data/benchmarks` (referenced by code) and 155 cache videos. `data/finance_f3` was kept as instructed.
- **Protected assets verified present:** masters, P3.4 graph, narration, music, the 20 final Three.js clips, the 8 original AI clips, the s35/s67 charts and F3.
- **Geography:** s22 India is the authored "Bretton Woods signatory" (India was among the 44 nations); s31 Japan is the authored "dollars across the Pacific". Both are illustrative and consistent with the narration. **Pass.**
- **AI rights:** the P3.4 graph references **no** Pollinations-derived asset (0 references). All 8 unresolved AI clips were replaced in P3.3 and are preserved only on disk. **Pass.**

## QA results (`scripts/k70_p34_master_qa.py`, release candidate)

| Check | Result | Detail |
|---|---|---|
| resolution_1080x1920 | PASS |  |
| fps_30 | PASS |  |
| codecs_h264_aac | PASS |  |
| duration_matches_timeline | PASS | 656.767 s against 656.942 s; the 0.175 s difference comes from quantizing 156 clips to whole frames. The last 0.25 s of the voiceover is silent (peak −38 dB), so no narration is lost. |
| audio_video_same_length | PASS |  |
| audio_sync_within_40ms | PASS | 5.0 s: 0.0 ms (corr 0.981); 164.2 s: 0.0 ms (corr 0.989); 328.5 s: 0.0 ms (corr 0.997); 492.7 s: 0.0 ms (corr 0.987); 641.9 s: 0.0 ms (corr 0.992) |
| no_black_segments | PASS | blackdetect, true black (≥1 s): none |
| scene_midframes_ok | PASS | 156 scene mid-frames checked; none near-black or flat |
| captions_present_and_within_video | PASS | 576 cues from 0.0 to 648.98 s |
| captions_corrected_wording | PASS | "race to the moon" present; "sharply higher" and "an one hundred" absent. s126 captions are deliberately yielded under the hero stat. |

**Informational items**
- 32 freeze segments of 2.5 s or longer. These are expected holds on kinetic-typography cards and still plates.
- Built-in pipeline QA flags "RAM peak 6.1 GB > 4 GB". That figure is system-wide memory use; minimum free stayed at 5.6 GB.
- Built-in pipeline QA also flags "plan-vs-delivery 40/156 downgraded". It compares against the legacy F4 storyboard plan, so it includes the deliberate P3.x replacements.
- Dark scenes listed for manual review were checked by eye and are fine: s92/s96 are terminal graphics, s151 is a night aerial, s46/s145/s153 are dark plates, and the navy brand cards are dark by design.
- A 156-frame contact sheet was reviewed.

## Defects found that are NOT fixed (pre-existing)

1. **s118 chart overflow.** The counter "$250 pesos / week" is wider than the frame and reads as "0 pesos / w". It comes from the original F4 job chart (`jobs/k70_f4_bitcoin_ep01/visuals/s118_chart.mp4`) and was present in every earlier cut. The fix is to re-render that chart with a shorter label (e.g. "$250 / week") and re-encode the master, which takes about 15 minutes. **Needs approval.**
2. **The Premium V2 master `data/finance_p0/k70_bitcoin_ep01_premium_v2/final_p0_v2.mp4` (145 MB) is not a valid MP4** ("moov atom not found"). That render was interrupted. It was not touched; earlier reports that called it intact were wrong.

## Not done (as instructed)

- PR #9 is not merged. Nothing was published to YouTube.

## Disk now

Free space is about 8.1 GB after two renders. `render_full_v1/` (about 2.3 GB, superseded) can be removed with approval.
