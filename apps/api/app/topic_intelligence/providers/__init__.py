"""Provider registry. Every connector is optional and independently flagged."""
from __future__ import annotations

from ..settings import TopicIntelligenceSettings
from .base import BaseProvider, TrendProvider
from .economic_calendar import EconomicCalendarProvider
from .finance_news import FinanceNewsProvider
from .gemini_grounding import GeminiGroundingProvider
from .google_trends import GoogleTrendsProvider
from .reddit import RedditProvider
from .x_api import XProvider
from .youtube import YouTubeProvider

PROVIDER_CLASSES = (
    GoogleTrendsProvider,
    YouTubeProvider,
    RedditProvider,
    XProvider,
    EconomicCalendarProvider,
    FinanceNewsProvider,
    GeminiGroundingProvider,
)


def build_providers(
    settings: TopicIntelligenceSettings | None = None,
    *,
    only: set[str] | None = None,
) -> list[BaseProvider]:
    """Instantiate every provider. Disabled/unconfigured ones are still returned so
    their status shows up in the health report — they just yield no signals."""
    providers = [cls(settings) for cls in PROVIDER_CLASSES]
    if only:
        providers = [p for p in providers if p.name in only]
    return providers


__all__ = [
    "BaseProvider", "TrendProvider", "build_providers", "PROVIDER_CLASSES",
    "GoogleTrendsProvider", "YouTubeProvider", "RedditProvider", "XProvider",
    "EconomicCalendarProvider", "FinanceNewsProvider", "GeminiGroundingProvider",
]
