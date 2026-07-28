# Phase 2A — Gemini-Powered Finance Trend Intelligence

**Status:** shipped, additive, isolated. The Phase 1–4 render core (`PRODUCTION.md`)
is untouched.

This package answers exactly one question: **what should the next US-finance Short
be about?** It collects real external signals, normalizes and clusters them,
rejects duplicates and unsafe angles, scores every candidate deterministically,
and uses Gemini as a reasoning layer on top of data that was actually collected.

It does **not** render, upload or schedule anything.

---

## Architecture

```
Google Trends ─┐
YouTube ───────┤
Reddit ────────┤
X / Twitter ───┼──▶ Signal Normalization ──▶ Topic Clustering ──▶ Duplicate
Econ Calendar ─┤        (per-provider          (subject +          Rejection
Finance News ──┤         metric vocab)          event + text)          │
Gemini Search ─┘                                                       ▼
                                                          Evidence Verification
                                                          + Finance Safety Gate
                                                                       │
                                                                       ▼
                                                        Deterministic Pre-Score
                                                          (10-20 finalists)
                                                                       │
                                                                       ▼
                                                        Gemini Topic Ranking
                                                          (judgement only)
                                                                       │
                                             ┌─────────────────────────┤
                                             ▼                         ▼
                                    validate + reject         deterministic
                                    + RECOMPUTE score           fallback
                                             │                         │
                                             └───────────┬─────────────┘
                                                         ▼
                                                Best Topic Selection
                                                (or NO_SAFE_TOPIC_AVAILABLE)
                                                         ▼
                                          existing Director pipeline (opt-in)
```

### The division of labour

| Layer | Owns | Never does |
|---|---|---|
| Providers | fetching real data, preserving raw metrics | interpreting, scoring |
| Normalizer | canonical text, entities, factual state, comparable metrics | inventing absent metrics |
| Clustering | grouping wordings of one story | merging different factual states |
| Dedup | ledger enforcement | deciding quality |
| Safety | eligibility, risk penalty | ranking |
| Scoring | **the overall score, always** | qualitative nuance |
| Gemini | angle, hook, why-now, qualitative sub-scores | facts, numbers, sources, the final score |

---

## Module map

```
apps/api/app/topic_intelligence/
  settings.py        every flag and credential (separate from app.config.Settings)
  models.py          RawTrendSignal → NormalizedSignal → TopicCandidate → RankedTopic
  entities.py        ticker/company aliases, event + asset lexicons, source tiers
  normalizer.py      text canonicalization + per-provider metric normalization
  clustering.py      similarity blend, factual-state separation, syndication collapse
  dedup.py           exact + semantic dedup against the topic ledger
  safety.py          the finance safety gate (code, not prompt)
  scoring.py         deterministic pre-score and the authoritative overall score
  gemini_client.py   SDK loading, retries, budget, cost accounting
  rankers/           deterministic (fallback) + gemini (validated)
  providers/         seven independently-flagged connectors
  service.py         the orchestrator
  repository.py      additive SQLModel persistence
  provenance.py      the evidence bundle
  bridge.py          the ONE seam into the existing Director pipeline
  router.py          /topic-intelligence/* endpoints
  __main__.py        the CLI
config/topic_intelligence/scoring.yaml   weights, saturations, half-lives
```

---

## Providers — required, optional, paid

| Provider | Default | Cost | Notes |
|---|---|---|---|
| **Finance news (RSS)** | **ON** | **free, no key** | The only provider usable out of the box. Fed + BLS + CNBC + MarketWatch. |
| **YouTube Data API** | ON (needs key) | free quota 10,000 units/day | The competition signal. ~804 units/run → ~12 runs/day free. |
| **Gemini** | ON (needs key) | free tier available | The ranking layer. Without it the deterministic ranker runs. |
| Reddit | OFF | free | Official OAuth2. Interest signal ONLY. |
| Economic calendar | OFF | varies (Finnhub has a free tier; TradingEconomics is effectively paid) | Vendor-neutral abstraction. |
| Google Trends | OFF | **no free official API** | You must supply an approved connector endpoint. |
| X / Twitter | OFF | **paid plan required** | Recent search is not on the free tier. Auto-disabled without a token. |

