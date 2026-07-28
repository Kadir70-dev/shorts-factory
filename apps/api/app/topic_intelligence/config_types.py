"""
The channel brief handed to a ranker: identity, audience, editorial rules and
production constraints. Built from the EXISTING `config/channels/<id>.yaml`, so a
channel's creative DNA has exactly one home.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import ChannelConfig

DEFAULT_ALLOWED_ASSETS = (
    "equities", "crypto", "gold", "oil", "forex", "rates", "macro", "ai_tech",
    "market_structure",
)

# Always-on editorial rules for a US finance channel, on top of the channel's own
# banned_topics. Enforced in code by safety.py — listed here so the model sees them.
BASE_BANNED_TOPICS = (
    "guaranteed returns or risk-free profit claims",
    "personalized financial advice or buy/sell recommendations",
    "pump-and-dump or 'to the moon' framing",
    "unsupported market-manipulation allegations",
    "unverified prices, statistics or breaking news",
    "predictions presented as facts",
    "insider-trading implications",
    "sensational claims about named individuals without evidence",
)


class ChannelBrief(BaseModel):
    channel_id: str
    name: str = ""
    niche: str = ""
    target_audience: str = (
        "US-based retail investors and traders, 18-45, who follow markets daily and "
        "want a sharp 30-45 second explanation of what just happened and why it matters"
    )
    identity: str = ""
    cta: str = ""
    banned_topics: list[str] = Field(default_factory=lambda: list(BASE_BANNED_TOPICS))
    allowed_asset_classes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ASSETS)
    )
    # Production constraints from the frozen pipeline (RenderConfig defaults).
    min_duration_sec: float = 20.0
    max_duration_sec: float = 45.0
    production_notes: str = (
        "Vertical 1080x1920 Shorts, 20-45s, CPU-only render: narration + real "
        "footage/AI stills + captions + at most one animated chart. No live "
        "presenter, no complex multi-scene reenactments."
    )
    region: str = "US"

    @classmethod
    def from_channel(cls, channel: ChannelConfig, region: str = "US") -> "ChannelBrief":
        return cls(
            channel_id=channel.id,
            name=channel.name,
            niche=channel.niche,
            identity=(channel.style_notes or "").strip(),
            cta=channel.cta,
            banned_topics=list(BASE_BANNED_TOPICS) + list(channel.banned_topics),
            region=region,
        )
