"""Director factory. Picks the real Claude engine or the offline mock."""
from __future__ import annotations

import os

from ..config import ChannelConfig


def get_director(channel: ChannelConfig):
    mode = os.getenv("DIRECTOR_MODE", "live").lower()
    if mode == "mock":
        from .mock import MockDirector
        return MockDirector(channel)
    from .engine import Director
    return Director(channel)
