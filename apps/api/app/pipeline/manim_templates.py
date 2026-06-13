"""
Parametric Manim templates. We do NOT let Claude write Manim code (unsafe + slow
+ flaky). Instead the Director picks a chart TYPE and the pipeline fills a vetted
template with numbers. v1 ships two: animated line trend and bar comparison —
which cover ~all finance/election visuals (CPI trend, polling bars, etc.).

Rendered at 1080x1920 vertical via the manim CLI. Returns the mp4 path.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
from pathlib import Path

# Self-contained scene file template. {payload} is injected JSON of values.
SCENE_PY = textwrap.dedent('''
    from manim import *
    import json
    config.frame_width = 9
    config.frame_height = 16
    config.pixel_width = 1080
    config.pixel_height = 1920

    DATA = json.loads(r"""{payload}""")

    class Chart(Scene):
        def construct(self):
            kind = DATA["kind"]
            title = Text(DATA.get("title", ""), font_size=42, weight=BOLD).to_edge(UP, buff=1.2)
            self.play(FadeIn(title))
            if kind == "line":
                self._line()
            else:
                self._bar()
            self.wait(0.5)

        def _line(self):
            ys = DATA["values"]
            ax = Axes(x_range=[0, len(ys) - 1, 1], y_range=[min(ys), max(ys), max(1,(max(ys)-min(ys))/4)],
                      x_length=7, y_length=8, tips=False).shift(DOWN*0.5)
            pts = [ax.coords_to_point(i, y) for i, y in enumerate(ys)]
            line = VMobject(color=YELLOW).set_points_as_corners(pts)
            self.play(Create(ax), run_time=1)
            self.play(Create(line), run_time=2)
            dot = Dot(pts[-1], color=RED)
            self.play(FadeIn(dot, scale=2))

        def _bar(self):
            labels = DATA["labels"]; vals = DATA["values"]
            chart = BarChart(values=vals, bar_names=labels, y_range=[0, max(vals)*1.1, max(1,max(vals)/4)],
                             x_length=7, y_length=9, bar_colors=["#16c784", "#ea3943", "#f5c518", "#1d4ed8"])
            self.play(Create(chart), run_time=2.2)
''')


async def render_chart(payload: dict, out: Path) -> str:
    if not shutil.which("manim"):
        raise RuntimeError("manim not installed")
    work = out.parent
    scene_file = work / f"{out.stem}_scene.py"
    scene_file.write_text(SCENE_PY.format(payload=json.dumps(payload)))

    proc = await asyncio.create_subprocess_exec(
        "manim", "render", "-ql", "--format", "mp4",
        "-o", out.name, "--media_dir", str(work / "_manim"),
        str(scene_file), "Chart",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    # locate the produced file (manim nests under media_dir) and move it
    produced = next((work / "_manim").rglob(out.name), None)
    if not produced:
        raise RuntimeError(f"manim produced nothing: {err.decode()[:400]}")
    shutil.move(str(produced), str(out))
    return str(out)


def payload_from_query(query: str, title: str) -> dict:
    """v1 heuristic: 'bar' in query -> bar chart, else line. Real numbers should
    come from the research step (Phase 2). Placeholder data until then."""
    q = query.lower()
    if "bar" in q or "vs" in q or "poll" in q:
        return {"kind": "bar", "title": title[:28],
                "labels": ["A", "B", "C"], "values": [48, 44, 8]}
    return {"kind": "line", "title": title[:28],
            "values": [2.1, 2.4, 2.9, 3.1, 3.4]}
