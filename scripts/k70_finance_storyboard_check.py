#!/usr/bin/env python3
"""Check a K70 Finance Shorts storyboard before editor/render hand-off.

This is an editorial structure gate, NOT a claim that licensed footage or actual
YouTube retention has been validated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


def verify(story: dict) -> list[str]:
    problems = []
    beats = story.get("beats", [])
    if not beats:
        return ["no beats"]
    end = 0.0
    kinds = []
    roles = []
    for i, beat in enumerate(beats):
        start = float(beat["start"])
        stop = float(beat["end"])
        if abs(start - end) > .001:
            problems.append(f"beat {i}: timeline gap/overlap at {start}s; expected {end}s")
        if not (1.0 <= stop - start <= 5.0):
            problems.append(f"beat {i}: visual duration must be between 1 and 5 seconds")
        if not beat.get("narration", "").strip():
            problems.append(f"beat {i}: empty narration")
        end = stop
        kinds.append(beat.get("visual"))
        roles.append(beat.get("role"))
    if not (30 <= end <= 45):
        problems.append("Short must be 30–45 seconds")
    if beats[0].get("role") != "hook" or beats[0]["end"] > 3:
        problems.append("hook must finish inside first 3 seconds")
    if "newspaper" not in kinds or not any("chart" in str(k) or k == "counter" for k in kinds):
        problems.append("must have newspaper source card plus chart/counter")
    if kinds.count("footage") < 3:
        problems.append("need at least 3 real-footage beats")
    if "payoff" not in roles or roles[-1] != "engage":
        problems.append("need payoff and meaningful closing question")
    if not story.get("fact_sources"):
        problems.append("no fact sources")
    for source in story.get("fact_sources", []):
        u = urlparse(source)
        if u.scheme != "https" or not u.netloc:
            problems.append("non-HTTPS or invalid fact source: " + source)
    try:
        from datetime import date
        brief = story["news"]
        date.fromisoformat(brief["published"])
        u = urlparse(brief["source_url"])
        if u.scheme != "https" or not u.netloc:
            problems.append("invalid newspaper source")
        if not brief["headline"] or not brief["publisher"]:
            problems.append("newspaper metadata missing")
    except (KeyError, TypeError, ValueError):
        problems.append("missing or invalid newspaper metadata")
    return problems


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parents[1] / "data/k70_finance_shorts/storyboard_examples.json")
    data = json.loads(src.read_text())
    total = 0
    for story in data["stories"]:
        err = verify(story)
        if err:
            print(f"FAILED {story['id']}: {'; '.join(err)}")
            total += len(err)
        else:
            print(f"PASS {story['id']}: {story['beats'][-1]['end']}s, headline + footage + charts + question")
    if total:
        raise SystemExit(1)
    print("Editorial structure validated. Rights, source facts, real footage and video QA still required.")


if __name__ == "__main__":
    main()
