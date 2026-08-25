# THE COMPLETE HISTORY OF BITCOIN
## Episode 1 — The World Before Bitcoin (1970–2008)

Production plan. The machine-readable spec is `scene_graph.json`; this document
is what a human needs to approve, source and finish it.

| | |
|---|---|
| Runtime | 856s authored estimate · **~745s (12.4 min) at measured TTS speed** |
| Beats | 156 · 1,726 words · 10 chapters |
| Format | 1080×1920, 30 fps, H.264 |
| Brand | `k70` — deep navy-black, one gold accent, green/red reserved for real data direction |
| Channel / niche | `k70_history` / `usa_history` |
| Story structure | `timeline_twist_conclusion` |
| Music family | `mystery` — "dark ambience · mystery and suspense" |
| Pre-render QA | **26/26 PASS** (`qa_report.md`) |

---

## 1. Story architecture

Ten chapters. Every one ends on a beat whose role is a turn, reveal, stake or
payoff — never a flat context line. QA enforces this.

| # | Chapter | Ends on |
|---|---|---|
| 00 | Cold Open — The Vault That Could Not Pay | "…the thing in your wallet was no longer what you thought it was." |
| 01 | The Promise (1944) | "That was all the time the system had left." |
| 02 | The Drain (1952–1971) | "And then Britain asked for roughly three billion more." |
| 03 | Sunday Night (15 August 1971) | The 1971 dollar worth 19 cents by 2008 |
| 04 | The Decade The Money Died (1971–1981) | "The value of your money is a decision. And you are not the one making it." |
| 05 | The Machine That Kept Breaking (1986–1998) | "But: what if you did not need one?" |
| 06 | The Ones Who Tried (1982–2007) | "Nobody knew how to build that." |
| 07 | When Money Breaks In Real Life (2001–2008) | "In two thousand and seven, that thought died too." |
| 08 | The Collapse (2007–2008) | "In the autumn of 2008, hundreds of millions of people stopped." |
| 09 | Cliffhanger | "…that would change money forever." → EPISODE TWO card |

**Twist cadence:** 59 turn/reveal/hook beats. Longest gap **34s**, median **14s** —
inside the brief's 20–40s rule with margin.

**The structural choice that carries the episode.** Chapter 1 originally ran 40
seconds of uninterrupted world-building — the flattest stretch in the film.
Rather than relabel beats to satisfy the cadence check, a real twist was added:
**Robert Triffin told the Joint Economic Committee in October 1959 that Bretton
Woods was already doomed, and Congress did nothing for twelve years.** It turns
the setup into a countdown and hands Chapter 2 a clock.

---

## 2. Visual Intelligence plan

Every one of the 156 narration sentences carries a visual plan. Zero talking-head
beats, zero flat-colour beats, **136 distinct visuals and 156 distinct visual
objectives — no visual is used twice**.

Six channels. `visual_budget.yaml` sets the bands; the allocator assigns each
scene exactly one channel, so the mix sums to 100% by construction.

| Channel | Authored | Allocator's own plan | Band | What it carries |
|---|---|---|---|---|
| Motion graphics | 28.2% | 32.3% | 25–35% | The claim itself, set in the channel's type |
| Official / archival | 17.8% | 15.2% | 15–25% | Government, central-bank, museum, public-domain |
| Charts | 16.2% | 10.0% | 10–20% | Real cited figures, animated |
| AI cinematic recreation | 15.2% | 16.3% | 15–25% | Moments no camera was in the room for |
| Three.js | 13.5% | 16.1% | 15–25% | Globe flights — geography and scale |
| Stock | 9.2% | 10.0% | 10–20% | Support shots of genuinely filmable things |

The allocator reads the graph independently and lands **inside every band**. It
wins at render time; the authored column is editorial intent.