> **Explicitly not claimed:** Google Trends and X access are *not* free and *not*
> universally available. Neither is required, and the system is fully functional
> without both.

### Fallback behaviour

* Any provider may fail, time out, be rate-limited or be missing — the run
  continues with whatever arrived. Every outcome is recorded in `ti_provider_run`.
* A provider that fails `TI_CIRCUIT_FAILURE_THRESHOLD` times trips a circuit
  breaker for `TI_CIRCUIT_RESET_S`.
* A provider whose newest signal is older than `TI_STALE_AFTER_HOURS` is marked
  `stale` (advisory — primary sources are quiet by nature).
* Gemini failure, disablement, or budget exhaustion → deterministic ranker.
* Nothing credible and safe survives → `NO_SAFE_TOPIC_AVAILABLE`, and **no filler
  content is generated**.

---

## Setup

### Gemini (recommended)

1. Get a key at <https://aistudio.google.com/apikey>.
2. `GEMINI_API_KEY=...` in `.env`.
3. `GEMINI_MODEL` must be a **stable production model** (default
   `gemini-2.5-flash`). Never pin a preview model.
4. `GEMINI_DAILY_BUDGET_USD` is enforced in code *before* each call, using spend
   recorded in `ti_ranking_run`. `0` means unlimited.

The SDK (`google-genai`) is imported lazily. If it is not installed, the engine
logs it and falls back — it does not crash.

### YouTube Data API (recommended)

1. <https://console.cloud.google.com> → new project → enable **YouTube Data API v3**.
2. Credentials → **API key** → `YOUTUBE_DATA_API_KEY=...`.
3. Restrict the key to the YouTube Data API.

Quota accounting per run (defaults): 8 × `search.list` (100 units each) + 1–2 ×
`videos.list` + 1 × `channels.list` ≈ **804 units**. Responses are cached for
`TI_CACHE_TTL_S` (15 min), so repeated runs inside that window are free.

### Reddit (optional)

1. <https://www.reddit.com/prefs/apps> → **create app** → type **script**.
2. Copy the client id (under the app name) and secret.
3. Set `REDDIT_ENABLED=true`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a
   descriptive `REDDIT_USER_AGENT` (Reddit rejects generic agents).

### X / Twitter (optional, paid)

1. <https://developer.x.com> → a plan that includes **recent search** (`/2/tweets/search/recent`).
2. `X_TRENDS_ENABLED=true` and `X_BEARER_TOKEN=...`.

Without a token the provider reports `missing credentials` and is skipped. A
401/403 is treated as "your plan does not include this" and is non-fatal.

### Economic calendar (optional)

Set `ECONOMIC_CALENDAR_PROVIDER` to one of:

* `finnhub` — free tier available, <https://finnhub.io>; set `ECONOMIC_CALENDAR_API_KEY`.
* `tradingeconomics` — `guest:guest` returns a tiny sample; real use is paid.
* `generic_json` — any endpoint you host; set `ECONOMIC_CALENDAR_BASE_URL`.

Adding a vendor means writing one `_parse_*` branch in
`providers/economic_calendar.py`. `previous`/`forecast`/`actual` are passed
through exactly as published and stay `None` when absent.

### Google Trends (optional)

There is no free, officially supported public Trends API, and unofficial scrapers
are not a hidden production dependency here. To enable it, host or buy a
connector and point `GOOGLE_TRENDS_BASE_URL` at it. The expected response shape
is documented at the top of `providers/google_trends.py`.

### Finance news (on by default)

