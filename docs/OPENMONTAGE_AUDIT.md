# OpenMontage audit — long-form documentary upgrade path

Research-only deliverable. **No production code was changed to produce this
document.** Every "current state" claim is sourced from a direct code audit
(file:line) of Shorts Factory as it exists on this branch today; every
OpenMontage claim is sourced from a direct read of its source at
`github.com/calesthio/OpenMontage` (commit as of 2026-08-03, the last push
before this audit). OpenMontage is treated strictly as a reference/benchmark
implementation — nothing here proposes migrating to it, and no OpenMontage
code has been copied into this repo.

**Scope discipline, repeated up front because it matters for every verdict
below:** SceneGraph, the D-AI Director, Paper Craft/Scribus, Three.js, Motion
Graphics, Charts/Maps, TTS, the FFmpeg pipeline, and the existing cache system
are the core engine and are not being replaced by anything in this document.
Everything recommended below is either a **new module that sits beside them**
(checkpointing, CLIP retrieval, pre-render QA) or a **generalization of logic
that already exists and already proved itself** (Episode 1's spec-level QA).

---

## 0. License — read this before anything else in this document

**OpenMontage is AGPL-3.0.** Confirmed via the GitHub API license field and
the `LICENSE` file header, not the README badge alone.

AGPL-3.0 §13 ("Remote Network Interaction") is the operative clause: if a
modified version of an AGPL work is used to interact with users **remotely
over a network**, the operator must offer those users the Corresponding
Source of the running modified version — this is stricter than plain GPL,
which only triggers on *distribution*. Shorts Factory's API/worker path
(`apps/api`, `arq` queue, `workers/tasks.py`) is exactly this shape: a
network-reachable service.

**Practical consequence:** copying or adapting any OpenMontage source file
verbatim into Shorts Factory would put the combined work under AGPL
obligations the moment it's served over the API — not just if it's
redistributed. This is true even for a single file, even with modifications.

**What this audit therefore recommends, without exception:** study
OpenMontage's *architecture and algorithms* (schema shapes, retrieval
strategy, gate sequencing — none of which are copyrightable), then
**clean-room reimplement** anything worth having, in Shorts Factory's own
code style, importing only permissively-licensed third-party libraries
(e.g. `open_clip_torch`/`transformers`, MIT/Apache) directly. **Zero
OpenMontage source files are to be copied, transcribed, or translated
line-by-line.** Every verdict below assumes this constraint; nothing is
marked KEEP because KEEP would mean "use OpenMontage's code as-is," which
is off the table for AGPL regardless of merit.

---

## 1. What OpenMontage actually is (verified, not assumed)

- **45.8k GitHub stars, created 2026-03-29, most recent push 2026-08-03.**
  Real, active, not vaporware.
- It is an **agent-driven** system: 12 pipeline definitions (YAML manifests),
  each broken into stages, each stage backed by a "skill" markdown file that
  instructs an LLM coding assistant (Claude Code, Cursor, etc.) how to
  execute that stage, call tools, and self-review. **There is no standalone
  batch executable equivalent to `scripts/produce.py`.** The human-approval
  gates, "END YOUR TURN" protocol, and Backlot board all assume a
  conversational agent is driving the pipeline turn-by-turn. This is a
  fundamentally different execution model from Shorts Factory's unattended
  CLI run, and it matters for every recommendation below — the *data
  structures* (checkpoint schema, review schema) port cleanly; the
  *interaction protocol* (present-to-human, end-turn, wait-for-approval)
  does not, because Shorts Factory has no human in the loop during a run.
