# OSS integration research — what to adopt, what to skip, and why

Research-only deliverable. No code changed as part of this document. Every
"current state" claim below is sourced from a direct code audit (file:line);
every OSS claim is sourced from the project's own docs/license file or a
2026 web search. Where I'm inferring rather than citing, I say so.

**Bottom line up front:** this pipeline is far less "reinventing the wheel"
than the request assumed. Two of the eight requested categories (3D, and
motion-graphics-adjacent video compositing) are **already real integrations**
of exactly the tools on the list — Three.js and Remotion are both genuinely
wired in, not aspirational names. The actual gap is narrower than it looks:
**diagrams** (zero capability today) and **font-metrics-aware text wrapping**
(a heuristic today, by the code's own admission) are the two places an
external library would fix something real. Most of the rest of the request
— Excalidraw, Penpot, Inkscape, Scribus, D3, Chart.js, Shotcut, Olive — don't
have a capability gap to fill, and several are GUI applications with no
headless story that fits an automated CLI pipeline at all.

---

## 1. Current state (from a full code audit)

| Area | What's actually there | Real library, or hand-rolled? |
|---|---|---|
| Charts | 6 kinds (`counter`, `bar_compare`, `line_trend`, `delta`, `donut`, `meter`) | **Hand-rolled** — numpy SDF rasterizer + ffmpeg `drawtext`. `apps/api/app/pipeline/dataviz.py` |
| Motion graphics / kinetic type | 5 background "treatments", headline/kicker/source overlay | **Hand-rolled** — same numpy+drawtext mechanism. `pipeline/motiongfx.py` |
| 2D vector primitives | rect/circle/ring/segment/polyline/gradient, alpha compositing | **Hand-rolled** — signed-distance-field rasterizer in raw numpy, *no Pillow, no cairo*. `brand/raster.py` |
| Text layout / wrap | character-count lookup table (`_CHAR_BUDGET`) | **Heuristic**, explicitly not glyph-metric-based (`brand/text.py:10-12`, its own docstring admits this) |
| 3D | 7 templates (bar towers, share/ownership, cashflow, timeline flythrough, compound growth, globe flight) | **Real integration** — Puppeteer drives headless Chromium (SwiftShader software WebGL) running the actual `three` npm package. `pipeline/threejs_engine.py` + `apps/remotion/src/threejs/worker.ts` |
| Video compositing / captions / ducking | Full React composition: transitions, Ken Burns, word-level captions, audio ducking | **Real integration** — Remotion, `apps/remotion/src/compositions/Short.tsx`. Reachable from the API/worker path (`pipeline/render.py`) but **not** from the `scripts/produce.py` CLI path this session used, which calls `render_ffmpeg.py` directly and never touches Node |
| Diagrams (flowchart/org-chart/graph) | **none** | Zero hits for mermaid/plantuml/graphviz/dot anywhere in the pipeline |
| Image processing | blur, resize, vignette, even a hand-written PNG encoder | **Hand-rolled** — `pipeline/ambience/imaging.py`, explicitly built because "Pillow is not in the venv" |
| Video/audio encode | ffmpeg CLI, always | Correct as-is; even Remotion's output gets finished through ffmpeg |
| Fonts | filesystem paths resolved per-platform (this session added the Windows fallback chain) | `@remotion/google-fonts` exists but only on the JS/Remotion side, unused by the numpy path |

Two things surfaced that aren't in the request but matter for it:

- **`manim_templates.py` is dead code.** `dataviz.py`'s own docstring says it's
  *"the replacement for a prior Manim-based chart path that shipped
  hard-coded placeholder data."* Manim was tried for exactly the chart use
  case the request asks about, and abandoned — worth knowing before
  recommending it again for the same job.
- **`numpy` is missing from `requirements.txt`** despite being load-bearing
  across the entire raster/dataviz/motiongfx/ambience stack. Unrelated to
  this research, but a real bug worth a one-line fix independent of anything
  else here.

---

## 2. Category-by-category verdicts

Legend: 🟢 **Adopt** — real gap, clean license, concrete path. 🟡 **Adapt the
idea, not the dependency** — the algorithm/format is worth having, the
runtime isn't. 🔴 **Skip** — no capability gap, or no headless story.

### Paper craft & document design

| Project | License | Verdict | Why |
|---|---|---|---|
| Excalidraw | MIT | 🔴 Skip (🟡 aesthetic only) | Headless CRUD works, but PNG/SVG export needs the frontend running in a browser — same cost as the Three.js integration for a much narrower payoff. If the actual goal is a "hand-drawn sketch" look, the underlying algorithm (rough.js-style perturbed strokes) is small enough to port as a new `Canvas` primitive in `raster.py` rather than standing up a second headless-browser subsystem. |
| Penpot | MPL-2.0 (self-hosted service, AGPL components) | 🔴 Skip | Full design tool; headless export also needs its own browser service. License is more complex to clear than the payoff justifies. |
| Inkscape | GPL-3.0 | 🔴 Skip | GPL CLI invocation via subprocess would be legally fine (same pattern as ffmpeg/PlantUML), but its value-add — interactive SVG editing — doesn't map onto beat-by-beat programmatic generation. |
| Scribus | GPL-2.0 | 🔴 Skip | Desktop publishing GUI; no relevance to short-form video at all. |

**None of these four have a capability gap to fill.** If "paper craft" means
torn-paper edges, aged textures, stop-motion cutout aesthetics for specific
beats, that's a raster-texture problem, solvable with a small curated
public-domain texture pack plus 1-2 new `Canvas` primitives (torn-edge SDF,
grain overlay) — architecturally identical to what `raster.py` already does,
not a new dependency.

### Motion graphics & diagrams

| Project | License | Verdict | Why |
|---|---|---|---|
| **Mermaid** | MIT | 🟢 **Adopt** | Fills the one real, total gap in the pipeline: there is no flowchart/timeline/sequence-diagram capability today. Official rendering needs headless Chromium — which this repo *already drives* for Three.js (`threejs_engine.py`'s Puppeteer pattern), and Playwright is already installed in this environment (confirmed present with cached browsers). A `diagram_engine.py` following the exact same worker-subprocess shape as `threejs_engine.py` is the lowest-risk way to add this. |
| PlantUML | GPL (tool only — generated output is *not* covered by the GPL) | 🔴 Skip | Redundant with Mermaid for documentary-relevant diagram types, and requires a JVM — a genuinely new heavy runtime this pipeline doesn't otherwise need. Mermaid covers the same ground with a lighter, already-proven-pattern dependency. |
| **Graphviz** | EPL-2.0 (changed from CPL-1.0 in March 2026 — permissive, business-friendly) | 🟢 Adopt (lower priority) | Genuinely complementary to Mermaid, not redundant: Graphviz's `dot`/`neato`/`fdp` layout engines do real automatic force-directed/hierarchical layout for arbitrary-complexity relationship graphs ("who bailed out whom"-style diagrams), which Mermaid's more opinionated layouts don't do well. Native Windows binary + a thin `graphviz` PyPI wrapper that shells out — same subprocess pattern as ffmpeg, no new architecture. |
| **Manim Community** | MIT | 🔴 Skip for charts/motion-gfx (🟡 niche exception) | Already tried and abandoned for exactly this job (see §1). The existing numpy+ffmpeg path is leaner and has tighter drawtext-sync than a general animation engine would give for free. Its actual strength — precise mathematical animation (equation morphs, geometric proofs) — is a real gap *only if* a math/science-explainer channel gets added later; if so, invoke it the same way `threejs_engine.py` invokes its Node worker: an isolated, optional subprocess, never a core dependency. |

### Charts & data visualization

| Project | License | Verdict | Why |
|---|---|---|---|
| D3 | ISC (permissive) | 🔴 Skip (🟡 algorithms only) | JS/DOM-native; needs a headless browser or Node+jsdom to run outside a page, which duplicates the Puppeteer machinery for zero new chart types the pipeline actually uses. If a genuinely new chart *kind* is ever needed (treemap, sunburst, sankey, force-graph — none of which the current 6 kinds cover), port the specific `d3-scale`/`d3-hierarchy` **algorithm** into the existing numpy `Canvas` system rather than adopting the D3 runtime. ISC license makes that clean. |
| Chart.js | MIT | 🔴 Skip | Same headless problem as D3, same "no missing chart type" conclusion. |
| Apache ECharts | Apache-2.0 | 🔴 Skip (best fallback if ever needed) | Worth knowing this is the most headless-friendly of the three: it has a genuine SVG server-side-rendering mode with **zero native dependencies** (confirmed — no node-canvas needed for SVG output). If a future chart type can't be reasonably hand-rolled, ECharts-SVG-SSR is the one to reach for over D3/Chart.js specifically because of this. Not needed today. |

**The current 6-kind numpy system is a good fit for this pipeline's actual
requirements** (small fixed vocabulary of chart types, frame-perfect
drawtext-synced animated counters, CPU-only, no browser) and shouldn't be
replaced. This is the one category where "hand-rolled" is arguably the
*right* call already, not technical debt.

### 3D & animation

| Project | License | Verdict | Why |
|---|---|---|---|
| Three.js | MIT | 🟢 Already integrated — two concrete follow-ups, not new adoption | (1) `globe_flight`'s code silently falls back to a 2D canvas projection instead of real WebGL, contradicting a comment claiming it "defaults to 3d" (`worker.ts:35-37` vs. the actual gate at `worker.ts:267-270`) — worth fixing as a bug independent of this research. (2) Software WebGL costs ~700ms/frame per the code's own comment; any *new* Three.js template should be budgeted against that, not assumed free. |
| **Remotion** | **Remotion License** — free only for individuals or for-profit orgs with ≤3 employees; 4+ employees requires a paid Company License ($25/seat/mo Creators, $0.01/render min $100/mo Automators, $500+/mo Enterprise) | ⚠️ **Decision needed, not a research verdict** | This is the one place licensing directly collides with "no paid services." Remotion is a real, fully-built integration (captions, ducking, Ken Burns, overlays — genuinely more capable than `render_ffmpeg.py` in places) sitting in the repo *unused* by the CLI path that actually shipped Episode 1. Two honest paths: (a) if this stays a solo/small operation, Remotion is legitimately free to use — worth wiring `produce.py` to use it, since it already exists and is more capable; (b) if this is being treated as licensing-constrained regardless of team size, `render_ffmpeg.py` should be treated as canonical going forward and Remotion either pruned or clearly marked experimental/unused, since half-built parallel renderers are a maintenance liability. **I'm flagging this rather than deciding it** — it's a business/team question, not a technical one. |

### Video & media processing

| Project | License | Verdict | Why |
|---|---|---|---|
| FFmpeg | LGPL/GPL (build-dependent) | ✅ Already correct, no change | Confirmed as the sole encode/mux backend, used correctly everywhere including finishing Remotion's output. |
| Shotcut | GPL-3.0 | 🔴 Skip | GUI desktop NLE. No documented headless scripting API — the underlying MLT framework (LGPL) *could* theoretically be scripted directly, but that's "adopt MLT," not "adopt Shotcut," and MLT wouldn't do anything ffmpeg doesn't already do here. |
| Olive | GPL-3.0 | 🔴 Skip | Same story: GUI NLE, no headless/library story, no capability gap. |

### Image processing

| Project | License | Verdict | Why |
|---|---|---|---|
| ImageMagick | ImageMagick License (Apache-2.0-derivative, permissive) | 🔴 Skip (low priority) | CLI-subprocess-callable exactly like ffmpeg already is, so it's not architecturally awkward — but the existing hand-rolled `imaging.py` (blur/resize/vignette/PNG-encode) already works and was written *deliberately* dependency-free. Only worth reaching for if a specific missing operation (real ICC color management, exotic format support) becomes a real blocker. |
| **libvips / pyvips** | LGPL-2.1-or-later | 🟢 **Adopt (medium priority) — the single best-value pick in this whole report** | 4-8x faster and ~15x lower memory than ImageMagick per independent benchmarks, real Python bindings (not subprocess-CLI), and as of the `pyvips-binary` wheel (updated July 2026) it's a genuine `pip install` on Windows with no separate libvips download needed. If asset-provider images (from `asset_engine.py`'s multi-source fetches) ever need real normalization/resizing/format-conversion at scale, this is a one-dependency, low-risk, high-quality-improvement swap for the custom code in `imaging.py`. |

### Typography

| Project | License | Verdict | Why |
|---|---|---|---|
| **fonttools** | MIT | 🟢 **Adopt — highest-confidence, lowest-risk win in this report** | Directly fixes a weakness the code documents about itself: `brand/text.py` wraps text by character-count lookup table specifically *because* "measuring real glyph advances would need a font library we deliberately don't depend on" (its own words). `fontTools.ttLib` reads a font's `hmtx`/`cmap` tables for real per-glyph advance widths — no shaping engine needed for this brand's mostly-Latin all-caps display type, no new runtime, pure-Python-ish, one pip install. This directly improves headline/caption wrap accuracy against whichever font actually resolved (which now varies more, since this session added Windows fallback fonts). |
| Google Fonts (github.com/google/fonts) | Per-font OFL/Apache-2.0 (verify per family, generally unrestricted) | 🟢 Formalize an integration that already started informally | `@remotion/google-fonts` already exists on the JS/Remotion side. On the Python side, this session's own Windows font-resolution fix *already downloaded* Archivo Black, Anton, Barlow Condensed, and IBM Plex Mono directly from `github.com/google/fonts` raw URLs as a stopgap. The existing `scripts/fetch_brand_fonts.sh` does this properly on Linux (with attribution) but has no Windows equivalent — a small, concrete task: write the PowerShell counterpart, or better, move the fetch-with-caching-and-attribution logic into `theme.py`'s font resolution itself so it's platform-agnostic. |

---

## 3. Prioritized recommendation list

Ranked by (impact × how sure I am it's a real win) ÷ effort — not by category
order above.

1. **Fix `numpy` missing from `requirements.txt`.** Not OSS-integration work, but a one-line correctness bug this research surfaced. Do this regardless of anything else.
2. **Adopt fonttools for text wrapping.** Highest confidence, lowest effort, directly fixes a self-documented weakness, zero architecture change.
3. **Fix the `globe_flight` WebGL/2D-canvas mismatch and decide the Remotion question.** Not new integration work — closing a gap between what the code claims and what it does, and resolving a real license-vs-team-size decision that's currently unmade by default (Remotion sits there, unused, license risk unassessed).
4. **Adopt Mermaid for diagrams**, following the exact `threejs_engine.py` Puppeteer-worker pattern that's already proven in this repo. This is the one category with a genuine zero-to-something capability gap.
5. **Formalize the Google Fonts fetch** (Windows-native `fetch_brand_fonts` equivalent, or fold into `theme.py`). Small, concrete, closes out something this session already started ad hoc.
6. **Adopt Graphviz** for relationship-graph beats, once/if that content type comes up. Lower urgency than Mermaid; same subprocess-wrapper pattern as ffmpeg.
7. **Adopt pyvips**, but only when/if `asset_engine.py`'s fetched-image handling actually needs it — don't add the dependency speculatively.
8. Everything marked 🔴 above: no action. Re-evaluate only if a specific new requirement emerges that these would genuinely solve (e.g., a math-explainer spinoff channel → revisit Manim; a treemap/sankey chart requirement → revisit ECharts-SVG or port a d3-hierarchy algorithm).

## 4. What I'm explicitly *not* recommending, and why that's a feature not an oversight

The request's framing — "for every feature, determine whether an existing
open-source project already provides a production-quality solution... reuse
instead of rebuilding" — is the right instinct in general, but this audit
found the pipeline already followed it where it mattered (Three.js, Remotion,
ffmpeg) and made a deliberate, documented, reasonable call to hand-roll where
it didn't (charts, motion graphics, image processing) — mostly to avoid
adding a browser/JVM/GUI-app dependency for something a few hundred lines of
numpy already does correctly and fast. "Netflix-quality" isn't blocked by
missing D3 or ImageMagick; the actual quality ceiling right now is more
plausibly things like text-wrap accuracy (fonttools fixes this) and the
complete absence of diagram support (Mermaid fixes this) — which is why
those two are the top of the priority list rather than the biggest names on
the request's own list.

---

*No files outside this document were modified. Ready for review before any
of the above becomes an implementation task.*
