# K70 Finance vs Dhruv Rathee — Documentary Quality Comparison (F5)

Date: 2026-10-20 · Scope: analysis only, no production code changed, no render launched.

## 0. What was and was not observed

| Source | What was actually examined | Not examined |
|---|---|---|
| Dhruv Rathee (3 public videos) | yt-dlp metadata (title, date, duration, views, chapters, description) and YouTube **auto-captions** (Hindi original + auto-translated English), timestamped | Picture and audio. **No video frames were viewed and no audio was heard.** Visual, music, SFX, grading and editing claims about his videos are therefore *not scored* below |
| K70 F4 documentary | Final MP4 (ffprobe, full decode, EBU R128 loudness, blackdetect, silencedetect, 22-frame contact sheet every 30 s, frame-to-frame PSNR), final SceneGraph, original authored graph, production log, QA report | Subjective listening of the voice (measured only) |

Reference videos (public URLs):

| ID | Title | Published | Length | Views at fetch |
|---|---|---|---|---|
| [sh7jXV3nwUo](https://www.youtube.com/watch?v=sh7jXV3nwUo) | Bitcoin kya hai? How Bitcoin works… | 2020-12-05 | 15:36 | 4.29 M |
| [dUm1J-glLGE](https://www.youtube.com/watch?v=dUm1J-glLGE) | Downfall of American Banks — SVB Crash Explained | 2023-03-20 | 17:29 | 5.46 M |
| [oImxcKc0qak](https://www.youtube.com/watch?v=oImxcKc0qak) | The Truth behind Inflation | 2020-06-14 | 12:59 | 3.38 M |

K70 video: `data/finance_f4/k70_f4_bitcoin_ep01_cinematic/final_f4_cinematic.mp4`
(656.8 s, 1080×1920, H.264 + AAC; "The World Before Bitcoin", Ep. 1). Base render without inserts:
`data/jobs/k70_f4_bitcoin_ep01/final.mp4` (untouched).

## 1. Dhruv Rathee — observable techniques (from transcripts/metadata)

1. **Hook = a concrete, personal number in the first 5 s.** Inflation 0:00 — "a ₹100 note from 1958 kept under your bed is worth ₹1.20 today". Bitcoin 0:02 — "value zero ten years ago, now almost ₹15 lakh". SVB 0:00 — "two of America's major banks have collapsed… second biggest failure in US history".
2. **Explicit roadmap within ~30 s.** SVB 0:38 "What happened exactly? How did it happen? And what will be the probable impacts?"; Inflation 0:55 "Why does inflation occur… is it really a bad thing… related to unemployment?".
3. **Question-led narration.** Rhetorical questions counted in auto-captions: 12 (Bitcoin), 9 (SVB), 16 (Inflation). K70 script: **2**.
4. **Everyday analogies, timestamped.** Inflation 1:44 "imagine an aeroplane with 100 seats"; Bitcoin 1:41 "take a look at any note in your wallet… 'I promise to pay the bearer'"; SVB 3:02 "suppose you use all your savings for buying gold". Analogy/example markers: 7 / 5 / 6. K70: **1**.
5. **Direct address and reassurance.** "Greetings, friends!" openers; Bitcoin 6:08 "if all this explanation went straight above your head like a bouncer, then do not worry".
6. **News-clip montage as evidence.** SVB 0:44–1:15 — eight quoted lines from news broadcasts ("Silicon Valley Bank collapsed on Friday", "the bank stock lost 80% of its value this week") inserted before the explanation begins. (Observed as quoted audio in captions; the picture was not viewed.)
7. **Chapters.** Bitcoin: 7 chapters; Inflation: 6; SVB: none.
8. **Speech rate.** ~205–208 Hindi words/min across all three (auto-caption word count ÷ duration; approximate, and not directly comparable to English wpm).
9. **Balanced close + next-video CTA.** Bitcoin ends "both an opportunity as well as a risk"; SVB ends with an expert outlook then "click here" to the bank-business-model video.
10. **Sources in description: none listed** in all three descriptions (0 occurrences of "source"; only app/Patreon/podcast links). On-screen sourcing could not be verified without viewing.

Not observed and therefore not claimed: his motion-graphics style, maps, 3D, footage ratio, music, SFX, typography, grading, cut rhythm, private workflow or tools.

## 2. K70 F4 documentary — measured facts

| Measure | Value | Evidence |
|---|---|---|
| Duration | 656.8 s (10:57) — 57 s over the 8–10 min brief | ffprobe |
| Scenes | 156; mean 4.21 s, median 4.12 s, min 0.85 s, max 9.38 s | final SceneGraph |
| Narration rate | 158 wpm (1726 words); stock Kokoro voice, not the cloned K70 voice | graph + voice diagnostics |
| Loudness | Final mix −16.3 LUFS integrated; narration stem −23.7 LUFS; no silence ≥1.5 s at −45 dB | ebur128, silencedetect |
| Visual time share | motion_gfx **43.9 %** (71 scenes) · stock b-roll 30.7 % (52) · charts 16.7 % (20) · F2 cinematic clips 4.1 % (6) · stills 4.7 % (7) | final SceneGraph |
| Planned vs delivered | 16 planned **threejs → motion_gfx**, 2 → b-roll, 2 → image; 8 official → motion_gfx; 13 ai_broll → stock | authored vs final graph |
| Attribution | 68 on-screen source overlays, 21 charts with sourced data, 50 headlines, 30 lower-thirds | final SceneGraph |
| Contact sheet (22 frames, every 30 s) | **12/22 are the same dark-navy kinetic text card** layout | `contact.png` frames 0:08, 0:38, 2:08, 3:08, 4:38, 5:08, 6:08, 6:38, 7:08, 9:08, 9:38, 10:38 |
| Static frames | 4:38 (s64): near-black (YAVG 16), **PSNR 63 dB between 0 s and 1.5 s** = no motion; 9:08 (s131) text barely readable | signalstats/psnr |
| Dark stretches ≥1 s | 5 (271.5 s, 277.9 s, 366.0 s, 453.0 s, 634.7 s) — all dark kinetic cards, not empty frames | blackdetect + frames |
| Base production QA | FAIL: RAM 4066 MB (>4000), wall time 3815 s (>3600), 2 dark stock picks (fixed in F4 cinematic version), 16 silent downgrades | qa_report.txt |

Frame observations (viewed): strong 0:00–0:47 cold open narration; charts are clean and legible (2:38 "61 % of reserves lost 1952–1971", 4:08 US CPI line chart); 1:08 stock banknotes **appear not to be US dollars** in a US-dollar story; 10:08 a generic suburban house and 8:38 a helicopter on a white sky read as loosely related stock; captions are small relative to frame.

## 3. Side-by-side comparison

Dhruv scores are given **only where the transcript gives evidence**; "n/s" = not scored (not viewed). K70 scores are from the measured facts above.

| Category | Dhruv Rathee (evidence) | K70 Finance (evidence) | Gap | Improvement | DR | K70 |
|---|---|---|---|---|---|---|
| Storytelling | Concrete personal hook ≤5 s; roadmap by ~0:38; chapters; balanced close | Excellent suspense cold open (0:00–0:47 "The gold was not there"); timeline→twist; cliff-hanger end "Episode two. The nine pages." No roadmap, no chapters | Viewer orientation + personal stakes | Add a 1-line "why this matters to your wallet" + 3-question roadmap after the cold open; emit YouTube chapters from acts | 8 | 7 |
| Narration | Conversational 2nd person, ~205–208 Hindi wpm, reassurance lines | 158 wpm stock TTS; only 8/156 lines address "you"; 2 questions | Voice identity, energy, interaction | Restore cloned voice; +6–10 % pace; add questions/asides at act turns | n/s (audio not heard) | 5 |
| Cinematic visuals | n/s | 6 F2 clips = 4.1 % of runtime; stock is generic and partly mismatched (1:08 non-US notes) | Too little bespoke imagery; weak stock relevance | More AI stills (paced free tier) for ai_broll beats; tighter stock query/QA | n/s | 4 |
| Motion graphics | n/s | 43.9 % of runtime is one card template; 12/22 sampled frames identical layout; s64 static 1.5 s | Repetition and dead frames | 4–6 kinetic templates with immediate text-on, background motion, icons/maps | n/s | 4 |
| 3D animation | n/s | 0 delivered (worker deps were missing; fixed after render); 20 planned scenes fell back | Planned 3D absent | Re-render 3D beats (now working, ~7 s per 0.8 s preview @360p on this CPU) | n/s | 1 |
| Editing | n/s | 4.2 s mean shot; single `dissolve_essay` transition family | Uniform rhythm | Vary cut length by beat role; match-cuts/whip on act turns | n/s | 5 |
| Research quality | No sources listed in any of 3 descriptions; on-screen sourcing not verified | 68 on-screen source overlays, 21 sourced charts, QA sourcing checks PASS | K70 is ahead on visible attribution | Keep; add a sources list in the YouTube description | n/s | 8 |
| Sound design | n/s | −16.3 LUFS (≈2 dB under the common −14 LUFS streaming target); music + SFX stages ran; not listened | Unknown subjective quality | Normalize to −14 LUFS; listening QA | n/s | n/s (measured only) |
| Audience retention | Number hook, roadmap, news-clip montage (SVB 0:44), chapters, end CTA to next video | Strong cold open, cliff-hanger; no roadmap/chapters; long stretches of text cards | Mid-video visual fatigue | See P0 list | 8 | 6 |
| Overall polish | n/s | Clean branding, captions, charts; fallback-heavy visuals, static frames, 57 s over length | Visual variety + voice | P0 items below | n/s | 5 |

## 4. Top 10 problems in our documentary (ranked)

1. **Visual monotony** — 43.9 % one dark kinetic-card template (`motiongfx.kinetic`).
2. **Planned 3D absent** — 20 threejs beats became cards/stock (dependency gap, now fixed).
3. **Static/empty frames** — s64 (4:38) unchanged for ≥1.5 s; delayed text-on leaves dark frames.
4. **Stock relevance** — 1:08 banknotes appear non-US; generic house (10:08), helicopter (8:38).
5. **Voice** — stock Kokoro, 158 wpm, flat; cloned K70 voice unavailable on this laptop.
6. **Length** — 10:57 vs 8–10 min brief (narration-driven).
7. **Only 6 cinematic AI clips (4.1 %)**; 13 ai_broll beats fell to stock because the allocator ignores pre-attached stills.
8. **No roadmap/chapters, few questions/analogies** (2 questions, 1 analogy vs 9–16 / 5–7 in references).
9. **Uniform editing** — one transition family, near-constant 4 s shots.
10. **Ops** — base production 1 h 08 m, 4.16 GB peak, QA fails RAM and wall-time budgets.

Scenes that feel static/generic/repetitive (from frames): s64 (4:38), s131 (9:08, low-contrast), the card run around 2:08–3:08 and 6:08–7:08, stock at 1:08, 8:38, 10:08.

**Do the 6 cinematic clips help?** Yes, locally — 0:00 (s1), 1:30 (s21), 2:19 (s33), 2:46 (s39), 3:13 (s46), 3:58 (s56) are the richest frames in their minutes. But they are 4.1 % of runtime and all in the first 4 minutes (spacing rule + available stills), so the second half gets none.

**Does missing Three.js hurt?** Yes: 20 planned scenes (~13 % of beats) became the same text card, which is the main driver of problem 1.

## 5. Upgrade plan (mapped to existing modules; no code changed yet)

| P | Change | Module(s) | Effort | CPU/RAM impact on i5-4300U |
|---|---|---|---|---|
| P0 | 4–6 kinetic templates (stat-split, icon+text, map pin, timeline strip, quote card), text visible from frame 0, subtle background motion; ban >1 s static frames in QA | `pipeline/motiongfx.py`, `pipeline/qa.py` | 2–3 d | Similar per frame (ffmpeg/PIL); no RAM change |
| P0 | Honour pre-attached AI stills and render threejs beats (deps fixed); re-render only changed scenes via manifest reuse | `pipeline/visual_budget.py`, `pipeline/threejs_engine.py` | 1–2 d | 3D ≈ +1.4 GB RSS while rendering; preview 7 s per 0.8 s clip at 360p — full-res 20 scenes est. 30–60 min (not measured) |
| P0 | Script layer: roadmap line after cold open, YouTube chapters from acts, 1 question or analogy per act | `pipeline/storyboard.py`, `scene_director.py`, authored episode JSON | 1 d | None |
| P1 | Cloned voice back (reference clip/model are missing here) + per-job pace override | `voice/profile.py`, `voice/engines.py`, `config/voice/profile.yaml` | 0.5 d + assets | Kokoro ≈ 14 min for 11 min audio today |
| P1 | Stock relevance gate (country/currency/object terms, reject off-topic) | `pipeline/broll.py`, `providers.py` | 1–2 d | Network-bound |
| P1 | F2 spacing across whole runtime + more stills (paced free Pollinations ~50 s/image) | `tools/finance_cinematic_cpu/auto.py`, `stills.py` | 0.5 d | ~10 s clip render each at 720p |
| P1 | Loudness to −14 LUFS; listening QA | `pipeline/music.py` / final mux in `render_ffmpeg.py` | 0.5 d | Negligible |
| P2 | Transition variety by beat role; match/whip cuts at act turns | `pipeline/variety.py`, `render_ffmpeg.py` | 1–2 d | Small |
| P2 | Bring production under QA budgets (RAM 4.0 GB, 1 h) | `production_optimizer.py`, preset threads | 1 d | Goal: lower |
| P2 | 16:9 long-form variant (episode is authored 9:16) | presets, stills generator sizes | 1–2 d | 16:9 1080p ≈ same pixels |

All items stay inside the frozen 14-layer architecture: they change asset generators, allocation and QA, not the layer stack. No paid API is required.

## 6. Recommendation — 3 changes with the biggest visible effect

1. **Kinetic-card variety + no dead frames (P0, motiongfx/qa)** — fixes the single largest share of screen time (43.9 %).
2. **Deliver the planned 3D and AI-still beats (P0, visual_budget/threejs)** — replaces ~33 text-card/stock beats with designed visuals.
3. **Voice + roadmap (P0/P1, voice + storyboard)** — the cloned voice at a slightly faster pace, plus a 3-question roadmap and chapters after the cold open.

Next step requires approval: implementing any of the above and launching a new full render.