- **The `documentary-montage` pipeline is short-form, not long-form.** Its
  own worked examples are "A Minute in the Rain" (45s–3min pieces); its
  `max_wall_time_minutes: 60` budget is a *wall-clock ceiling for the whole
  agentic session*, not a target video duration. Grepping every skill file
  and pipeline manifest in the repo for `chapter|act|long-form|duration_minutes`
  turns up nothing beyond that one wall-time field and a "3-minute piece"
  aside. **OpenMontage has no dedicated long-form/chaptered pipeline at all**
  — it ships 12 pipelines (`clip-factory`, `talking-head`, `cinematic`,
  `animated-explainer`, etc.) and all of them are shorts/single-piece
  oriented. This is the single most important finding of this audit for
  category 1 below.
- Four things it does have that are genuinely more developed than the
  equivalent in Shorts Factory: **CLIP-embedding semantic retrieval over a
  built stock/archival corpus**, **explicit stage-checkpoint files with a
  resume protocol**, **a "final_review" post-render self-check schema with a
  "promise preservation" concept** (did the render actually deliver what was
  planned, or did something silently downgrade), and **per-provider stock
  adapters with normalized license/attribution metadata**.

---

## 2. Category-by-category audit

### 2.1 Long-form documentary planning

**OpenMontage — how it works.** `pipeline_defs/documentary-montage.yaml`
defines 5 checkpointed stages (`idea → scene_plan → assets → edit →
compose`), each with a `skill` file that tells the agent what to produce,
a `review_focus` checklist, and machine-checkable `success_criteria` (e.g.
"Sum of target_hold_seconds within 10% of brief.duration_seconds"). Every
stage's artifact is schema-validated (`schemas/artifacts/*.schema.json`)
before the next stage may start (`_enforce_stage_prerequisites` in
`lib/checkpoint.py`). There is no chaptering concept — a "scene_plan" is one
flat list of slots for the whole (short) piece.

**Shorts Factory — what's actually there.** Verified against the real
Bitcoin Episode 1 artifacts, not a synthetic example:
- `data/series/bitcoin_history/ep01/scene_graph.json`: **156 scenes, 10
  chapters, 14.27 min at measured TTS speed** — i.e. Shorts Factory has
  *already* produced content at the low end of the user's 40–60 min target
  range (12–14 min), hand-planned rather than Director-generated end-to-end.
- `data/series/bitcoin_history/ep01/qa_report.md`: **26 spec-level checks,
  26/26 PASS**, covering structure (scene-id contiguity, beat-duration
  bounds), visual coverage (156/156 beats have a visual plan, 136 distinct
  visuals — zero repeats), sourcing (every chart attributed, speculative
  beats hedged, no unconfirmed absolutes), and **story craft that
  OpenMontage's schema has no equivalent for at all**: twist/reveal cadence
  (59 turns, longest gap 34s, median 14s, checked against a 20–40s rule),
  every chapter ending on a cliffhanger beat, and a running count of
  synthetic/AI-recreated beats for **YouTube's "Altered or Synthetic
  Content" disclosure requirement** — a real regulatory concern for
  documentary content that OpenMontage's schemas never mention.
- The catch: **this 26-check QA report is bespoke.** It was produced by
  `scripts/build_bitcoin_ep01.py`, a one-off authoring script written for
  this specific episode — not a reusable pipeline stage. There is no
  `pre_render_qa.py` module any new long-form job runs through
  automatically. Chapters exist only as headings in the human-readable
  `production_plan.md`; the `SceneGraph` pydantic schema
  (`apps/api/app/schemas/scene.py`) has **no chapter/act field** — it's a
  flat `scenes: list[Scene]`, identical in shape whether the graph holds 9
  scenes (the Bitcoin demo) or 156.
- `Scene.duration_sec` is bounded `0.8–12.0s` per scene — fine at 156 scenes,
  but nothing in the schema or the Director enforces chapter-level pacing
  budgets (e.g. "chapter 3 must land 6:30–7:30 into the runtime") the way
  `structures.py`'s `Structure`/`Beat` classes enforce beat-role sequencing
  for a single short.