**Decision rule per sentence:**
1. Does the line state a real, sourced figure? → **chart** of exactly that figure, attributed on screen.
2. Does it name a real place? → **globe flight** to that place.
3. Does a real document or photograph exist? → **archival**, cited.
4. Is the subject genuinely filmable and generic? → **stock**, support only.
5. Was no camera in the room? → **AI recreation**, disclosed.
6. Otherwise → **kinetic type**. The floor, never the default.

---

## 3. Charts (21)

All from figures verified against primary or institutional sources. No chart
carries a number the narration does not speak.

| Scene | Form | Figure | Source |
|---|---|---|---|
| s20 | counter | $35/oz, fixed 1944–1971 | Bretton Woods Agreement |
| s34 | counter | 20,748 t US gold, 1952 | U.S. Treasury (Minerals Yearbook 1952) at $35/oz |
| s35 | delta | 20,748 t → 8,133 t | U.S. Treasury / U.S. Mint |
| s36 | meter | 61% of reserves gone | U.S. Treasury / U.S. Mint |
| s51 | delta | $1.00 (1971) → $0.19 (2008) | BLS CPI-U 40.5 → 215.3 |
| s54 | delta | Gold $35 → $850 (21 Jan 1980) | London gold fixing |
| s57 | line_trend | US inflation 1971–1982, 12 real points | BLS CPI-U |
| s61 | counter | Fed funds 19.1%, June 1981 | Federal Reserve |
| s66 | bar_compare | 1,043 of 3,234 S&Ls failed | FDIC / GAO 1996 |
| s67 | bar_compare | $160B total, $132.1B taxpayers | GAO 1996 |
| s69 | counter | Dow −22.6%, 19 Oct 1987 | DJIA |
| s89 | delta | DigiCash 1989 → 1998 | Chapter 11 filing |
| s118 | counter | 250 pesos/week | Decree 1570/2001 |
| s120 | counter | $95B default | Republic of Argentina / IMF |
| s125 | counter | Prices doubling every 24.7 hours | Hanke & Kwok, Cato Journal 29(2) 2009 |
| s134 | delta | 1866 → 2007, 141 years | Overend & Gurney → Northern Rock |
| s135 | bar_compare | Bear Stearns $171.51 → $2.00 → $10.00 | JPMorgan / Federal Reserve |
| s140 | counter | Lehman $639B assets | Chapter 11 petition, 15 Sep 2008 |
| s141 | counter | Fed → AIG $85B | Federal Reserve Board, 16 Sep 2008 |
| s142 | bar_compare | Bear $30B · AIG $85B · TARP $700B | EESA, 3 Oct 2008 |
| s144 | counter | 7.8M completed foreclosures | CoreLogic (2017) |

**Two chart-renderer defects were found and fixed while proving these** — see §9.

---

## 4. Maps / Three.js plan (20 globe flights)

The `globe_flight` template flies world → country → region. Every target was
verified to resolve against the Natural Earth and US Census boundary data, and
**no destination is used twice**.

| Scene | Target | Move |
|---|---|---|
| s7 | Maryland | The vanishing to Camp David |
| s14 | New Hampshire | Bretton Woods, 44 nations |
| s17 | Germany | 1930s devaluations firing between capitals |
| s22 | India | The far side of the world, tethered to Washington |
| s31 | Japan | Dollars leaving the US across the Pacific |
| s37 | France | Paris converts |
| s47 | United States of America | Every currency on earth, backed by one thing |
| s62 | Ohio | Where the 1981–82 recession landed |
| s72 | Thailand | The baht floats, July 1997 |
| s73 | Indonesia | Contagion spreading from Bangkok |
| s74 | Russia | Moscow defaults, August 1998 |
| s76 | New York | Liberty Street — the LTCM rescue |
| s86 | Netherlands | DigiCash, Amsterdam 1989 |
| s87 | Switzerland | Deutsche Bank and Credit Suisse sign |
| s90 | California | The Bay Area, 1992 |
| s104 | Florida | The network collapses to one address — e-gold's, per the DOJ indictment |
| s116 | Argentina | Buenos Aires, 1 December 2001 |
| s124 | Zimbabwe | 2008 |
| s128 | Hungary | The 1946 pengő — the worst on record |
| s131 | United Kingdom | Newcastle, 14 September 2007 |

