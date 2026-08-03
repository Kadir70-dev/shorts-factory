# Pipeline upgrade — originality, branding and monetisation safety

What changed, why, and where each piece lives. This is a permanent architectural
change, not a set of switches: the old behaviour is gone in the places it was
causing harm.

---

## 1. Voice — your own, on every video

**Kokoro cannot clone a voice.** It ships fixed speaker embeddings baked into the
weights; there is no supported zero-shot or fine-tuning path. So narration moved
to engines that can carry a cloned identity.

| Tier | Engine | Licence | Cost/render | Role |
|---|---|---|---|---|
| default | **Piper fine-tune** | MIT | zero | every video |
| premium | **ElevenLabs clone** | licensed on paid plans | per character | when fidelity matters |
| optional | Chatterbox | MIT | zero (needs GPU) | off by default |
| refused | XTTS-v2 | **non-commercial** | — | blocked unless acknowledged |

Both production tiers are built from **one** recording session. Full walkthrough:
**[docs/VOICE_CLONING.md](VOICE_CLONING.md)**.

```bash
python scripts/voice_record_plan.py --identity k70_host_v1   # 103 takes, ~25 min
python scripts/voice_build_dataset.py --identity k70_host_v1 # clean + QA gate
python scripts/voice_train_piper.py --identity k70_host_v1   # local or free Colab
python scripts/voice_verify.py --identity k70_host_v1 --keep
```

### The identity lock

`config/voice/profile.yaml` sets `locked: true`. The synthesis cascade now
contains **only engines holding your clone**, and when they are all exhausted the
render **fails** rather than substituting a stock narrator.

This is the single most important behavioural change in the voice work. The old
cascade degraded across *different people* — ElevenLabs' Adam, then Kokoro's
am_michael, then Piper's Ryan — decided by whichever provider happened to be
reachable. A failed render is something you notice; a substituted narrator is
something your audience notices after you have published.

Consistency comes from one locked speaking rate, a pronunciation lexicon, and
number normalisation applied **in the pipeline** rather than inside each engine —
so `$4.2B` is spoken identically whether ElevenLabs or Piper rendered it, while
the screen still shows `$4.2B`.

*Code:* `apps/api/app/voice/`, `apps/api/app/pipeline/tts.py`

---

## 2. Story structure — the fixed template is gone

Nine narrative spines in `config/story_structures.yaml`, rotated per video with a
cooldown against the channel's recent history:

`mystery_reveal_lesson` · `timeline_twist_conclusion` · `problem_solution_impact`
· `myth_vs_reality` · `before_after` · `hidden_strategy` · `one_number_story` ·
`autopsy` · `two_paths`

