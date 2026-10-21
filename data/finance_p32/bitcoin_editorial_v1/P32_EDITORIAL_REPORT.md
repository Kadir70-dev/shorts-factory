# K70 Bitcoin Ep. 1: P3.2 Editorial Repair Report

- **Date:** 2026-10-22
- **Input (read-only):** `data/finance_p31/bitcoin_repaired_v1/scene_graph_p31_repaired.json` (sha256 `6f5175d2b1ba72ac…`)
- **Output (new copy):** `data/finance_p32/bitcoin_editorial_v1/scene_graph_p32.json`
- **Tooling:** `scripts/k70_p32_editorial_repair.py` applies the reviewed decision file `p32_decisions.json`. The machine-readable record of every change is `p32_changes.json`.

**Status:** this is an unrendered graph plus six single-scene test clips. **There is no full-length render.** None of the existing masters, voiceover, captions or the P3.1 output were modified.

---

## 1. Headline finding: s30 and s126 were text defects, not voice defects

Before regenerating any speech, I checked what the recorded voice actually says.

| Scene | Graph `narration` (P3.1) | Recorded clip, transcribed by local Whisper small | Timed captions |
|---|---|---|---|
| s30 | "…A race **sharply higher**." | "A war in Vietnam. A war on poverty. A race **to the moon**." | "A race to the / moon." |
| s126 | "…print **an one** hundred trillion dollar note." | "Within weeks, the central bank would print **a** $100 trillion note." | "print **a** / one hundred" |

Two further checks back this up:

- **Clip match:** the job clips `vo/scene_29.wav` and `vo/scene_125.wav` are sample-identical (mean abs diff 0, correlation 1.0) to the Kokoro narration-cache entries for the **corrected** sentences. The engine was the same: `k70_host_v1`, cascade `kokoro`.
- **Where the error came from:** the compliance rewrite and the a/an error happened in the graph text after TTS. They never reached the audio.

**What was done:**
- The narration text of s30 and s126 was restored to match the recorded speech.
- The script refuses a text fix unless the new words equal the timed caption words in that scene's window (`p32_editorial.caption_words`).
- **No voice segment was regenerated.** It was not needed: the speech is already correct, and the TTS cache is deterministic, so it would have returned the same bytes.
- The voiceover, captions and every duration are unchanged. The total is still 656.942 s.

**Still stale:** `meta.compliance_notes` still describes the old s30 rewrite. Metadata was left untouched under the frozen-field rule, so P3 still raises its `compliance_rewrite_changed_narration` flag.

---

## 2. Visual repairs (21 scenes)

All sources come from Wikimedia Commons and were fetched by exact file title. For each one, the licence, author and date are as stated on its Commons page, recorded with a sha256 in `p32_changes.json → provenance`.

**This is not a legal clearance.** A human still needs to confirm the licences and add attribution, especially for CC BY and CC BY-SA files.

Every repaired scene uses a 1080×1920 plate (`assets/plates/`). The plate shows the whole source image over a blurred copy of itself, with an on-screen identity or date label. Landscape stills are no longer centre-cropped into a 9:16 slice.

### Task 1: Historical identity

| Scene | Before (P3.1) | After | Notes |
|---|---|---|---|
| **s42** Nixon | Stock clip of an unidentified man | Verified Nixon official portrait (8 Jul 1971, public domain), labelled as such, with a dated evidence line: "ADDRESS TO THE NATION · Sunday, 15 August 1971" | No licensed frame of the 15 Aug broadcast was found. The 9 Sep 1971 Congress photo was rejected because it is a different speech. The plate does **not** claim to be the broadcast. |
| **s82** Chaum | Stock clip of an unidentified man | David Chaum at Web Summit 2018 (CC BY 2.0, Web Summit), labelled "photographed 2018" | Identity rests on the event organiser's caption. It is dated so it is not presented as a 1982 image. |

### Task 2: Archival corrections