`s104` is the plan's best beat: the narration says a referee always has *an
address*, and the camera lands on the state where e-gold's directors actually
lived, per the Justice Department's own indictment.

---

## 5. Motion graphics plan

47 kinetic-type beats. Each carries authored display copy in a `headline`
overlay — the schema's display-copy channel. The renderer skips scene typography
for pre-rendered visuals, so the card is drawn once, by the motion-graphics
engine, never doubled.

Recurring devices, used once each:
- **Single-word holds** — "TEMPORARILY." · "TRUST." — the loudest lines in the film
- **Callbacks** — "THE PATTERN" (ch 5 open) → "NOTICE THE PATTERN" (ch 5 close)
- **Mirror pairs** — "THEY GOT THE MONEY." / "YOU GOT THE LETTER."
- **Counters as type** — "1959 → 1971" running in silence
- **Quote cards** — Nixon (15 Aug 1971), Hughes (Mar 1993)

The finance motion engine additionally maps document-shaped beats to
`document_highlight` (s85, the Chaum paper) and event beats to `timeline_events`.

---

## 6. Asset plan

Full machine-readable plan in `asset_plan.json` — one entry per beat with
channel, acquisition route, query/prompt, search terms, citation and licence.

| Route | Beats | Notes |
|---|---|---|
| Rendered in-pipeline | 88 | charts, motion graphics, Three.js — no network, no keys, no licence risk |
| Archival / official | 27 | **manual clearance required** — government and central-bank sources are public domain; museum and press images are not |
| Stock video API | 17 | Pexels / Pixabay — support shots only |
| AI recreation | 24 | synthetic; see §8 |

`scene_graph.json` deliberately ships with `asset_provenance`,
`threejs_provenance`, `motion_graphics_provenance` and `ai_broll_provenance`
**empty**. Those models are render *receipts* — they record what was fetched or
drawn, with retrieval dates and cache keys. Filling them by hand would put
`status: "rendered"` next to work nobody did. The pipeline writes them.

**28 sources are cited**, each opened and checked during authoring. Full register
in `timeline.md`, keyed to the beats that depend on them.

---

## 7. Music plan

`music.py` builds the intensity envelope from `beat_role`, so choreographing
roles *is* choreographing the score. Family: `mystery`.

| Role | Level | Where |
|---|---|---|
| hook | −17 dB | 4 chapter openers |
| turn / reveal / evidence / payoff | −19 dB | 78 beats — the swells |
| context / mechanism | −25 dB | 35 beats — the film breathing out |
| cta | −20 dB | the Episode 2 card |

Base sits at −24 dB under narration with sidechain ducking at −9 dB, 1.5s fade
in, 2.0s fade out. The bed never cuts abruptly; both renderers interpolate
linearly between keyframes.

---

## 8. Compliance

- **Disclaimer** burned in and prepended to the description: *"Educational purposes only. Not financial advice."*
- **YouTube "Altered or Synthetic Content" must be ticked.** 24 beats (15% of runtime) are AI recreations of real historical moments. They are shot as *recreations* — no fabricated documents, no invented quotes, no synthetic likeness of a real named person presented as archive. The pipeline flags this; it cannot tick the box for you.
- **Confidence labelling.** Every beat carries `confirmed` / `probable`. The four `probable` beats — the £3bn British request, France's conversions, e-gold's account count, Hungary 1946 — are hedged in the read ("about", "by most accounts", "more than a million", "almost every generation"). QA fails the build if an unconfirmed beat is stated flat.
- Compliance pass on the rendered slice: **PASS**, one advisory note on the word "bankruptcy" in the description (sourced and neutral, kept).

---

## 9. Pipeline defects found and fixed

Proving this episode surfaced four real bugs. All four are fixed in the pipeline,
not worked around in the spec.