Works with no key. Override the feed list with `TI_NEWS_RSS_FEEDS` (comma
separated). `NEWS_API_KEY` (<https://newsapi.org>) optionally adds NewsAPI; its
free tier is development-only and rate-limited.

---

## Scoring

The overall score is **always** recomputed in code from
`config/topic_intelligence/scoring.yaml`:

```
overall = Σ (normalized_weight_i × sub_score_i) − risk_weight × risk_penalty
```

| Dimension | Weight | Source |
|---|---|---|
| trend_momentum | 0.20 | deterministic only |
| audience_relevance | 0.15 | deterministic, Gemini-adjustable |
| freshness | 0.12 | deterministic only |
| cross_source_confirmation → `credibility` | 0.12 | deterministic only |
| competition_opportunity | 0.10 | deterministic only |
| ctr_potential | 0.10 | deterministic, Gemini-adjustable |
| retention_potential | 0.08 | deterministic, Gemini-adjustable |
| monetization_potential | 0.05 | deterministic, Gemini-adjustable |
| production_feasibility | 0.05 | deterministic, Gemini-adjustable |
| subscriber_potential | 0.03 | deterministic, Gemini-adjustable |
| **risk_penalty** | ×0.60 | **subtractive**, deterministic only |

Gemini may move an *adjustable* sub-score by at most `GEMINI_INFLUENCE`
(default 0.5, i.e. a 50/50 blend). It cannot touch momentum, freshness,
credibility, competition or risk, and it can never set `overall_score`.

### Competition opportunity

Not "how many search results". Computed from what the YouTube API actually
returned:

```
0.32×demand + 0.20×(100−supply) + 0.18×(100−incumbent_strength)
+ 0.12×staleness + 0.10×same_angle_saturation + 0.08×breakout
```

where incumbent strength blends median competitor views and median subscriber
count, staleness is the age of competing uploads, and breakout is
views-per-subscriber. Without YouTube data the score is a neutral 50 and the run
says so — no keyword volume is ever claimed.

### CTR / retention / subscriber / monetization

These are **internal relative scores (0–100) with a confidence**, not real-world
predictions. The engine never emits a claim like "this will achieve 12.4% CTR".
Monetization is deliberately *not* called ROI: real ROI needs YouTube analytics
and revenue data, which this phase does not have.

---

## Finance safety gate

Implemented in `safety.py` as code, so a model that ignores its instructions
cannot get past it. It runs **before** Gemini and again **on Gemini's own output**.

**Blocking** (topic can never win): guaranteed-profit claims, personalized
financial advice / buy-now-sell-now, pump-and-dump framing, unsupported
manipulation allegations, insider-trading implications, predictions stated as
fact, sensational claims about named individuals, and any rumour whose only
support is social.

**Penalizing**: misleading certainty, sensational framing, unverified price
claims, breaking-news framing, single-source "confirmed" events, no citable URL,
incomplete grounding metadata, and factual claims supported only by social
sources. A cumulative penalty ≥ 60 blocks the candidate.

Every candidate carries `risk_flags`, `risk_penalty` and
`eligible_for_production`.

---

## Deduplication

| Layer | Window | Basis |
|---|---|---|
| Exact | `TOPIC_EXACT_DEDUP_DAYS` (365) | canonical hash of (factual_state, token set) |
| Semantic | `TOPIC_SEMANTIC_DEDUP_DAYS` (90) | blended similarity ≥ `TOPIC_SIMILARITY_THRESHOLD` (0.86) |
| Angle | same | `ANGLE_SIMILARITY_THRESHOLD` (0.90) — a different angle is allowed but penalized |

Ledger statuses that block reuse: `selected`, `queued`, `rendering`, `published`.

A topic is reusable when (a) a **materially new event** occurred — a confirmed
release supersedes the forecast that preceded it, (b) the angle is substantially
different, or (c) an admin passes `--override <topic_id>`.

---

## Database

Seven additive tables, all prefixed `ti_`. The existing `Job` table is **not**
modified and its JSON blobs are not overloaded with trend data.

```
ti_provider_run     per-provider outcome for one run (the health ledger)
ti_trend_signal     raw + normalized signal, for audit
ti_topic_candidate  clustered candidate + deterministic scores + dedup verdict
ti_topic_evidence   the citation ledger
ti_ranking_run      one end-to-end decision (audit root, carries cost)
ti_ranking_result   per-candidate outcome, including why a candidate lost
ti_topic_ledger     what the channel has committed to — the dedup memory
```

Migration is `SQLModel.metadata.create_all(tables=[...])` — creates what is
missing, alters nothing. SQLite-compatible; right-sized for ~3 videos/day.

---

## Usage

### CLI

```bash
cd apps/api

python -m app.topic_intelligence status                      # config + budget
python -m app.topic_intelligence collect --channel usa_trading
python -m app.topic_intelligence rank    --channel usa_trading
python -m app.topic_intelligence select  --channel usa_trading
python -m app.topic_intelligence run     --channel usa_trading
python -m app.topic_intelligence run     --channel usa_trading --enqueue
python -m app.topic_intelligence run     --channel usa_trading --json
python -m app.topic_intelligence run     --channel usa_trading --no-persist
```

Exit codes: `0` success, `2` `NO_SAFE_TOPIC_AVAILABLE`, `1` unexpected error.

### API

```
POST /topic-intelligence/collect
POST /topic-intelligence/rank
POST /topic-intelligence/select          409 when NO_SAFE_TOPIC_AVAILABLE
GET  /topic-intelligence/candidates
GET  /topic-intelligence/candidates/{topic_id}
GET  /topic-intelligence/providers/status
GET  /topic-intelligence/runs/{run_id}
```

### Handing the topic to production

`TI_AUTO_ENQUEUE=true` (or `--enqueue`) builds a `VideoSpec` and enqueues it via
`routers.generate.enqueue_spec` — the exact path `/generate` uses. The evidence
bundle is attached to the job's `metadata_json` under `topic_intelligence`, so a
finished render retains the evidence used to select its topic.

Phase 2A does **not** add uploading or the 3-per-day scheduler.

---

## Cost control

```
200-500 raw signals  →  20-40 clusters  →  10-20 finalists  →  Gemini  →  1 topic
   TI_MAX_RAW_SIGNALS   TI_MAX_CLUSTERS    TI_MAX_FINALISTS    GEMINI_MAX_CANDIDATES
```

Gemini sees a compact payload for the finalists only — never raw posts. One call
per run. Tokens and estimated USD are logged per call (`[ti.gemini] …`) and
persisted on `ti_ranking_run`. API keys are never logged. `429
RESOURCE_EXHAUSTED` is retried with exponential backoff + full jitter, honouring
a server-supplied `retryDelay`, then falls back.

---

## Tests

```bash
cd apps/api && python -m pytest tests -q
```

All tests run with **no API keys and no network**. Fixture scenarios cover an
FOMC decision, a CPI release (forecast *and* confirmed, kept separate), an Nvidia
earnings story, a Bitcoin price event, an HFT evergreen explainer, an unsupported
viral Reddit rumour, and a duplicate syndicated news story.

---

## Known limitations

* **Semantic similarity is lexical**, not embedding-based: token Jaccard +
  character-trigram cosine + entity/event agreement. Deterministic, dependency
  free and explainable, but it will miss paraphrases with no shared vocabulary
  and no shared entity. Swapping in embeddings means replacing
  `clustering.text_similarity` only.
* **Entity coverage is a curated list** (`entities.py`), not NER. Unlisted tickers
  and people are not linked.
* **Google Trends and X are inert** without, respectively, a connector you supply
  and a paid plan.
* **Monetization potential is a heuristic**, not a revenue estimate.
* **Cost figures are estimates** from configured list prices, not billed amounts.
* The frozen pipeline has no pytest suite of its own; Phase 2A enforces
  "production stays green" structurally (imports, contracts, table shape, the
  enqueue seam) rather than behaviourally.