- `apps/api/app/director/structures.py` (`Structure`, `Beat`,
  `StructureChoice`, `choose()`) is a real, working beat-sequencing engine —
  but it operates over one flat beat list, with no concept of grouping beats
  into chapters that each get their own act-level arc.

**Verdict: mostly REIMPLEMENT, small ADAPT.**
- **REIMPLEMENT** (no OpenMontage equivalent exists to adapt from): add a
  `Chapter`/`Act` grouping layer on top of `SceneGraph` — an ordered list of
  chapters, each owning a contiguous slice of `scenes`, each with a target
  duration band and a required ending beat-role (turn/reveal/cliffhanger),
  mirroring what `production_plan.md` already describes by hand for Episode
  1. `structures.py` extends naturally: a `Structure` becomes assignable
  per-chapter instead of once per video.
- **ADAPT** (generalize what already works, informed by *how* OpenMontage
  structures its stage manifest — declarative YAML with `review_focus` +
  `success_criteria` per stage — without adopting its human-in-the-loop
  execution model): turn `build_bitcoin_ep01.py`'s 26 checks into a reusable
  `pipeline/spec_qa.py` that any long-form `SceneGraph` runs through before
  render, parameterized the way OpenMontage parameterizes `success_criteria`
  per stage in YAML rather than hard-coded per-episode.
- **SKIP**: OpenMontage's `idea`/`scene_plan` agent-facing skill markdown
  files — they're prompts for a conversational agent, not planning logic;
  Shorts Factory's Director (`apps/api/app/director/`) already fills this
  role in a batch-compatible way.

### 2.2 Archival/stock footage retrieval and semantic ranking

**OpenMontage — how it works.** Two tiers, and OpenMontage's own docs are
explicit about when to use which:
- **`direct_clip_search`** (`tools/video/direct_clip_search.py`): fan out
  across `StockSource` adapters (Pexels, Archive.org, NASA, ESA, JAXA, NOAA,
  NARA, Library of Congress, Wikimedia, Unsplash, Mixkit, Videvo, Coverr,
  Dareful, Pond5-PD, Pixabay), download top-N per query, extract a thumbnail,
  no ranking beyond each provider's own relevance order. **This is
  functionally identical to what `broll.py` already does** — keyword query
  in, first hit out, per provider, in priority order.
- **`corpus_builder` → `clip_search`** (`lib/clip_embedder.py`,
  `tools/video/clip_search.py`): every candidate frame gets embedded with
  CLIP ViT-B/32 (`openai/clip-vit-base-patch32` via `transformers`+`torch`,
  ~150–300ms/image on CPU), L2-normalized, stored in a local corpus. At
  retrieval time, a text slot description (`"a hand slides a punch card into
  a machine, 1960s office"`) is embedded the same way and ranked against the
  corpus by a **fused visual+tag cosine score** (`tag_weight` blends visual
  similarity with keyword/tag-text similarity, default 0.3). Two more
  operations sit on top: `find_similar_set` (MMR — maximal marginal
  relevance — for "collection" shots that should share a register but not
  repeat each other) and `diversify` (greedily keep the most
  mutually-dissimilar subset of a pre-selected list). OpenMontage's own
  guidance: use the CLIP path specifically "when you have 50+ slots" — i.e.
  exactly the long-form case, not the short-form case where `direct_clip_search`
  is preferred for speed.
- Every `Candidate`/`ClipRecord` carries `creator`, `license`,
  `source_url`, `source_tags` — normalized provenance regardless of which
  of the 16 provider adapters it came from.