1. **`variety.apply` discarded authored transitions.** Its docstring promised "a scene that already carries a non-default transition keeps it"; the code overwrote all of them from a random palette. All 21 authored chapter-break transitions were being rolled away. *Verified: 21/21 now survive.*
2. **Globe flights landed in the wrong country.** `map_template` resolved the place by scanning `location + entity + narration + objective` with longest-match wins, so a beat located in Japan whose objective described the flight "out of the United States" flew to the United States. Six of twenty flights were wrong. An explicit `location` now wins outright. *Verified: 20/20 hit their target.*
3. **Chart readouts coloured by series direction, not by meaning.** The TARP total and the 1980 inflation spike both printed in the palette's `positive` green because their series happen to rise — against the brand rule reserving green for genuine data UP. The highlighted datum's explicit `emphasis` now wins. *Verified: both now red.*
4. **Production notes were printed on screen.** When a footage beat failed to resolve, the kinetic-type fallback used `visual.visual_intent` as its headline — a note aimed at the asset resolver. The rendered slice published **"MARINE ONE LIFTING OFF THE SOUTH LAWN, 1971 — THE VANISHING"** as a title card. Two call sites, now sharing one `_display_headline()` helper that only ever uses authored display copy or the narration. *Verified in a re-render.*

5. **The asset resolver threw away the Director's own search phrases.** `asset_engine.build_query()` read only storyboard fields and extracted subject nouns with `_FASHION_SUBJECT` — a *fashion* vocabulary (cotton, denim, loom, tannery). On a finance/history documentary it matches nothing, so queries collapsed to raw narration grammar: `'And then Britain asked for roughly'`, `'It worked Inflation broke'`. Meanwhile every scene already carries `broll_keywords` — which the schema defines as "ordered footage search phrases for the asset resolver" — e.g. `['marine one helicopter 1971', …]`. The engine never read them.

   That guaranteed rejection. `narration_match` scores a candidate as `0.30 + 0.70 × coverage` of the **query's** words; the floor is `0.58`, needing 40% coverage. Grammar words never appear in an archive caption, so **63 of 72 candidates scored 0.30–0.47 and were rejected**. Both the first query and the retry used the same broken extractor, so every beat paid two full provider fan-outs to fail twice — that was the 400-second asset stage.

   Fixed in three parts: authored keywords now lead the query, **one phrase per search** (concatenating both *lowers* coverage and so lowers the score of a correct photograph), and a stopword filter on the fallback path. Measured: candidates passing the gate **5 → 17**, official/public-domain delivered **0.0% → 14.0%**, asset stage **399.6s → 308.9s**, QA FAIL → **PASS**.

6. **`SAFE_LICENSES` omitted CC BY 2.5**, rejecting the genuinely relevant Northern Rock archival photographs on licence grounds. The 2.5 and 1.0 CC generations are exactly as commercially safe as the 2.0/3.0/4.0 already listed; attribution travels with the candidate and is burned into the credits. NonCommercial and NoDerivatives remain excluded. Licence rejections: **4 → 0**.

7. **Three.js was reported as "not installed" on a machine where it was fully installed.** `shutil.which("node")` cannot see an nvm install, because nvm adds its bin directory from an *interactive* shell profile that a pipeline subprocess never loads. All 20 globe flights were silently dropping to the 2D ladder. `find_node()` now checks `$NODE_BIN`, then PATH, then the newest `~/.nvm/versions/node/*`, and prepends that directory to the child environment so the `tsc` shim resolves too.

8. **Globe flights arrived unlabelled.** `_flight()` sent the subject as `pins`, which `worker.ts` types but never draws — only `regions` are painted and labelled. Every flight landed on an unhighlighted country and never told the viewer where it was. The subject now travels as a `region`, which gets the accent fill, the outline and a clamped screen label in one pass.

Also: a twelve-point line chart drew its axis labels on top of each other
(1971/1972, 1981/1982). Labels are now thinned by collision, with the highlighted
year seeded first so the beat's own number is never the one dropped. The chart
cache version was bumped, per the module's own protocol.

