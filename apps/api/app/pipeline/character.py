"""
Reusable CHARACTER MEMORY (Phase 2) — the fix for cross-scene consistency.

Phase-1 measured 66.4% character consistency from a fixed seed + prompt alone.
This registry pushes it further the only CPU-cheap way (no IPAdapter/GPU): LOCK a
character's visual description AND a stable seed the first time it appears, then
reuse BOTH on every later scene that features it. Same seed + identical locked
description → the most consistent face/outfit SD1.5 can give on CPU.

Persisted per story to data/cache/characters/<story>.json so a character is stable
ACROSS runs (re-render → same Kade). Pure, deterministic, no network, no Math.random
(the seed is derived from sha1(story:name) so resume/replays are reproducible).

Used only when settings().character_memory is on (default True, but inert unless the
Storyboard Agent / layered path asks for a character).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from ..config import settings


class CharacterRef(BaseModel):
    """A locked, reusable character. First definition wins (so it never drifts)."""
    name: str                         # short token, e.g. "kade"
    description: str                  # LOCKED visual description (prepended to prompts)
    seed: int                         # stable generation seed (deterministic)
    style: str = ""                   # optional style suffix (e.g. anime look)


def _store(story_key: str) -> Path:
    d = settings().data_dir / "cache" / "characters"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in story_key)[:80]
    return d / f"{safe}.json"


def _stable_seed(story_key: str, name: str) -> int:
    """Deterministic seed from the story+name (reproducible across runs)."""
    h = hashlib.sha1(f"{story_key}:{name.lower()}".encode()).hexdigest()
    return int(h, 16) % (2 ** 31)


def _load(story_key: str) -> dict[str, CharacterRef]:
    p = _store(story_key)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
        return {k: CharacterRef(**v) for k, v in raw.items()}
    except Exception:                 # corrupt cache → start clean, never crash
        return {}


def _save(story_key: str, reg: dict[str, CharacterRef]) -> None:
    _store(story_key).write_text(
        json.dumps({k: v.model_dump() for k, v in reg.items()}, indent=2))


def get_or_create(story_key: str, name: str, description: str,
                  *, style: str = "") -> CharacterRef:
    """Return the LOCKED character for `name` in this story, creating it (and
    persisting) on first sight. Later calls IGNORE a changed description — the
    first definition is the canon, so the character stays consistent."""
    key = name.strip().lower()
    reg = _load(story_key)
    if key in reg:
        return reg[key]
    ref = CharacterRef(name=key, description=description.strip(),
                       seed=_stable_seed(story_key, key), style=style.strip())
    reg[key] = ref
    _save(story_key, reg)
    return ref


def character_prompt(ref: CharacterRef, action: str) -> str:
    """Build a scene prompt that LOCKS the character: description first (identity),
    then the per-scene action, then the locked style. Identity-first ordering keeps
    SD1.5 anchored on the same character across scenes."""
    bits = [ref.description.strip(), action.strip(), ref.style.strip()]
    return ", ".join(b for b in bits if b)
