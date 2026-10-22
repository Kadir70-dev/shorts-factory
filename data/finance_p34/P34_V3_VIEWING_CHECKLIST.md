# K70 Ep. 1 v3 — viewing checklist (pre-upload review)

- **Master:** `data/finance_p34/render_full_v3/final_p34_v3.mp4`
  - sha256 `ae33ef82…ab29`, re-verified after cleanup.
  - Unchanged by this pass.
- **Graph:** `data/finance_p34/bitcoin_final_v1/scene_graph_p34.json`, with s102 and s118 now permanent. Two single-scene backups exist:
  - `scene_graph_p34.pre_s102.json`
  - `scene_graph_p34.pre_s118.json`

**Who checked:** the model did these checks, using measurements and extracted frames. They are not a substitute for one person watching the full 11 minutes with sound. The playback sign-off box at the end is for that.

## 1. Captions

| Check | Result | Evidence |
|---|---|---|
| Burned-in track present | PASS | 576 cues; first 0.00 s, last ends 648.98 s; byte-identical to v2 |
| Corrected wording | PASS | "race to the moon" present; "sharply higher" and "an one hundred" absent |
| Placement | PASS | Six sampled frames: one line, centred, y ≈ 1450 of 1920, clear of charts and plates |
| Yield under hero stats | As designed | Captions step aside under hero numbers (for example s126). Narration still carries the words. |
| Reading speed by eye | **Human** | Needs real-time playback |

## 2. Audio

| Check | Result | Evidence |
|---|---|---|
| Sync to voiceover | PASS | 0 ms offset at 5, 164, 328, 493 and 642 s; correlation 0.981–0.997 |
| Loudness | PASS | −16.3 LUFS integrated, LRA 2.0 LU, true peak −1.1 dBFS (no clipping; YouTube only turns down) |
| Dropouts | PASS | No silence ≥ 1.5 s below −45 dB across the film |
| A/V length | PASS | Audio 656.759 s, video 656.767 s |
| Music/VO balance and SFX taste | **Human** | Needs listening on headphones and a phone speaker |

## 3. Scene transitions

| Check | Result | Evidence |
|---|---|---|
| Mix | Info | 80 crossfade, 55 cut, 11 dip-to-black, 8 fade, 2 whip. All are in-clip, so timing is unchanged. |
| No true black ≥ 1 s | PASS | blackdetect is empty. The 8.4 s of brief dark frames (1.3 %) are dip-to-black transitions and dark brand cards. |
| Every scene lit at mid-roll | PASS | 156/156 mid-frames; `render_full_v3/contact_sheet_v3.jpg` |
| Rhythm and feel | **Human** | Needs playback |

## 4. Historical visuals

| Check | Result | Evidence |
|---|---|---|
| Provenance of every scene | PASS | `data/finance_p33/bitcoin_release_v1/FULL_FILM_PROVENANCE_AUDIT.md` (156 scenes) |
| No ShareAlike, no AI imagery | PASS | P3.3 rights pass; 0 Pollinations references in the graph |
| s102 | PASS | Original K70 card ("A digital coin is a file…") replaces the near-black Pexels clip. It is now in the graph, not a render override. Re-rendering through the production renderer gives a clip byte-identical to the one in V3. |
| s118 | PASS | `$250` / "Pesos per week, Dec 2001", Decree 1570/2001. Byte-identical on re-render. |
| s22 / s31 geography | PASS | India is a Bretton Woods signatory; the Japan shot shows dollars crossing the Pacific |
| **Chart titles inside the frame** | **FAIL** | See §6 |

## 5. Credits

| Check | Result | Evidence |
|---|---|---|
| Description credits block | PASS | `data/finance_p33/bitcoin_release_v1/FINAL_VIDEO_CREDITS.md`, "Paste into the YouTube description" |
| CC BY attributions | PASS | s80, s82, s28, s108, s139 and s132 are listed with author, licence and link. s80, s82, s28, s108 and s139 also carry an on-image credit. |
| s102 Pexels credit | Fixed | Removed, because the clip is no longer in the film |
| Pasting into YouTube | **Human** | Do this at upload |

## 6. Blocker found in this pass: chart titles overflow the right edge

- The F4 dataviz renderer wraps chart titles to the full 1080 px width. It does not leave a right margin, while the left pad is 80 px.
- The new `--edge-type dataviz` QA check samples every chart. Of 22 charts, 8 have bright title pixels in the outer 24 px:
  - **Visibly cut:** s140 ("LEHMAN BROTHERS ASSETS AT FI…") and s144 ("COMPLETED U.S. FORECLOSURES F…").
  - **Running into the edge:** s51, s61, s66, s120, s125 and s134.
- This was already present in v2 and every earlier master.
- It is the same failure s118 had.

**Proposed fix (needs approval).** Use the same data-only pattern as s118: shorter titles, a re-render of those 8 charts only, and an incremental v4 master (about 18 min and about 2.5 GB disk). The shared Shorts dataviz code stays untouched.

| Scene | Current title | Proposed |
|---|---|---|
| s51 | Purchasing power of one 1971 dollar | Value of a 1971 dollar |
| s61 | Effective federal funds rate, peak | Fed funds rate, peak |
| s66 | U.S. savings & loans, 1986-1995 | S&L failures, 1986-1995 |
| s120 | Argentine sovereign default, 2001 | Argentina's default, 2001 |
| s125 | Zimbabwe price-doubling time, Nov 2008 | Zimbabwe, Nov 2008 |
| s134 | Runs on a British retail bank | Runs on a British bank |
| s140 | Lehman Brothers assets at filing | Lehman assets at filing |
| s144 | Completed U.S. foreclosures from 2007 | U.S. foreclosures completed |

Sources, values and labels stay as they are.

## Playback sign-off (human)

- [ ] Watched the full film with sound, on a phone in portrait
- [ ] Caption reading speed is comfortable
- [ ] Music under the voice is never distracting
- [ ] Transitions feel deliberate
- [ ] Credits pasted into the description
