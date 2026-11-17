"""
Optional LLM copywriter for a countdown, through the factory's existing
Director backend (app/director/backends.py: the local `claude` CLI on the Max
plan by default). It writes ORIGINAL lines for the specific moments. It never
sees or reuses another channel's titles.

Returns None on any failure (no CLI, timeout, bad JSON, rule violation) so the
caller falls back to the deterministic templates. Everything it writes is
still reviewed before approval.
"""
from __future__ import annotations

import asyncio
import json
import re

SCHEMA = {
    "type": "object",
    "required": ["title", "hook", "captions", "outro"],
    "properties": {
        "title": {"type": "string", "maxLength": 60},
        "hook": {"type": "string", "maxLength": 22},
        "captions": {"type": "object", "required": ["5", "4", "3", "2", "1"],
                     "additionalProperties": {"type": "string", "maxLength": 32}},
        "outro": {"type": "string", "maxLength": 32},
    },
}
SYSTEM = (
    "You write on-screen copy for a family-friendly US YouTube Shorts channel "
    "that ranks five short {category} moments as a countdown from #5 to #1. "
    "Write ORIGINAL, playful, specific lines: react to what happens in each "
    "moment. Rules: US English; no profanity, slurs or mean jokes about people; "
    "no real people's names, brands or other channels; no emoji; no hashtags. "
    "title <= 60 chars and starts with 'Top 5' or a number; hook <= 22 chars, "
    "teases #1; each caption <= 32 chars; outro <= 32 chars and invites a comment."
)
BANNED = re.compile(r"\b(damn|hell|stupid|idiot|kill|dead)\b", re.I)
HASHTAG = re.compile(r"#[A-Za-z]")          # "#1" is a rank, "#shorts" is a hashtag


def _valid(d: dict) -> bool:
    try:
        caps = [d["captions"][k] for k in ("5", "4", "3", "2", "1")]
        lines = [d["title"], d["hook"], d["outro"], *caps]
    except (KeyError, TypeError):
        return False
    limits = [60, 22, 32] + [32] * 5
    return (all(isinstance(x, str) and 0 < len(x.strip()) <= n for x, n in zip(lines, limits))
            and not any(BANNED.search(x) or HASHTAG.search(x) for x in lines))


def write(category: str, subjects: dict[int, str], labels: dict[int, str],
          timeout: float = 120.0) -> dict | None:
    try:
        from ..director.backends import CLIBackend
    except ImportError:
        return None
    moments = "\n".join(
        f"#{r}: subject={subjects.get(r) or 'unknown'}; what happens: "
        f"{labels.get(r) or 'not described'}" for r in (5, 4, 3, 2, 1))
    try:
        raw = asyncio.run(asyncio.wait_for(
            CLIBackend().generate(SYSTEM.format(category=category.replace("_", " ")),
                                  f"The five moments:\n{moments}", SCHEMA), timeout))
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:                               # noqa: BLE001 — always fall back
        return None
    if not _valid(data):
        return None
    return {"title": data["title"].strip(), "hook": data["hook"].strip().upper(),
            "captions": {int(k): v.strip() for k, v in data["captions"].items()},
            "outro": data["outro"].strip(), "writer": "claude-cli"}
