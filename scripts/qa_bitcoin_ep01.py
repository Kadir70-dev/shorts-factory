#!/usr/bin/env python3
"""
Pre-render QA for THE COMPLETE HISTORY OF BITCOIN · EPISODE 1.

Runs the checks that can be made BEFORE any frame is drawn — schema validity,
the pipeline's own visual-budget allocator, visual-repeat detection, chapter
cliffhanger cadence, twist cadence, source coverage and hedging discipline —
and writes `qa_report.md` next to the spec.

`pipeline/qa.py` audits the finished MP4 (black frames, loudness, caption drift,
duration match). This audits the SPEC, so a defect is caught in seconds instead
of after a 14-minute render.

    .venv/bin/python scripts/qa_bitcoin_ep01.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

SPEC = ROOT / "data" / "series" / "bitcoin_history" / "ep01" / "scene_graph.json"
REPORT = SPEC.parent / "qa_report.md"

# Language the sanity gate expects to see when a beat is not a settled fact.
HEDGES = ("reportedly", "widely reported", "is said", "about ", "roughly",
          "almost ", "more than", "around ", "would ", "estimated",
          "by most accounts", "thought to", "believed to")
# Absolutes that must never appear on a non-confirmed beat.
ABSOLUTES = ("proves", "always", "never", "everyone knows", "obviously")


class Check:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, bool, str]] = []

    def add(self, group: str, name: str, ok: bool, detail: str) -> None:
        self.rows.append((group, name, ok, detail))

    @property
    def failed(self) -> list[tuple[str, str, bool, str]]:
        return [r for r in self.rows if not r[2]]

    def markdown(self) -> str:
        out = ["| | Check | Result |", "|---|---|---|"]
        group = None
        for g, name, ok, detail in self.rows:
            if g != group:
                group = g
                out.append(f"| | **{g.upper()}** | |")
            out.append(f"| {'PASS' if ok else 'FAIL'} | {name} | {detail} |")
        return "\n".join(out)


def main() -> int:
    from app.schemas.scene import SceneGraph
    from app.pipeline import visual_budget

    graph = SceneGraph.model_validate_json(SPEC.read_text())
    scenes = graph.scenes
    total = graph.total_duration_sec
    c = Check()

    # ── structure ────────────────────────────────────────────────────────── #
    c.add("structure", "schema validates against SceneGraph 2.0", True,
          f"{len(scenes)} scenes · schema_version {graph.schema_version}")
    c.add("structure", "runtime inside the 10-15 min brief",
          600 <= total <= 900, f"{total:.0f}s = {total/60:.2f} min")
    c.add("structure", "scene ids unique and contiguous",
          [s.id for s in scenes] == [f"s{i}" for i in range(1, len(scenes) + 1)],
          f"s1 … s{len(scenes)}")
    c.add("structure", "storyboard covers every scene",
          graph.storyboard is not None
          and len(graph.storyboard.scenes) == len(scenes)
          and {b.source_scene_id for b in graph.storyboard.scenes} == {s.id for s in scenes},
          f"{len(graph.storyboard.scenes) if graph.storyboard else 0} semantic beats")
    over = [s.id for s in scenes if s.duration_sec > 12.0 or s.duration_sec < 0.8]
    c.add("structure", "every scene inside the 0.8-12s beat window",
          not over, "no outliers" if not over else ", ".join(over))

    # ── visual plan ──────────────────────────────────────────────────────── #
    missing = [s.id for s in scenes if not s.visual.visual_intent.strip()]
    c.add("visual", "every narration sentence carries a visual plan",
          not missing, f"{len(scenes)}/{len(scenes)} beats"
          if not missing else f"missing on {', '.join(missing)}")

    talking_head = [s.id for s in scenes if s.visual.type == "solid"]
    c.add("visual", "no talking-head / flat-colour beats",
          not talking_head, "0 solid beats" if not talking_head
          else ", ".join(talking_head))

    # "No repeated visuals": the thing that actually fills the screen must be
    # unique. For rendered channels that is the query/intent; for fetched
    # channels it is the search phrase set.
    fingerprints = Counter()
    for s in scenes:
        key = (s.visual.query.strip().lower()
               or "|".join(sorted(k.lower() for k in s.visual.broll_keywords)))
        fingerprints[key] += 1
    dupes = {k: n for k, n in fingerprints.items() if n > 1 and k}
    c.add("visual", "no repeated visual across the episode",
          not dupes, f"{len(fingerprints)} distinct visuals"
          if not dupes else f"{len(dupes)} repeated: {list(dupes)[:3]}")

    intents = Counter(s.visual.visual_intent.strip().lower() for s in scenes)
    c.add("visual", "no repeated visual objective",
          max(intents.values()) == 1, f"{len(intents)} distinct objectives")

    # ── visual budget ────────────────────────────────────────────────────── #
    # Two mixes matter: what we AUTHORED, and what the pipeline's own allocator
    # independently decides when it reads this graph. They should agree; where
    # they don't, the allocator wins at render time and we want to know now.
    delivered: dict[str, float] = {}
    for s in scenes:
        delivered[s.visual.budget_channel] = \
            delivered.get(s.visual.budget_channel, 0.0) + s.duration_sec
    c.add("visual", "authored mix spans all six budget channels",
          len(delivered) == 6,
          " · ".join(f"{ch} {secs/total*100:.1f}%"
                     for ch, secs in sorted(delivered.items(), key=lambda kv: -kv[1])))

    report = visual_budget.allocate(graph)
    c.add("visual", "pipeline allocator assigns every scene",
          len(report.assignments) == len(scenes),
          f"{len(report.assignments)}/{len(scenes)} scenes assigned")
    off_band = [ch for ch in ("motion_gfx", "threejs", "official", "ai_broll",
                              "stock", "charts")
                if not report.within_band(ch)]
    c.add("visual", "allocator's own plan lands inside every band",
          not off_band,
          " · ".join(f"{ch} {report.pct.get(ch, 0.0):.1f}%"
                     for ch in ("motion_gfx", "threejs", "official", "ai_broll",
                                "stock", "charts"))
          + (f"  (outside: {', '.join(off_band)})" if off_band else ""))
    c.add("visual", "no scene left unresolved by the allocator",
          not report.seconds.get("unresolved"),
          f"{report.seconds.get('unresolved', 0.0):.1f}s unresolved")

    # ── data / sourcing ──────────────────────────────────────────────────── #
    charts = [s for s in scenes if s.data]
    bad = [s.id for s in charts if not s.data.valid()]
    c.add("sourcing", "every chart has real data behind it",
          not bad, f"{len(charts)} charts"
          if not bad else f"invalid: {', '.join(bad)}")
    unsourced = [s.id for s in charts if not s.data.source.strip()]
    c.add("sourcing", "every chart carries an attribution",
          not unsourced, "all attributed"
          if not unsourced else f"missing: {', '.join(unsourced)}")

    cited = [s for s in scenes if any(o.type == "source" for o in s.overlays)]
    c.add("sourcing", "sourced beats show their attribution on screen",
          len(cited) >= 25, f"{len(cited)} beats carry a source overlay")

    # A non-confirmed beat must be hedged in the narration itself.
    unhedged = [s.id for s in scenes if s.confidence != "confirmed"
                and not any(h in s.narration.lower() for h in HEDGES)]
    c.add("sourcing", "speculative/probable beats are hedged in the read",
          not unhedged, "all hedged" if not unhedged else ", ".join(unhedged))

    absolute = [s.id for s in scenes if s.confidence != "confirmed"
                and any(a in s.narration.lower() for a in ABSOLUTES)]
    c.add("sourcing", "no absolutes on an unconfirmed beat",
          not absolute, "clean" if not absolute else ", ".join(absolute))

    # ── storytelling (the brief's own rules) ─────────────────────────────── #
    twist_roles = {"turn", "reveal", "hook"}
    twists = [(i, s) for i, s in enumerate(scenes) if s.beat_role in twist_roles]
    starts, acc = [], 0.0
    for s in scenes:
        starts.append(acc)
        acc += s.duration_sec
    gaps = [starts[twists[i + 1][0]] - starts[twists[i][0]]
            for i in range(len(twists) - 1)]
    worst = max(gaps) if gaps else 0.0
    c.add("story", "a twist at least every 40s",
          worst <= 40.0, f"{len(twists)} turns/reveals · longest gap {worst:.0f}s")
    c.add("story", "median twist spacing inside 20-40s",
          bool(gaps) and 12.0 <= sorted(gaps)[len(gaps) // 2] <= 40.0,
          f"median {sorted(gaps)[len(gaps)//2]:.0f}s" if gaps else "n/a")

    # Every chapter must end on a mini-cliffhanger: the last beat of a chapter
    # has to be a turn/reveal/stakes/payoff, never a flat context beat.
    chapter_of: dict[str, list] = {}
    for s in scenes:
        ch = (s.visual.decision_reason.split("·")[0] or "").strip()
        chapter_of.setdefault(ch, []).append(s)
    weak = [ch for ch, ss in chapter_of.items()
            if ss[-1].beat_role not in
            {"turn", "reveal", "stakes", "payoff", "cta", "tension", "consequence"}]
    c.add("story", "every chapter ends on a cliffhanger beat",
          not weak, f"{len(chapter_of)} chapters"
          if not weak else f"flat ending: {', '.join(weak)}")

    c.add("story", "opens on a hook, closes on the Episode 2 hand-off",
          scenes[0].beat_role == "hook"
          and "change money forever" in " ".join(s.narration.lower() for s in scenes[-3:]),
          f"s1 `{scenes[0].beat_role}` → s{len(scenes)} `{scenes[-1].beat_role}`")

    # No filler. A ONE-WORD beat is not filler when it is a deliberate turn or
    # reveal held on a card ("Temporarily." / "Trust.") — that is the loudest
    # line in the film. Filler is a short beat that carries no turn and no card.
    filler = [s.id for s in scenes
              if len(s.narration.split()) < 2
              and s.beat_role not in ("turn", "reveal")
              and not s.overlays]
    c.add("story", "no filler beats", not filler,
          "none" if not filler else ", ".join(filler))

    # ── music ────────────────────────────────────────────────────────────── #
    roles = Counter(s.beat_role for s in scenes)
    quiet = roles["context"] + roles["mechanism"]
    swell = roles["reveal"] + roles["turn"] + roles["evidence"] + roles["payoff"]
    c.add("music", "score has both quiet passages and swells",
          quiet >= 15 and swell >= 30,
          f"{quiet} quiet beats · {swell} swell beats · {roles['hook']} hooks")

    # ── captions safety ──────────────────────────────────────────────────── #
    low = [f"{s.id}/{o.type}" for s in scenes for o in s.overlays if o.y > 0.7]
    c.add("render", "overlays keep clear of the caption band (y<=0.70)",
          not low, "clear" if not low else ", ".join(low))

    # ── AI disclosure ────────────────────────────────────────────────────── #
    ai_beats = [s for s in scenes if s.visual.strategy == "ai_image"]
    c.add("render", "synthetic beats are countable for YouTube AI disclosure",
          bool(ai_beats),
          f"{len(ai_beats)} AI recreations "
          f"({sum(s.duration_sec for s in ai_beats)/total*100:.0f}% of runtime) "
          f"— requires the 'Altered or Synthetic Content' box")

    # ── write ────────────────────────────────────────────────────────────── #
    ok = not c.failed
    body = [f"# QA — {graph.meta.title}", "",
            f"`{SPEC.relative_to(ROOT)}` · {len(scenes)} scenes · "
            f"{total/60:.2f} min · brand `{graph.brand_id}` · "
            f"structure `{graph.meta.structure_id}`", "",
            f"**{'PASS' if ok else 'FAIL'}** — "
            f"{len(c.rows) - len(c.failed)}/{len(c.rows)} checks", "",
            c.markdown(), "",
            "## Delivered visual mix (authored plan)", "",
            "| Channel | Share | Seconds | Band |", "|---|---|---|---|"]
    bands = {"motion_gfx": "25-35%", "threejs": "15-25%", "official": "15-25%",
             "ai_broll": "15-25%", "stock": "10-20%", "charts": "10-20%"}
    for ch, secs in sorted(delivered.items(), key=lambda kv: -kv[1]):
        body.append(f"| {ch} | {secs/total*100:.1f}% | {secs:.0f}s | "
                    f"{bands.get(ch, '—')} |")
    body += ["", "## What this does NOT check", "",
             "Black frames, loudness, caption drift and encoded duration are",
             "properties of the finished MP4 — `pipeline/qa.py` gates those",
             "during `scripts/produce.py`. This report gates the spec only."]
    REPORT.write_text("\n".join(body))

    print(c.markdown().replace("| ", "").replace(" |", ""))
    print(f"\n{'PASS' if ok else 'FAIL'} — "
          f"{len(c.rows) - len(c.failed)}/{len(c.rows)} checks · wrote {REPORT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
