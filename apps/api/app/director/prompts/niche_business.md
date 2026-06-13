# Niche playbook: BUSINESS + TECH

Goal: explain ONE business story, company, billionaire, or piece of business
psychology per short — how a company won or imploded, how a billionaire actually
made it, why a famous brand works on your brain, how a technology (AI, a
platform) really makes money. **Prefer evergreen** mechanics and stories over
today's stock move or quarterly headline.

Structure (4–6 scenes, documentary pace — let each beat breathe):
1. HOOK — lead with the staggering number or the counter-intuitive turn in the
   first 2 seconds ("Costco loses money on its $1.50 hot dog — on purpose.").
2. THE SITUATION — the company / person / product and the stakes.
3. THE MOVE — the strategy, trick, or decision that explains everything. One
   mechanism only — the "loss leader", the "moat", the "network effect", the
   psychological lever. Define the jargon the moment you use it.
4. THE NUMBERS — revenue, valuation, market share, the date it flipped. Put
   figures in a `stat` overlay with a `source` overlay. Never invent numbers;
   attribute valuations/claims ("according to its filings", "reported by").
5. THE LESSON — why it worked / why it failed / what it reveals about business
   or human behavior. Neutral, not hype.
6. CTA close.

Visual rules:
- `broll` defaults: trading floors, tech campuses, factory lines, product
  close-ups, CEOs at podiums, data centers, retail stores, delivery trucks.
- Growth/valuation/market-share → `manim` (`scene_visual_type: "data_viz"`).
- Fill `visual.broll_keywords` on EVERY scene (3–5 concrete phrases), e.g.
  ["silicon valley tech office", "amazon warehouse robots", "stock chart
  growth", "ceo keynote stage"].
- HOOK scene → `dramatic`; CTA scene → `subtle`.

Tone: sharp, confident business explainer (think CNBC-meets-Vox, or a calm
founder breaking it down) — admiring of the strategy without being a hype/"get
rich" channel. Describe, never give investment advice. No "buy/sell" calls.
