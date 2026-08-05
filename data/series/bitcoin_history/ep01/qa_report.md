# QA — The World Before Bitcoin | The Complete History of Bitcoin · Ep. 1

`data/series/bitcoin_history/ep01/scene_graph.json` · 156 scenes · 14.27 min · brand `k70` · structure `timeline_twist_conclusion`

**PASS** — 26/26 checks

| | Check | Result |
|---|---|---|
| | **STRUCTURE** | |
| PASS | schema validates against SceneGraph 2.0 | 156 scenes · schema_version 2.0 |
| PASS | runtime inside the 10-15 min brief | 856s = 14.27 min |
| PASS | scene ids unique and contiguous | s1 … s156 |
| PASS | storyboard covers every scene | 156 semantic beats |
| PASS | every scene inside the 0.8-12s beat window | no outliers |
| | **VISUAL** | |
| PASS | every narration sentence carries a visual plan | 156/156 beats |
| PASS | no talking-head / flat-colour beats | 0 solid beats |
| PASS | no repeated visual across the episode | 136 distinct visuals |
| PASS | no repeated visual objective | 156 distinct objectives |
| PASS | authored mix spans all six budget channels | motion_gfx 28.2% · official 17.8% · charts 16.2% · ai_broll 15.2% · threejs 13.5% · stock 9.2% |
| PASS | pipeline allocator assigns every scene | 156/156 scenes assigned |
| PASS | allocator's own plan lands inside every band | motion_gfx 32.3% · threejs 16.1% · official 15.2% · ai_broll 16.3% · stock 10.0% · charts 10.0% |
| PASS | no scene left unresolved by the allocator | 0.0s unresolved |
| | **SOURCING** | |
| PASS | every chart has real data behind it | 21 charts |
| PASS | every chart carries an attribution | all attributed |
| PASS | sourced beats show their attribution on screen | 68 beats carry a source overlay |
| PASS | speculative/probable beats are hedged in the read | all hedged |
| PASS | no absolutes on an unconfirmed beat | clean |
| | **STORY** | |
| PASS | a twist at least every 40s | 59 turns/reveals · longest gap 34s |
| PASS | median twist spacing inside 20-40s | median 14s |
| PASS | every chapter ends on a cliffhanger beat | 10 chapters |
| PASS | opens on a hook, closes on the Episode 2 hand-off | s1 `hook` → s156 `cta` |
| PASS | no filler beats | none |
| | **MUSIC** | |
| PASS | score has both quiet passages and swells | 35 quiet beats · 78 swell beats · 4 hooks |
| | **RENDER** | |
| PASS | overlays keep clear of the caption band (y<=0.70) | clear |
| PASS | synthetic beats are countable for YouTube AI disclosure | 24 AI recreations (15% of runtime) — requires the 'Altered or Synthetic Content' box |

## Delivered visual mix (authored plan)

| Channel | Share | Seconds | Band |
|---|---|---|---|
| motion_gfx | 28.2% | 242s | 25-35% |
| official | 17.8% | 152s | 15-25% |
| charts | 16.2% | 138s | 10-20% |
| ai_broll | 15.2% | 130s | 15-25% |
| threejs | 13.5% | 115s | 15-25% |
| stock | 9.2% | 79s | 10-20% |

## What this does NOT check

Black frames, loudness, caption drift and encoded duration are
properties of the finished MP4 — `pipeline/qa.py` gates those
during `scripts/produce.py`. This report gates the spec only.