| Scene | Narration | Before (P3.1) | After | Licence |
|---|---|---|---|---|
| s23 | "it worked beautifully" | 1950s motel postcard | Main Street, Greenville, c. 1958 postcard | Public domain |
| s30 | Vietnam / war on poverty / moon | Couple watching TV | Triptych: UH-1D helicopters in Vietnam (1966), LBJ signing the Economic Opportunity Act (1964), Apollo 11 launch (1969) | Public domain (US Army, Stoughton/White House, NASA) |
| s52 | "1970s … a mugging" | 2025 Hong Kong rice aisle | Ford "Whip Inflation Now" button (1974) | Public domain |
| s56 | grocery prices | 1905 Brisbane fruit shop | Supermarket, Annandale VA, late 1970s | Public domain (per Commons) |
| s58 | savings "slow leak" | 19th-century coin table | Savings passbook, labelled 1953 (illustrative) | Public domain |
| s80 | "how do we fix the banks?" | 2024 Portland tower | Bank branch facade, Gustine CA (illustrative) | CC BY 4.0 |
| s88 | "by a full decade, the future" | Climate temperature chart | Typography: "DIGICASH · Founded 1989. Bankrupt 1998." The existing "TEN YEARS EARLY" headline still renders. | No image (none licensed found) |
| s95 | "And they did." | Store keyboard aisle | 1997 "Munitions" T-shirt carrying export-restricted crypto code | CC0 (Adam Back) |
| s111 | Liberty Dollar raid, 14 Nov 2007 | Eisenhower dollar | Typography: "14 NOVEMBER 2007 · LIBERTY DOLLAR · Offices raided. Coins seized." The source overlay is kept. | No image: the Commons search returned only 19th-century Seated Liberty coins |
| s112 | "somebody knocks on the door" | 1918–38 China lantern slide | Closed door with knocker (illustrative metaphor) | CC BY-SA 4.0 |
| s114 | "Nobody knew how to build that." | Electricity photo | Bare door and frame (illustrative metaphor) | CC0 |
| s117 | savings frozen | World map (PIIGS) | Savers protesting outside BBVA Banco Francés, Buenos Aires, labelled **Feb 2002** | CC BY-SA 3.0 |
| s126 | Z$100 trillion note | Framed set of 16 notes | The exact Z$100,000,000,000,000 note (obverse), whole note visible | Public domain per Commons. Currency reproduction rules need human review. |
| s146 | bailout with public money | Taipei tower | U.S. Treasury Building, Washington (illustrative; Treasury ran TARP) | CC BY-SA 3.0 |

**Typography and illustrative scenes:** s88 and s111 are factual typography, because no correct imagery could be sourced. Neither invents evidence. s80, s112, s114 and s146 are illustrative and make no historical claim.

### Review scenes

| Scene | Finding | Action |
|---|---|---|
| s15 | 1923 five-million-mark note | **Kept** (provisional keep, as the brief asked) |
| s132 | Northern Rock queue, 2007 | **Kept** (provisional keep) |
| s38 | Real Michigan bank run, Feb 1933, used as an analogy for 1971 | Kept, and the plate now labels it "February 1933" |
| s121 | Real corralito protest, but dated **6 Feb 2002**, not Dec 2001 | Kept, and the plate now labels it "Feb 2002" |
| s115 | Unidentified ATM/wall (Basque "Caixak"). Not false, just irrelevant. | **Flagged for manual review.** Unchanged. |
| s129 | Street in Pune, India, against "not here, not to us" (the Western suburbs) | Replaced with a US suburban street, 2008 (CC BY-SA 4.0) |

### Rejected candidates

These are recorded in `p32_decisions.json → rejected_candidates`.

- **Nick Szabo (s98):** the only free photo is a group stage shot, and he cannot be identified in frame.
- **CCC 2007 "Cypherpunks" sign:** a 2007 sign would read as 1990s evidence.
- **Nixon 9 Sep 1971 Congress address:** the wrong event.

---

## 3. Overlay fix found during test rendering (s126)

`render_ffmpeg` draws `stat.sub` as the hero number and `stat.text` as the label. The authored s126 stat had these two fields swapped. As a result, "issued 16 January 2009" rendered at hero size and ran off-frame, which the test clip showed.

Because the overlay is unchanged from P3.1, the P3.1 graph has this same defect.

I also tried "Z$100 TRILLION" as the hero, and it still overflowed. The fix is:
- **Hero:** `Z$100T`
- **Label:** "one hundred trillion dollars · issued 16 January 2009"

The re-rendered test clip was checked visually and fits. This is the only overlay changed; the validator allows overlay edits only for listed scenes.

---

## 4. Editorial polish

**Transitions:** 35 changed from crossfade to cut.
- 29 were card-to-card joins (motion_gfx or dataviz).
- 6 were punch beats shorter than 2 s.

| Transition | P3.1 | P3.2 |
|---|---|---|
| Crossfade | 133 of 156 (85%) | 98 (63%) |
| Cut | 2 | 37 |

What was preserved:
- Every dissolve into or out of the 3D and AI cinematic scenes.
- Every fade, dip_to_black and whip.
- s35 and s67.

In `render_ffmpeg`, transitions are duration-preserving effects inside each clip, so a cut cannot shift audio or caption sync. P3 still raises `transition_monotony` because crossfade is still above 50%. I stopped there rather than also cutting footage-to-footage dissolves, which are part of the established "dissolve_essay" style.

**Card runs:** three scenes that were cards now carry verified imagery, and their text overlays still render on top.

