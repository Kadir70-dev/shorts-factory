"""Validated finance templates extending the existing numpy/FFmpeg motion path."""
from __future__ import annotations

import hashlib
import json
import math
import random
import resource
import time
from dataclasses import dataclass
from pathlib import Path

from ..brand import theme_for
from ..brand import text as tx
from ..brand.raster import Canvas, ease_out_cubic, write_video
from ..schemas.scene import (MotionGraphicsRenderProvenance, Scene, SceneGraph,
                             StoryboardScene)
from . import dataviz, motiongfx

TEMPLATE_VERSION = "1.1.0"
TEMPLATES = (
    "stat_card", "bar_chart_comparison", "percentage_split", "timeline_events",
    "before_after", "revenue_profit_waterfall", "price_inflation",
    "document_highlight", "quote_card", "company_ecosystem",
)


@dataclass(frozen=True)
class MotionSpec:
    template: str
    title: str
    values: tuple[float, ...]
    prefixes: tuple[str, ...]
    suffixes: tuple[str, ...]
    labels: tuple[str, ...]
    source_text: str
    clarity_reason: str


def _parsed(beat: StoryboardScene) -> list[tuple[float, str, str]]:
    return [value for raw in beat.financial_numbers
            if (value := dataviz.parse_number(raw)) is not None]


def map_template(beat: StoryboardScene) -> MotionSpec | None:
    """Use only validated storyboard facts; never synthesize chart values."""
    beat = StoryboardScene.model_validate(beat.model_dump())
    text = f"{beat.narration} {beat.visual_objective}".lower()
    parsed = _parsed(beat)
    values = tuple(value for value, _, _ in parsed)
    prefixes = tuple(prefix for _, prefix, _ in parsed)
    suffixes = tuple(suffix for _, _, suffix in parsed)
    entities = tuple(dict.fromkeys(
        [beat.primary_entity, *beat.secondary_entities, beat.company, beat.location]))
    entities = tuple(value for value in entities if value)
    title = (beat.overlay_text[0] if beat.overlay_text else
             beat.company or beat.primary_entity or beat.narration)[:56]
    labels = tuple(beat.financial_numbers[:4])
    source = f"{beat.company} {beat.year or ''}".strip()

    # Curved compounding over time materially benefits from the spatial camera
    # language in Phase 4; do not flatten it into a generic single stat card.
    if values and any(word in text for word in ("compound", "compounded", "cagr")):
        return None

    if any(word in text for word in ("filing", "document", "sec report", "annual report")) \
            and (beat.company or beat.year or values):
        template, reason = "document_highlight", "A sourced document excerpt is clearer in 2D."
        labels = tuple(filter(None, (beat.company, str(beat.year or ""), *labels)))
    elif any(mark in beat.narration for mark in ('"', "“", "”")) or \
            any(word in text for word in (" said ", " says ", " quote ")):
        template, reason = "quote_card", "The attributed statement is the visual fact."
        labels = (beat.narration.strip(' "“”'), source)
    elif any(word in text for word in ("ecosystem", "subsidiar", "supplier", "platform")) \
            and len(entities) >= 3:
        template, reason = "company_ecosystem", "Entity relationships read faster as a 2D map."
        labels = entities[:6]
    elif "waterfall" in text or ("revenue" in text and "profit" in text and len(values) >= 2):
        template, reason = "revenue_profit_waterfall", "Sequential contributions need a waterfall."
    elif "inflation" in text and "price" in text and len(values) >= 2:
        template, reason = "price_inflation", "Two real price measures need a direct comparison."
    elif any(word in text for word in ("before", "after", "from", "versus")) and len(values) == 2:
        template, reason = "before_after", "Two states are cheaper and clearer as flat panels."
    elif beat.year and any(word in text for word in ("timeline", "since", "history", "milestone")):
        template, reason = "timeline_events", "Event order needs a lightweight timeline."
        labels = tuple(filter(None, (str(beat.year), *beat.secondary_entities,
                                     beat.company or beat.primary_entity)))
        values = values or (float(beat.year),)
        prefixes, suffixes = prefixes or ("",), suffixes or ("",)
    elif any(word in text for word in ("ownership", "stake", "split", "owns")) and values:
        template, reason = "percentage_split", "A flat split is clearer than a 3D ownership scene."
    elif len(values) >= 2:
        template, reason = "bar_chart_comparison", "A 2D comparison communicates equal facts cheaper."
    elif len(values) == 1:
        template, reason = "stat_card", "One real value needs a focused mobile stat card."
    else:
        return None
    return MotionSpec(template, title, values, prefixes, suffixes,
                      labels or entities[:4], source, reason)


def dimensions(quality: str) -> tuple[int, int]:
    return (360, 640) if quality == "preview" else (1080, 1920)