**Shorts Factory — what's actually there** (verified in `broll.py`, not
recalled): `_search_terms()` builds an ordered keyword list (exact Director
terms → generic filler → supporting filler), `_first_hit()` tries each term
against Pexels then Pixabay and **returns the first non-empty result** —
no scoring, no ranking, no embeddings, no cross-provider fusion. Dedup
(`_dedupe_real_assets`) only catches **exact same file reused twice**; it
re-picks by index offset, not by visual similarity, so two *different* stock
clips that look nearly identical (a real, common problem across stock
libraries — "server room with blinking lights," multiplied) sail straight
through. Provenance tracking is real and already good —
`graph.asset_provenance` / `motion_graphics_provenance` /
`ai_broll_provenance` fields exist and are tested
(`tests/pipeline/test_multi_source_assets.py`) — this part does **not**
need to change.

At 9–30 beats (a Short), keyword-first-hit rarely gets noticed. At **156
beats across 10 chapters** (Episode 1's actual scale, already proven-out),
visual repetition and mismatch become far more visible to a viewer watching
continuously for 12+ minutes — exactly the risk the user flagged.

**Verdict: REIMPLEMENT the capability, clean-room (never copy OpenMontage's
files — AGPL, see §0).**
- **REIMPLEMENT**: a `pipeline/clip_corpus.py` using CLIP embeddings
  (`open_clip_torch` or `transformers`, both permissive) for: (a) fused
  visual+tag ranking against candidates already being fetched from Pexels/
  Pixabay (no new provider integrations needed — this augments ranking, not
  sourcing), (b) MMR-based diversification so visually-similar-but-distinct
  clips get spread out across the runtime instead of clustering, (c) a real
  semantic dedup pass that supersedes `_dedupe_real_assets`'s exact-file-only
  check. The `Candidate`/fused-score *shape* is worth mirroring (it's a
  sensible data model, not a copyrightable expression) — the code is not.
- **KEEP**: the existing `broll.py` provider-fetch layer (Pexels/Pixabay
  calls, download, provenance fields) — CLIP ranking slots in *after*
  candidates are fetched, it doesn't replace how they're fetched.
- **SKIP**: adding the other 14 OpenMontage stock providers (Archive.org,
  NASA, LOC, Wikimedia, etc.) is tempting for "archival" content
  specifically, but it's a separate, genuinely valuable idea worth its own
  decision later — bundling it into this benchmark would conflate two
  independent variables (ranking quality vs. source breadth). Flagged, not
  recommended here.

### 2.3 Resumable/checkpointed production

**OpenMontage — how it works.** `lib/checkpoint.py` (634 lines, real and
load-bearing, not a stub): `write_checkpoint()`/`read_checkpoint()` per
stage, `get_next_stage()` walks completed checkpoints to find where to
resume, `_enforce_stage_prerequisites()` hard-blocks advancing a stage
whose predecessor isn't `completed` (and, if gated, `human_approved`), and
`_archive_superseded_checkpoint()` preserves every prior version in
`history/` before overwriting. Crucially, stages that run long
(`assets`, `compose`) are instructed (`skills/meta/checkpoint-protocol.md`
Step 4) to write **intra-stage `in_progress` checkpoints** after each
significant unit of work (one scene's assets, one clip), storing partial
progress under `metadata.partial_progress` with a `completed_scene_ids`
list — so a crash mid-stage resumes from item N, not from the top of the
stage. Atomic writes (`tmp` + `os.replace`) avoid truncated-checkpoint
corruption on a mid-write crash.

**Shorts Factory — what's actually there** (this needed real digging —
the answer is more nuanced than "nothing exists"):
- There **is** a generic checkpoint primitive:
  `production_optimizer.py`'s `CheckpointStore` (content-hash-verified
  `valid()`, atomic `save()`) and a `resumable_stage()` wrapper built on top
  of it. **`resumable_stage()` — the actual skip-if-already-done wrapper —
  is never called anywhere in the codebase.** `CheckpointStore` itself is
  used in exactly one place: `apps/api/app/workers/tasks.py` (the ARQ
  job-queue path), where it **records** 5 coarse checkpoints
  (`pipeline`/`assets`/`finalization`/`qa`) for observability — but nothing
  reads them back to skip work on retry. It's write-only telemetry today,
  not resumability.