`scripts/produce.py` had a flat `RENDER_TIMEOUT_S = 600`, correct for a 45-second
Short and fatal for a 12-minute film. It now scales with runtime, with 600s as
the floor.

---

## 10. Metadata

**Title**
> The World Before Bitcoin | The Complete History of Bitcoin · Ep. 1

**Hook (first 1.5s on screen)**
> In August 1971, Britain asked America for its gold. The gold wasn't there.

**Description** — in `scene_graph.json` under `meta.description`; leads with the
episode premise, lists the source institutions, closes with the disclaimer.

**Tags** — bitcoin · history of bitcoin · bitcoin documentary · 1971 · nixon
shock · gold standard · bretton woods · inflation · 2008 financial crisis ·
lehman brothers · cypherpunks · digicash · hyperinflation · argentina 2001 ·
zimbabwe · federal reserve · money · documentary

**Hashtags** — #bitcoin #documentary #history #money #2008crisis

**Pinned comment** — the 28-source register from `timeline.md`, so every date and
figure in the episode can be checked by a viewer.

---

## 11. Thumbnail concept

**Text:** `THE GOLD WASN'T THERE`

Three words the audience cannot resolve without clicking. It is not about
Bitcoin, which is the point — Episode 1 has to sell the *problem*.

**Composition (1280×720):**
- Left two-thirds: the interior of a bullion vault, shot wide, **almost empty** — bare steel shelving, two bars left, one hard raking light. Deep navy-black, the brand base.
- Right third: the type, stacked in the display face. `THE GOLD` in ink white, **`WASN'T THERE`** in the gold accent, the only saturated element in frame.
- Bottom-left corner: `1971` small, in mono, gold rule beneath — a date, not a label.
- No face. No arrow. No circle. The brand's rule is documentary restraint, and a
  clean empty vault at thumbnail size reads faster than a person pointing at one.

**Why it works:** the frame contains a visible absence. The eye finds the empty
shelving before it reads the words, and the words then explain what is missing.

**Series continuity:** every episode thumbnail is the same grid — image left,
gold-accented three-word claim right, year bottom-left. Episode 2's is the nine
pages.

---

## 12. What still blocks the full-quality render

The spec is finished and validated. The 54-second cold open has been rendered
end-to-end through `produce.py` and passed every QA gate. The full episode needs
three things this host does not currently have:

Every provider used is **free**. Nothing here bills.

| Source | Cost | Status |
|---|---|---|
| Wikimedia Commons | free, no key | available — 3.0s/search |
| Pexels | free tier key | available — 0.8s/search |
| Pixabay | free tier key | available — 0.4s/search |
| Pollinations (AI stills) | free, no key | available — 1.4s/image |
| Three.js / charts / motion graphics / maps | local | available |
| Google AI, HuggingFace, ComfyUI | paid or token | **unconfigured — skipped without a network call** |

Provider availability is now decided **once per run** rather than rediscovered per
beat, and a provider that fails twice is parked for the remainder of the run.
Measured: 50 calls to an unconfigured provider cost **0.2 ms total**; a parked
provider short-circuits in **0.03 ms** without opening a socket.

Measured on this box (4 cores, 3.8 GB): render runs at **2.13× realtime**, TTS at
**~1× realtime**, and TTS comes in **~13% faster** than the authored estimate, so
the finished episode lands near **12.4 minutes**.

Remaining bottleneck: the asset stage still costs ~62s per externally-resolved
beat, dominated by candidate downloads rather than search. Budget **~100 minutes**
of wall clock for a full episode render, QA and packaging.

```bash
.venv/bin/python scripts/build_bitcoin_ep01.py     # rebuild the spec
.venv/bin/python scripts/qa_bitcoin_ep01.py        # 26/26 must pass first
.venv/bin/python scripts/produce.py --preset documentary_series \
    --from-json data/series/bitcoin_history/ep01/scene_graph.json --keep
```
