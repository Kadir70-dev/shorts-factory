"""
Cross-upload ROTATION LEDGER — the memory that stops the channel from looking
like a template.

Every creative choice that could become a visible pattern across uploads (story
structure, music bed, transition palette, caption animation, CTA phrasing, colour
grade) is recorded here per channel. The next short reads the ledger and DEMOTES
recently-used options, so a viewer scrolling five of our Shorts in a row never
sees the same skeleton twice.

Design rules:
  * File-backed JSON under data/state/ — no DB dependency, safe for the CLI path.
  * Best-effort: a corrupt/unwritable ledger degrades to "no history", never
    raises. Variety is a quality feature, not a correctness requirement.
  * Bounded: each (channel, dimension) keeps only the last `KEEP` picks.
  * Process-safe enough for our worker model (max_jobs=2) via an atomic replace.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from .config import settings

KEEP = 12                      # how many recent picks to remember per dimension
_FILENAME = "rotation_ledger.json"


def _path() -> Path:
    return settings().data_dir / "state" / _FILENAME


def _load() -> dict:
    try:
        return json.loads(_path().read_text())
    except Exception:                          # noqa: BLE001 — missing/corrupt → empty
        return {}


def _save(data: dict) -> None:
    """Atomic write so a crash mid-render can't leave a truncated ledger."""
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, p)
    except Exception:                          # noqa: BLE001 — never break a render
        pass


def recent(channel_id: str, dimension: str, limit: int = KEEP) -> list[str]:
    """Most-recent-first list of the last picks for one dimension."""
    hist = _load().get(channel_id, {}).get(dimension, [])
    return list(hist)[:limit]


def record(channel_id: str, dimension: str, value: str) -> None:
    """Push one pick onto the front of a dimension's history."""
    data = _load()
    ch = data.setdefault(channel_id, {})
    hist = [value] + [v for v in ch.get(dimension, []) if v != value]
    ch[dimension] = hist[:KEEP]
    _save(data)


def record_many(channel_id: str, picks: dict[str, str]) -> None:
    """Record several dimensions in ONE read-modify-write (the render path)."""
    data = _load()
    ch = data.setdefault(channel_id, {})
    for dimension, value in picks.items():
        if not value:
            continue
        hist = [value] + [v for v in ch.get(dimension, []) if v != value]
        ch[dimension] = hist[:KEEP]
    _save(data)


def cooldown_weights(options: Iterable[str], history: list[str],
                     floor: float = 0.05) -> dict[str, float]:
    """Multiplier per option from how recently it was used.

    The most recent pick is nearly vetoed (`floor`), older picks recover linearly,
    and anything outside the remembered window keeps full weight. Multiplying a
    base weight by this is what turns "random" into "rotating" — options genuinely
    take turns instead of clustering by luck.
    """
    opts = list(options)
    span = max(1, min(len(history), max(1, len(opts) - 1)))
    out: dict[str, float] = {}
    for o in opts:
        try:
            age = history.index(o)
        except ValueError:
            out[o] = 1.0                       # unseen in the window → full weight
            continue
        if age >= span:
            out[o] = 1.0
        else:
            out[o] = floor + (1.0 - floor) * (age / span)
    return out