def cache_key(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
              spec: MotionSpec, quality: str, seed: int) -> str:
    theme = theme_for(graph, "motion_graphics")
    payload = json.dumps({
        "version": TEMPLATE_VERSION, "template": spec.template,
        "beat": beat.model_dump(mode="json"), "duration": scene.duration_sec,
        "fps": graph.fps, "quality": quality, "seed": seed,
        "brand": theme.fingerprint,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _format(value: float, prefix: str = "", suffix: str = "") -> str:
    for scale, tag in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= scale:
            return f"{prefix}{value / scale:.1f}{tag}{suffix}".replace(".0", "")
    return f"{prefix}{value:,.1f}{suffix}".replace(".0", "")


def _filters(theme, spec: MotionSpec, w: int, h: int, duration: float) -> list[str]:
    pad = int(w * .065)
    title_size = theme.size("chart_title", h)
    filters = tx.drawtext_block(
        tx.wrap(theme.display.apply_case(spec.title), title_size, w, max_lines=2),
        font=theme.display.path, size=title_size, color=theme.ff("ink"),
        x=str(pad), y_top=int(h * .11), shadow=3)
    value_size = max(theme.size("headline", h), int(h * .065))
    if spec.template in {"stat_card", "percentage_split"} and spec.values:
        filters.append(tx.drawtext(
            _format(spec.values[0], spec.prefixes[0] if spec.prefixes else "",
                    spec.suffixes[0] if spec.suffixes else ""),
            font=theme.mono.path, size=theme.size("stat_number", h),
            color=theme.ff("primary"), x="(w-text_w)/2", y=str(int(h * .39)),
            alpha=tx.fade_alpha(.15, duration + 1, .25), shadow=4))
    elif spec.template == "quote_card" and spec.labels:
        filters += tx.drawtext_block(
            tx.wrap(f'“{spec.labels[0]}”', theme.size("headline", h), w,
                    max_lines=5), font=theme.display.path,
            size=theme.size("headline", h), color=theme.ff("ink"),
            y_top=int(h * .30), shadow=4)
    else:
        for i, value in enumerate(spec.values[:4]):
            x = int(w * (.18 + .22 * i))
            filters.append(tx.drawtext(
                _format(value, spec.prefixes[i] if i < len(spec.prefixes) else "",
                        spec.suffixes[i] if i < len(spec.suffixes) else ""),
                font=theme.mono.path, size=value_size, color=theme.ff("ink"),
                x=f"{x}-text_w/2", y=str(int(h * .65)), shadow=3))
    for i, label in enumerate(spec.labels[:4]):
        filters.append(tx.drawtext(
            str(label)[:28], font=theme.body.path, size=theme.size("source", h),
            color=theme.ff("ink_dim"), x=str(pad),
            y=str(int(h * (.72 + i * .035))), shadow=2))
    return filters


def _frames(theme, spec: MotionSpec, w: int, h: int, fps: int,
            duration: float, seed: int):
    count = max(1, round(fps * duration))
    rng = random.Random(seed)
    treatment = motiongfx.brand_treatment(theme, rng)
    base = motiongfx._bg_base(theme, w, h)
    for frame in range(count):
        t = frame / fps
        p = ease_out_cubic(min(1.0, t / max(.25, duration * .62)))
        c = base.copy()
        motiongfx._draw_treatment(c, theme, treatment, t, w, h, rng)
        top, bottom = h * .29, h * .64
        if spec.template == "stat_card":
            c.rect(w * .09, top, w * .82, bottom - top, theme.rgb("bg_soft"), .94, w * .03)
            c.rect(w * .09, top, w * .82 * p, h * .012, theme.rgb("primary"), 1, 3)
        elif spec.template in {"bar_chart_comparison", "price_inflation"}:
            maximum = max((abs(v) for v in spec.values), default=1) or 1
            n = max(1, len(spec.values)); bw = w * .66 / n
            for i, value in enumerate(spec.values):
                bh = (bottom - top) * .82 * abs(value) / maximum * p
                c.rect(w * .17 + i * bw, bottom - bh, bw * .68, bh,
                       theme.rgb("primary" if i == 0 else "secondary"), .95, 5)
        elif spec.template == "percentage_split":
            value = min(100, max(0, spec.values[0]))
            c.ring(w / 2, h * .47, w * .24, w * .055, theme.rgb("grid"), .8)
            c.ring(w / 2, h * .47, w * .24, w * .055, theme.rgb("primary"), 1,
                   sweep=value / 100 * p)
        elif spec.template == "timeline_events":
            from ..config import settings
            branded = settings().brand_identity_enabled
            line_key = theme.timeline.get("active_color", "primary") if branded else "primary"
            line_px = float(theme.timeline.get("line_width_px", 8)) * w / 1080 \
                if branded else w * .018
            y = h * .48; c.segment(w * .12, y, w * (.12 + .76 * p), y,
                                   line_px, theme.rgb(line_key))
            for i in range(min(5, max(2, len(spec.labels)))):
                x = w * (.15 + .7 * i / max(1, min(4, len(spec.labels) - 1)))
                marker = theme.timeline.get("active_color", "primary") if branded else "primary"
                c.circle(x, y, w * .025, theme.rgb("secondary" if i else marker))
        elif spec.template == "before_after":
            for i in range(2):
                x = w * (.08 + .46 * i); y = top + (1 - p) * 25
                c.rect(x, y, w * .38, bottom - top, theme.rgb("bg_soft"), .96, 8)
                c.rect(x, y, w * .38, h * .012,
                       theme.rgb("ink_dim" if i == 0 else "positive"), p, 4)
            c.segment(w * .45, h * .47, w * (.45 + .10 * p), h * .47,
                      w * .015, theme.rgb("primary"))
        elif spec.template == "revenue_profit_waterfall":
            maximum = max((abs(v) for v in spec.values), default=1) or 1
            acc = bottom
            for i, value in enumerate(spec.values[:4]):
                bh = (bottom - top) * .62 * abs(value) / maximum * p
                x = w * (.12 + i * .2)
                c.rect(x, acc - bh, w * .13, bh,
                       theme.rgb("positive" if value >= 0 else "negative"), .95, 4)
                acc -= bh * .35
        elif spec.template == "document_highlight":
            c.rect(w * .13, top, w * .74, bottom - top, (235, 238, 242), p, 6)
            for i in range(7):
                c.rect(w * .20, top + h * (.04 + i * .035), w * (.50 - i % 3 * .06),
                       h * .006, theme.rgb("grid"), .65)
            c.rect(w * .18, top + h * .145, w * .58 * p, h * .045,
                   theme.rgb("primary"), .55, 3)
        elif spec.template == "quote_card":
            c.rect(w * .08, top, w * .84, bottom - top, theme.rgb("bg_soft"), .96, 10)
            c.rect(w * .08, top, w * .018, (bottom - top) * p, theme.rgb("primary"), 1, 3)
        elif spec.template == "company_ecosystem":
            cx, cy = w / 2, h * .47
            c.circle(cx, cy, w * .10, theme.rgb("primary"), p)
            nodes = max(3, min(6, len(spec.labels)))
            for i in range(nodes):
                angle = i / nodes * math.tau
                x, y = cx + math.cos(angle) * w * .30, cy + math.sin(angle) * h * .15
                c.segment(cx, cy, x, y, w * .009, theme.rgb("grid"), p)
                c.circle(x, y, w * .055, theme.rgb("secondary"), p)
        yield c


async def render(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
                 quality: str = "final", seed: int = 0
                 ) -> MotionGraphicsRenderProvenance:
    beat = StoryboardScene.model_validate(beat.model_dump())
    quality = quality if quality in ("preview", "final") else "final"
    spec = map_template(beat)
    if spec is None:
        raise ValueError("storyboard beat has no validated 2D finance mapping")
    theme = theme_for(graph, "motion_graphics")
    w, h = dimensions(quality)
    key = cache_key(graph, scene, beat, spec, quality, seed)
    out = settings_data_dir() / "cache" / "finance_motion" / key / "render.mp4"
    base = dict(scene_id=scene.id, storyboard_scene_id=beat.scene_id,
                template=spec.template, template_version=TEMPLATE_VERSION,
                cache_key=key, seed=seed, fps=graph.fps, width=w, height=h,
                quality=quality, brand_id=graph.brand_id,
                brand_fingerprint=theme.fingerprint,
                existing_decision=scene.visual.strategy, clarity_reason=spec.clarity_reason)
    if out.is_file() and out.stat().st_size:
        return MotionGraphicsRenderProvenance(**base, status="cache_hit",
            render_path=str(out), render_ms=0, peak_rss_mb=0)
    started = time.perf_counter()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        filters = _filters(theme, spec, w, h, scene.duration_sec)
        await write_video(_frames(theme, spec, w, h, graph.fps,
                                  scene.duration_sec, seed), w, h, graph.fps, out,
                          vf=",".join(filters) if filters else None)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        return MotionGraphicsRenderProvenance(**base, status="rendered",
            render_path=str(out), render_ms=(time.perf_counter() - started) * 1000,
            peak_rss_mb=rss)
    except Exception as exc:
        out.unlink(missing_ok=True)
        return MotionGraphicsRenderProvenance(**base, status="unresolved",
            render_ms=(time.perf_counter() - started) * 1000,
            peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            error=f"{type(exc).__name__}: {str(exc)[:240]}")


def settings_data_dir() -> Path:
    # Local import avoids pulling Settings into module import paths used by tests.
    from ..config import settings
    return settings().data_dir