The chosen structure drives four things: the Director prompt, the valid scene
count (the old hard-coded 4–7 window was the template's last remnant), the music
family, and which beats must carry a real figure.

Selection is **seeded** off the video id — so a re-run rebuilds the same short —
and **weighted against history**, so structures genuinely take turns. Pure random
clusters; five consecutive videos sharing a spine is a likely coin-flip sequence
and a very visible pattern.

*Code:* `apps/api/app/director/structures.py`

---

## 3. Visuals — a five-tier ladder, stock last

Priority order, enforced by the decision engine:

1. **Subject-specific** — the exact thing named. Real footage, or an AI recreation
   of *that subject* when no camera could have been there.
2. **Motion graphics** — the claim itself, built on screen in the channel's type
   over a live branded field. For beats whose content *is* the words.
3. **Animated charts** — every important number.
4. **Branded graphics** — a branded plate. The floor.
5. **Stock footage** — a rescue, not a default.

### Every number gets a real chart

`Scene.data` carries the actual values and the chart renders from them, in the
channel's palette, with the source attribution burned in beside it.

Six forms: `counter` · `bar_compare` · `line_trend` · `delta` · `donut` · `meter`.

Two rules make this trustworthy:

- **Authored data is never capped.** If the Director said this beat is about these
  numbers, dropping the chart and substituting footage is the exact failure being
  fixed.
- **A chart is never invented.** `dataviz.render()` refuses to draw without real
  values. The previous Manim path shipped hard-coded placeholder numbers
  (`[2.1, 2.4, 2.9, 3.1, 3.4]`, regardless of topic) — a confident-looking graph
  of figures nobody asserted. That path is gone.

Axes anchor at zero for positive series, because a truncated y-axis makes a 2%
move look like a cliff, and that is a misleading graphic on a finance channel.

Rendering is numpy + ffmpeg — no Manim, no LaTeX, no network, no GPU.

*Code:* `apps/api/app/pipeline/{dataviz,motiongfx,scene_director,broll}.py`

---

## 4. Brand package

`config/brand/k70.yaml` is the single source of truth for the finance-documentary
look: palette, font system, watermark, lower thirds, intro stamp, end card,
caption styling, chart colours and four colour-grade variants.

Assets are **generated** from the theme, not checked in, and cached by a hash of
the config — so editing the palette re-skins every future render with no asset
wrangling and no stale files.

Fonts resolve through a preference list with fallbacks, and the resolver
specifically rejects **variable font files** for bold weights: ffmpeg and libass
both render a variable font's default instance, so asking for Bold silently gets
Regular. Run `scripts/fetch_brand_fonts.sh` to install the intended faces (all
SIL OFL, commercially free).

*Code:* `apps/api/app/brand/`

---

## 5. Monetisation safety

`config/compliance.yaml` — 40 rewrite rules, 5 blocking flags, 4 advisories.

- **Automatic rewrites** for the named phrases (`guaranteed`, `risk-free`,
  `get rich`, `best stock to buy`, `buy now`, `easy money`) and ~30 relatives.
  Every substitution is recorded on the graph — a compliance layer that edits
  silently is one you stop trusting.
- **Escalation, not patching.** First-person recommendations and price targets
  can't be machine-rewritten without changing meaning, so they fail the gate and
  go back through the Director's repair loop. A line needing three or more
  substitutions is escalated wholesale, because patching a promotional sentence
  phrase-by-phrase produces something that sounds wrong *when spoken*.
- **Grammar repair.** Substitutions fix article agreement (`a alleged` → `an
  alleged`) and can't re-fire on their own output.
- **Disclaimer** burned in twice (an early band, and full-width on the end card)
  and placed on the **first line** of the description — above the fold, where a
  reviewer reading two lines will actually see it.

The gate runs **inside** the Director's repair loop, so risky wording is rewritten
by the model that wrote it, with a non-strict backstop pass before rendering.

*Code:* `apps/api/app/pipeline/compliance.py`

---

## 6. AI disclosure

The pipeline cannot tick YouTube's *Altered or Synthetic Content* box for you — it
is a per-upload declaration in Studio. So it detects when you need to and makes
the reminder impossible to miss: console output at the end of the render, plus
`requires_ai_disclosure` and the reasons in `metadata.json`.

The test is **not** "did we use AI". Charts, plates and stylised backgrounds never
require disclosure. It fires when a beat resolved to a *generated* visual **and**
depicts a realistic person or real event, or was prompted for photorealism.

---

## 7. Audio

Five bed families × three variants = **15 beds**, synthesised with ffmpeg (no
licensing exposure, no Content ID risk). The family comes from the story
structure's preference; the variant rotates with a cooldown across all 15, so
consecutive uploads cannot share a bed.

The intensity envelope now follows the structure's **beat roles** — a `reveal`
swells wherever it falls, rather than only when a scene happens to have a stat
overlay.

*Code:* `apps/api/app/pipeline/music.py`

---

## 8. Visual variety

Every dimension that could ossify into a signature is planned per video and
rotated against channel history: scene count, transition palette, camera motion,
zoom travel, caption animation, colour grade, CTA shape, music family.

Deterministic (seeded off the video id, so renders are reproducible) and
anti-repeat (weighted against the ledger, so options take turns).

Bounded by taste: transitions still favour the documentary hard cut, motion stays
slow, and nothing here can produce a short that looks like a different channel.

*Code:* `apps/api/app/pipeline/variety.py`, `apps/api/app/state.py`

---

## Bug fixed along the way

`drawtext` silently rendered **nothing** for any text containing a `%`. The old
escaping added `\%`, which blanks the entire draw while ffmpeg still reports
success — so every headline or stat overlay with a percentage was invisible. The
fix is `expansion=none` plus a much narrower escape set, established by rendering
test strings and looking at the output rather than trusting exit codes.

*Code:* `apps/api/app/brand/text.py`

---

## Test coverage

104 new tests in `apps/api/tests/pipeline/`:

```bash
cd apps/api && ../../.venv/bin/python -m pytest tests/pipeline -q
```

They assert distribution properties (a structure library that doesn't repeat
across 20 uploads), refusals (no chart without data, no synthesis without the
cloned voice), and the things that must *not* happen (generic keywords never
counting as a subject, charts never triggering an AI disclosure).