- **`scripts/produce.py` — the actual path used for every real render in
  this repo, including every session's Bitcoin Episode work — instantiates
  no checkpoint object at all.** Its resumability is entirely *implicit*,
  via content-addressed caching at each stage: TTS narration cache
  (`data/cache/narration`), `asset_manifest.json` (intent-keyed), a frozen
  `variety.json`, and the scene-clip `manifest.json`
  (fingerprint+sha256+ffprobe-validated). Re-running the identical
  `produce.py` command is genuinely cheap because each stage's own cache
  lookup skips redone work — this is a real, elegant pattern and should
  **not** be torn out.
- The gap is visible in the repo's own scratch tooling:
  `scripts/_resume_btc_ep01.sh` (written during actual production of
  Episode 1, not hypothetically) says outright in its own comment: *"the
  previous run's log stopped mid-stage and could not be read for a resume
  point."* There is no file that says "render was on scene 91/156 in the
  `render` stage when it died" — only a log tail to reconstruct that by eye.
  For a 12-minute episode this is a minor annoyance; for a 40–60 minute
  film with proportionally more scenes and (per the RENDER_TIMEOUT scaling
  already added to `produce.py` this session) proportionally longer render
  wall-time, an unattended crash 90% through a render with no structured
  "where did it die" record is a real cost.

**Verdict: ADAPT the schema and resume logic; do not adopt the
human-approval-gate protocol** (no agent is present during a
`scripts/produce.py` run to answer a gate).
- **ADAPT**: wire the *existing, already-written* `resumable_stage()` +
  `CheckpointStore` into `scripts/produce.py`'s actual stage sequence
  (research/script → grounding → TTS → captions → assets → render → QA),
  finally putting the dead code to use — this alone closes most of the gap
  with zero new architecture. Borrow OpenMontage's two concrete refinements
  on top: (1) intra-stage partial-progress checkpointing for the long
  `assets`/`render` stages specifically (write progress every N beats, not
  just at stage boundaries — directly answers the `_resume_btc_ep01.sh`
  pain point), (2) archive superseded checkpoints to `history/` instead of
  overwriting, cheap insurance for a run that gets manually restarted mid-way.
- **KEEP unconditionally**: the content-addressed per-stage caches
  (narration, asset_manifest, variety, scene-clip manifest) — these are
  Shorts Factory's actual resumability engine today and are, if anything,
  more automatic than OpenMontage's explicit-checkpoint model (no agent has
  to remember to call `write_checkpoint`). Stage checkpoints should sit
  *on top of* this caching, recording "which stage got how far," not
  replace it.
- **SKIP**: `human_approval_default` gates, "END YOUR TURN" protocol, the
  Backlot board — all assume an interactive agent driving the run.
  `scripts/produce.py` is a batch job; the equivalent oversight point for
  Shorts Factory is the existing pattern already used for Episode 1 — a
  human reviews `production_plan.md`/`qa_report.md` **before** the spec
  is handed to `produce.py`, not mid-render.

### 2.4 Pre-render and post-render quality review

