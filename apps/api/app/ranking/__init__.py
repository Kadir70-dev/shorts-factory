"""
Ranking Shorts — Top-5 countdown pipeline built on the Shorts Factory.

Flow (every stage is a CLI subcommand of `python -m app.ranking`):

  register/scan  → probe sources (ffprobe), detect scene cuts + loudness peaks
  segments       → suggest candidate moments, manual timestamp correction
  select         → pick 5 compatible, rights-cleared, non-duplicate moments
  approve        → HUMAN gate: nothing renders until a concept is approved
  render         → FFmpeg 1080x1920 countdown with branded overlays
  qa             → resolution / duration / sync / black-frame validation
  metadata       → US-English title, description, hashtags, credits
  schedule       → DST-aware US-Eastern slots per channel
  upload         → private-by-default, channel-locked, resumable, idempotent

Rights are tracked per source. Only sources whose license is VERIFIED are ever
eligible for selection, and reshuffling or captioning footage is never treated
as a substitute for the right to reuse it.
"""
