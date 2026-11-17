# K70 Finance Shorts — simple, high-retention production recipe

**Markets:** USA Finance and World Finance. **Output:** 9:16, 1080×1920, 30 FPS,
~30–40 seconds. **Style:** real licensed footage + concise original newspaper
clippings + clear sourced charts + one useful explanation. This extends the
existing Shorts Factory; it does not replace FFmpeg, existing footage, narration,
the chart renderer or the frozen 14-layer long-form architecture.

## What "newspaper" means

1. **Default:** original K70 **Market Brief** newspaper-style card.
   It displays a rewritten, sourced financial headline, real date, and real
   publisher. It does **not** impersonate a newspaper, copy an article, or show
   a fabricated outlet masthead.
2. **Optional:** actual newspaper front-page photos or newspaper-turning footage.
   Add only when source and the rights/license have been separately reviewed.
   A public URL does **not** mean an image/article can be reused freely.
3. Add full original source URL to a sidecar and video description. On-screen
   source/date always visible. Never invent a newspaper screenshot or publish a
   current-looking headline based on an old report.
4. Pexels footage may be used under the Pexels License, but check each clip for
   represented people/brands, authenticity, and any extra rights. A photo of
   *someone* shopping is not evidence of an *American* shopper unless documented.

## Retention template (no promise of viral results)

- **0–2.5s:** a truthful contradiction or suspense hook on actual moving footage.
- **2.5–6s:** why the viewer should care (footage).
- **6–9s:** newspaper headline, zoom/reveal, source and date.
- **9–13.5s:** one mobile-readable chart with real figures.
- **13.5–17.5s:** cut back to real-world impact.
- **17.5–22s:** one strong, evidence-backed chart twist.
- **22–30s:** consequence + memorable payoff with real footage.
- **30–34s:** relevant ending question or takeaway; no manufactured engagement.

Use the beat structure as a *starting hypothesis*. Avoid aggressive edits that
make numbers unreadable. Aim for a meaningful visual shift every 2–5 seconds.
Captions/voice/music remain managed by the existing factory. Track actual
YouTube Studio **Stayed to watch**, audience retention, average percentage
viewed, Engaged views and comments/shares after posting. Revise based on the
observed drop-off points, not guessed viral claims.

Example, sourced editorial storyboards:
`data/k70_finance_shorts/storyboard_examples.json`
Both are editorial drafts and **not footage-cleared/production-rendered**.

## Preview the newspaper on real licensed footage

The repo's previous USA Inflation footage manifest includes a Pexels grocery
clip. If you have downloaded it to the existing local path and reviewed its
rights, run:

```bash
python scripts/k70_finance_storyboard_check.py
python scripts/k70_finance_news_preview.py \
  --clip data/k70_usa_inflation_20261117/footage/pexels_29369224.mp4 \
  --clip-source https://www.pexels.com/video/woman-shopping-for-organic-potatoes-29369224/ \
  --license https://www.pexels.com/license/ \
  --out /tmp/k70_usa_press_preview.mp4
```

The 3-second sample combines the *original*, dated BLS 9.1% June 2022 data
with the original K70 news-card graphic and the supplied footage. It writes an
MP4 and `.sources.json` evidence sidecar. There is no fake-video fallback.
The code tests all 90 frames for clipped and overlapping text **before** render.

The sample is not a finished Short; don't upload it as one. Complete the
existing scene graph/narration workflow only after sample quality approval.

## Two data-first story sources

- **USA Inflation (historical):** BLS CPI news release dated July 13, 2022:
  https://www.bls.gov/news.release/archives/cpi_07132022.htm
  (June 2022 12-month change: 9.1%).
- **World Debt (historical):** World Bank International Debt Report release
  dated December 3, 2025:
  https://www.worldbank.org/en/news/press-release/2025/12/03/developing-countries-debt-outflows-hit-50-year-high-during-2022-2024
  (2024 LMIC external debt interest payments approximately $415B).

**Not yet done:** footage cleared for the World Debt example, the two full
34-second Shorts rendered, narrator/caption alignment for those two videos,
real YouTube metrics, or uploads. No promises of engagement or monetization.