**OpenMontage — how it works.** Two distinct schemas:
- **Post-render only**: `schemas/artifacts/final_review.schema.json`. A
  structured self-check the `compose` stage must produce before presenting
  output: `technical_probe` (ffprobe), `visual_spotcheck` (sampled frames,
  black-frame/broken-overlay/missing-asset/unreadable-text flags),
  `audio_spotcheck` (narration/music present, clipping, unexpected silence),
  `subtitle_check` (coverage ratio, timing drift), and — the one genuinely
  novel piece — **`promise_preservation`**: did the render actually use the
  renderer/runtime locked at planning time, is there a `runtime_swap_detected`
  flag, a `motion_ratio_actual` vs. planned, a `silent_downgrade_detected`
  flag. `tools/analysis/visual_qa.py` is the mechanical half of this — it
  extracts frames and runs `ffprobe`, but it does *not* itself decide
  pass/fail on visual quality; an agent looks at the extracted frames and
  fills in the schema. There's no equivalent to OpenMontage's `source_media_review`
  in scope here (that's for reviewing *user-uploaded* footage before
  planning — not applicable, Shorts Factory doesn't ingest user source video).
- OpenMontage has **no pre-render spec/story QA schema at all** — its
  closest equivalent is the `review_focus`/`success_criteria` lists baked
  into each pipeline-manifest stage, checked by an agent against the
  artifact, not by a script.

**Shorts Factory — what's actually there:**
- **Post-render**: `pipeline/qa.py`'s `analyze()`/`production_analyze()` —
  10 real, scripted, automatically-enforced gates confirmed running on
  every `produce.py` render this session (render-completed, playable-file,
  has-video-stream, has-audio-stream, resolution match, duration match,
  black-frame fraction ≤6%, every-scene-lit, RAM-peak-within-budget,
  wall-time-within-budget). This is **more automated** than OpenMontage's
  post-render check — OpenMontage's `visual_spotcheck`/`audio_spotcheck`
  booleans are filled in by an agent looking at extracted frames, not by a
  script computing them. **What Shorts Factory's `qa.py` does not have,
  confirmed by grep, zero hits for `silent|downgrade|planned.*deliver`:**
  any check that the delivered visual mix matches the planned one. This is
  a real, already-observed gap, not speculative — this session's own demo
  render log printed exactly this condition as an unenforced note: *"s11:
  planned threejs → delivered motion_gfx (resolver could not supply the
  planned source)"* — the data needed for the check already exists in the
  visual-budget report; nothing currently turns it into a pass/fail gate.
- **Pre-render**: exists, and is arguably **richer than OpenMontage's**
  equivalent in the dimensions that matter most for documentary craft —
  Episode 1's 26-check `qa_report.md` (§2.1) checks twist cadence, chapter
  cliffhangers, chart attribution, hedged-speculation language, and AI-
  disclosure-threshold counting — none of which OpenMontage's schemas
  attempt. The catch, as in §2.1, is that this check set is bespoke to one
  authoring script, not a reusable gate.

**Verdict: ADAPT on both ends.**
- **ADAPT (pre-render)**: generalize `build_bitcoin_ep01.py`'s 26 checks
  into `pipeline/spec_qa.py`, run automatically by `produce.py` before
  render for any long-form job (short jobs keep today's lighter implicit
  checks — no regression risk to the existing Shorts path). This is
  Shorts Factory's own logic, proven on real output; OpenMontage informs the
  *shape* (a manifest-declared checklist with pass/fail criteria) more than
  the content.
- **ADAPT (post-render)**: add exactly one new gate to `qa.py`, informed by
  OpenMontage's `promise_preservation` concept but built from data Shorts
  Factory already computes: compare `graph`'s planned visual-channel
  allocation (already logged, see the "delivered visual breakdown" block
  every render already prints) against what actually rendered, and fail (or
  at minimum warn loudly) on an unflagged silent downgrade. This is a small,
  surgical addition, not a new subsystem.
- **KEEP**: the 10 existing technical gates in `qa.py` — no OpenMontage
  equivalent is stronger here.
- **SKIP**: `source_media_review` (no user-uploaded footage in this
  pipeline's model) and the agent-filled `visual_spotcheck`/`audio_spotcheck`
  booleans (Shorts Factory's scripted checks are already more automated and
  more reliable than an agent eyeballing extracted frames for the same
  properties `qa.py` already computes numerically).

---

## 3. Summary verdict table

| Capability | OpenMontage has it? | Shorts Factory has it? | Verdict | Why |
|---|---|---|---|---|
| Chaptered long-form spec (SceneGraph extension) | No (short-form only) | No (flat scene list; chapters are prose-only in `production_plan.md`) | **REIMPLEMENT** | No equivalent to adapt from either side; this is new work informed by Episode 1's own hand-built structure |
| Declarative per-stage success criteria | Yes (YAML manifest) | No (ad hoc per script) | **ADAPT** (pattern only) | Worth the shape, not the agent-facing prose |
| CLIP semantic clip retrieval + MMR diversify | Yes, real & working | No (keyword-first-hit only) | **REIMPLEMENT** (clean-room) | Concrete, proven gap at 150+ beat scale; AGPL forbids copying OpenMontage's implementation |
| Stock-provider adapters + provenance | Yes, 16 providers | Yes (Pexels/Pixabay), provenance already tracked & tested | **KEEP** current sourcing layer | Ranking is the gap, not sourcing |
| Explicit stage checkpoints | Yes, wired & used | Written but dead code (`resumable_stage` unused); `produce.py` uses none | **ADAPT** | Wire up what already exists; add intra-stage partial progress |
| Content-addressed stage caching | No real equivalent | Yes, and it works | **KEEP** | Already Shorts Factory's actual resumability engine |
| Human-approval gate protocol | Yes (agentic, turn-based) | N/A (batch CLI) | **SKIP** | Wrong execution model for `produce.py` |
| Post-render technical QA gates | Partial (agent-filled booleans) | Yes, 10 scripted gates | **KEEP** | Already more automated than OpenMontage's |
| Post-render "promise preservation" / silent-downgrade detection | Yes | No (confirmed, grep-verified) | **ADAPT** | One surgical gate addition using data already logged |
| Pre-render story/spec QA (cadence, sourcing, chapters) | No equivalent | Yes, but bespoke to one script | **ADAPT** | Generalize proven logic, don't import OpenMontage's (weaker) equivalent |
| Source-media (user-uploaded footage) review | Yes | N/A (not this pipeline's input model) | **SKIP** | No matching use case |

---

## 4. Hybrid architecture

Shorts Factory's engine is unchanged. Four new/adapted modules sit around it:

```
                          ┌─────────────────────────────────────────┐
                          │   scripts/produce.py  (orchestrator)     │
                          └───────────────┬───────────────────────────┘
                                          │
        ┌─────────────────────┬──────────┼──────────────┬───────────────────┐
        ▼                     ▼          ▼               ▼                   ▼
 SceneGraph + NEW      pipeline/       D-AI Director   pipeline/broll.py  pipeline/qa.py
 Chapter/Act layer      spec_qa.py     (unchanged)      + NEW               (existing 10
 (schemas/scene.py)     [NEW —         core            pipeline/           gates, unchanged)
 REIMPLEMENT            pre-render,                     clip_corpus.py       + NEW
                         ADAPTED from                    [NEW — REIMPLEMENT   promise_preservation
                         build_bitcoin_                  clean-room, CLIP     gate [ADAPT]
                         ep01.py]                         ranking + MMR]
        │                     │                          │
        │                     │                          ▼
        │                     │                   pipeline/render_ffmpeg.py
        │                     │                   Paper Craft / Scribus / Three.js /
        │                     │                   Motion Graphics / Charts / TTS
        │                     │                   (ALL UNCHANGED — core engine)
        ▼                     ▼
 production_optimizer.py  CheckpointStore
 [ADAPT — wire up the      + intra-stage partial
  existing but unused       progress writes
  resumable_stage()]        [ADAPT]
```

Flow for a 40–60 min job:
1. Director (unchanged) or hand-authoring produces a `SceneGraph` with the
   new chapter layer.
2. `spec_qa.py` runs the generalized 26-ish-check pre-render gate. Fails
   loudly before a single frame renders — same principle Episode 1 already
   proved, now enforced automatically instead of by a one-off script.
3. `produce.py`'s stage loop is wrapped in the now-actually-used
   `resumable_stage()`; each stage writes a `CheckpointStore` record,
   `assets`/`render` additionally write partial progress every N scenes.
   A crashed 45-minute-in run resumes from scene N, not from scratch.
4. `broll.py` fetches candidates exactly as it does today; `clip_corpus.py`
   re-ranks and diversifies them before they're written to
   `scene.visual.asset_path` — a ranking layer, not a new sourcing layer.
5. Render proceeds through the entirely unchanged core engine.
6. `qa.py` runs its existing 10 gates plus the new promise-preservation
   check, comparing planned vs. delivered visual mix.

Nothing here touches `SceneGraph`'s core fields, the Director's decision
logic, Paper Craft/Scribus, Three.js, Motion Graphics, Charts/Maps, TTS, the
FFmpeg render path, or the content-addressed caches. All four new pieces are
additive and individually revertible.

---

## 5. Proposed benchmark

**Subject:** one real 10–15 minute documentary episode — Bitcoin History
Episode 1 (`data/series/bitcoin_history/ep01/scene_graph.json`, 156 scenes,
10 chapters, already-authored and QA-passed) is the natural choice: it's
real content, already at the low end of the target range, and running it
through Path A first establishes a genuine baseline rather than a synthetic
one.

**A. Current Shorts Factory** — `scripts/produce.py --preset
documentary_series --from-json .../ep01/scene_graph.json`, unmodified,
exactly as it runs today.

**B. Shorts Factory + approved upgrades** — same spec, same preset, run
through the four ADAPT/REIMPLEMENT modules from §4 once each is built and
merged (not before — this benchmark happens *after* implementation, as a
separate follow-up task; this document is the pre-implementation comparison
report the user asked for, not the benchmark itself).

**Measurements, and how each is actually captured (not hypothetical —
these are real fields/logs this session already confirmed exist):**

| Metric | Source |
|---|---|
| Asset quality | Manual spot-check of N sampled beats' resolved footage against slot intent, scored 1–5, both runs blind-labeled |
| Visual diversity | Count of distinct `asset_path` values ÷ total visual beats (Episode 1's own QA already computes this: "136 distinct visuals" — reuse the same method) |
| Fallback rate | `graph_cache_report()`'s existing hit/miss namespaces (`production_optimizer.py`) plus the "resolver could not supply the planned source" note count from the visual-budget log |
| Render time | Wall-clock from `produce.py`'s own `stage()` timing prints, `render` stage specifically |
| RAM | `RamSampler.halt()` peak — already printed in every QA report today |
| Cache reuse | `[render] scene clips: N reused, M rendered` — already printed |
| Manual fixes | Count of human interventions required to reach a passing QA report, logged by hand during the run |
| QA failures | `qa.py` gate pass/fail count, both the existing 10 and (for Path B) the new promise-preservation gate |
| Final documentary quality | Same rubric used in this session's own visual-quality reviews (authenticity, readability, camera guidance, caption collisions, repetition, comparison to premium documentary editing standards), scored /10 across the same 7 dimensions already used for the Bitcoin Paper Craft demo — for continuity with prior verified work in this repo |

Both runs on the same machine, same episode, same preset, back-to-back, to
control for environment drift.

---

## 6. What this audit is explicitly not recommending

- Not adopting OpenMontage's other 15 stock providers (Archive.org, NASA,
  LOC, etc.) — real value for archival-specific content, but a separate
  decision from retrieval *ranking quality*, which is what was in scope here.
- Not adopting the agentic/human-approval-gate execution model — Shorts
  Factory's batch `produce.py` and OpenMontage's turn-based agent loop solve
  different problems; forcing one onto the other would be a net regression
  for unattended production runs.
- Not touching `source_media_review` — no matching input model in this
  pipeline.
- Not copying, transcribing, or otherwise deriving code text from
  OpenMontage's AGPL-3.0-licensed repository, per §0.

*Ready for review. No implementation begins until this report is approved.*