| Scene | Beat | New image | Licence |
|---|---|---|---|
| s28 | "Congress listened politely…" | U.S. Capitol, c. 1964 | CC BY 2.0 |
| s96 | Hashcash beat | Adam Back, photographed 2014 | CC BY 2.0 |

| Card runs | P3.1 | P3.2 |
|---|---|---|
| Card scenes | 54 | 52 |
| Longest run | s93–s100 (8 scenes) | s8–s11 and s97–s100 (4 each) |

**Still pending:** runs of 4 at s8–s11 and s97–s100, and runs of 3 at s43–s45, s63–s65, s83–s85 and s108–s110. Breaking these needs either more verified imagery or new card authoring.

---

## 5. Safety checks (verified on the output graph)

- **Scene timing:** all 156 scene IDs are in the same order. Every `duration_sec` is identical (total 656.942 s).
- **Unchanged blocks:** `captions`, `audio`, `sfx`, `meta`, `storyboard` and all provenance blocks.
- **Cinematic scenes:** all 20 Three.js and 8 AI cinematic visuals are byte-identical, and so are their transitions.
- **Sourced charts:** s35 and s67 are identical (visual, data and transition).
- **Narration:** changed only in s30 and s126, as described in section 1.
- **Media paths:** every `asset_path` in the graph exists on disk. The SceneGraph is Pydantic-valid; the check runs on a copy with 0.8 s clamping, like P3.1.
- **Frozen inputs:** the P3.1 folder, `final_p0_v2.mp4`, the job voiceover, the frozen 14-layer architecture, `config/visual_budget.yaml` and the Shorts pipeline were not touched.
- **Paid services:** none were used. The only network access was free Commons API queries.

---

## 6. Test clips (rendered, validated)

Six scenes were rendered with the real `render_ffmpeg._scene_clip` into `test_clips/`: s30, s42, s82, s96, s111 and s126.
- All are 1080×1920 and within one frame of the scene's duration.
- Mid-frames were inspected visually. Overlays, labels and plates are readable.
- s96's two-line headline sits close to the top of the photo. This is acceptable but worth a look in a full review.
- Disk use is about 69 MB. You can delete these clips freely.

---

## 7. Tests

- `tests/test_k70_p32_editorial.py`: 6 new tests, all passing. They cover:
  - narration fix only when the captions match, otherwise re-TTS is required
  - the 3D/cinematic and chart guards
  - selective transition polish
  - timing and caption tamper detection
  - the overlay-fix guard
  - plate sizes
- `tests/` overall: **122 passed**.

---

## 8. Still pending (needs a human decision)

1. **Licensing and attribution:** confirm every licence and write the attribution credits (CC BY/BY-SA: s28, s80, s82, s96, s112, s117, s121, s129, s146). Review the reproduction of the Zimbabwe note.
2. **s42:** a real licensed clip of the 15 Aug 1971 broadcast, for example from NARA or the Nixon Library, would beat the portrait card. None was available on Commons.
3. **s115:** manual decision on its visual.
4. **Generic stock elsewhere:** 14 other footage scenes still flagged by P3 `named_subject_on_generic_stock` (s13, s16, s21, s25, s40, s70, s75, s92, s107, s122, s133, s139, s143, s149), plus s18 and s151 (`resolved_archival_source_not_used`). They were outside this brief and are unchanged.
5. **P3 lexical flags:** P3's `narration_visual_terms_differ_review` count rose from 29 to 30. Repaired scenes keep their old `visual.query` text, so these flags are heuristic noise, not frame evidence.
6. **Full render and review:** a full-length render and a human frame-by-frame review are still needed before anything is called final.

---

## 9. Licence audit and release gate (added 2026-10-22)

The full table is in `P32_ASSET_CREDITS.md`; the raw live Commons metadata is in `p32_license_audit.json`.

All 21 source files are public domain, CC0, CC BY or CC BY-SA, so all are compatible with commercial use. **Do not merge or release** until these are signed off:

- **s56:** its PD claim (`PD-US-1978-89`) rests on a Facebook repost credited to United Natural Foods, Inc. Verify it or replace it.
- **s126:** Commons marks the file as possibly protected by currency-reproduction laws.
- **s82 and s96:** identifiable living people (personality rights).
- **CC BY-SA adaptations** (s112, s117, s121, s129, s146): the share-alike terms must be confirmed for the adapted plates.
- **Credits:** the 9 required CC BY / BY-SA credits must appear in the description or end card.

**Remaining editorial issues:**
- s115 still needs a manual review.
- The 14 generic-stock scenes listed in section 8 are unchanged.
- Card runs of 4 remain (s8–s11, s97–s100), plus runs of 3. Crossfades are still 63% of transitions.
- Full-film QA (full render plus a human frame review) has not been done.
