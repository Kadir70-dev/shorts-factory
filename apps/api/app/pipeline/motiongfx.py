"""
Motion graphics and branded plates — tiers 2 and 4 of the visual ladder.

These exist so that "no good footage of this exact subject" stops meaning "drop in
a stock clip of a businessman shaking hands". A beat about an abstract claim is
better served by the claim itself, moving, in the channel's type system, than by
generic stock that says nothing and looks like every other channel's B-roll.

Two forms:

  kinetic()  — TIER 2. The beat's key line built on screen over a live branded
               background: a moving grid, drifting accent geometry, a rule that
               tracks under the text. Used for claims, definitions, mechanisms and
               contrasts — the beats where the words ARE the content.

  plate()    — TIER 4. A branded background with no message of its own: layered
               gradients and slow geometry in the channel palette. It is what a
               beat falls back to instead of unrelated footage, so a failed asset
               lookup still produces something that belongs to this channel.

Both render at full frame with numpy + ffmpeg, same as the chart engine, so they
cost nothing beyond CPU and depend on nothing beyond ffmpeg.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
from pathlib import Path

from ..brand import text as tx
from ..brand.raster import Canvas, ease_out_cubic, write_video
from ..brand.theme import BrandTheme
from ..config import settings
from .util import visual_cache_path, visual_cache_store

# Bump when the drawing code changes shape: it namespaces every cache entry, so
# old frames can never be served for new geometry.
_CACHE_VERSION = 1


def cache_key(form: str, theme: BrandTheme, w: int, h: int, fps: int,
              duration: float, seed: int, treatment: str, **content: object) -> str:
    """Everything the drawn pixels depend on.

    `seed` is part of the key because the treatments are driven by a seeded RNG:
    two beats with the same text and a different seed are deliberately different
    images, and must not collide.
    """
    body = json.dumps({
        "version": _CACHE_VERSION, "form": form, "brand": theme.fingerprint,
        "w": w, "h": h, "fps": fps, "duration": round(duration, 4),
        "seed": seed, "treatment": treatment, **content,
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _cached(key: str, out: Path) -> Path | None:
    hit = visual_cache_path("motiongfx", key)
    if hit.is_file() and hit.stat().st_size > 1024:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hit, out)
        return out
    return None

# Background treatments. Rotated per beat so consecutive graphic scenes in one
# short don't share a look.
TREATMENTS = ["grid_drift", "rule_field", "orbit", "strata", "pulse_dots"]


def brand_treatment(theme: BrandTheme, rng: random.Random,
                    requested: str = "") -> str:
    if requested:
        return requested
    if settings().brand_identity_enabled:
        configured = str(theme.background.get("texture", ""))
        mapped = {"fine_grid": "grid_drift", "rules": "rule_field",
                  "strata": "strata", "dots": "pulse_dots"}.get(configured)
        if mapped:
            return mapped
    return rng.choice(TREATMENTS)


# --------------------------------------------------------------------------- #
# Backgrounds
# --------------------------------------------------------------------------- #
def _bg_base(theme: BrandTheme, w: int, h: int) -> Canvas:
    c = Canvas(w, h, bg=theme.rgb("bg"), bg_alpha=1.0)
    c.vgradient(0, 0, w, h, theme.rgb("bg_soft"), theme.rgb("bg"), 0.70, 0.0)
    c.vgradient(0, int(h * 0.62), w, int(h * 0.38), theme.rgb("bg"), (0, 0, 0),
                0.0, 0.45)
    return c


def _draw_treatment(c: Canvas, theme: BrandTheme, kind: str, t: float,
                    w: int, h: int, rng: random.Random) -> None:
    """One frame of the moving background. Kept deliberately slow — background
    motion that competes with the text is worse than a still."""
    grid = theme.rgb("grid")
    accent = theme.rgb("primary")

    if kind == "grid_drift":
        step = h // 18
        offset = (t * 14) % step
        for i in range(-1, h // step + 2):
            c.rect(0, i * step + offset, w, 2, grid, alpha=0.55)
        for j in range(0, w // step + 2):
            c.rect(j * step - offset * 0.4, 0, 2, h, grid, alpha=0.30)

    elif kind == "rule_field":
        for i in range(11):
            phase = (t * 0.16 + i * 0.11) % 1.0
            y = h * (0.08 + 0.082 * i)
            length = w * (0.22 + 0.55 * abs(math.sin(phase * math.pi)))
            x = w * 0.06 if i % 2 == 0 else w - w * 0.06 - length
            c.rect(x, y, length, 3, grid, alpha=0.70)

    elif kind == "orbit":
        # Rings are the most expensive primitive here (large bounding boxes), so
        # two of them, not three — the treatment reads the same and renders in a
        # third of the time.
        cx, cy = w * 0.5, h * 0.45
        for i, r in enumerate((h * 0.19, h * 0.31)):
            c.ring(cx, cy, r, 2.5, grid, alpha=0.55)
            ang = (t * (0.05 + 0.03 * i) + i * 0.33) % 1.0
            px = cx + r * math.sin(ang * 2 * math.pi)
            py = cy - r * math.cos(ang * 2 * math.pi)
            c.circle(px, py, 10 - i * 2, accent, alpha=0.85)

    elif kind == "strata":
        for i in range(9):
            phase = math.sin(t * 0.45 + i * 0.8)
            y = h * (0.12 + 0.09 * i) + phase * 9
            c.rect(w * 0.04, y, w * 0.92, 2, grid,
                   alpha=0.34 + 0.26 * abs(phase))

    else:                                       # pulse_dots
        cols, rows = 9, 16
        for i in range(cols):
            for j in range(rows):
                x = w * (0.08 + 0.84 * i / (cols - 1))
                y = h * (0.06 + 0.88 * j / (rows - 1))
                pulse = 0.5 + 0.5 * math.sin(t * 1.6 + (i + j) * 0.5)
                c.circle(x, y, 2.8 + 1.8 * pulse, grid,
                         alpha=0.32 + 0.34 * pulse)


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
async def plate(theme: BrandTheme, out: Path, w: int, h: int, fps: int,
                duration: float, seed: int = 0, treatment: str = "") -> Path:
    """TIER 4 — a branded background with no message. The floor a beat lands on
    instead of unrelated stock footage."""
    key = cache_key("plate", theme, w, h, fps, duration, seed, treatment)
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    kind = brand_treatment(theme, rng, treatment)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))

    def gen():
        for f in range(frames):
            c = base.copy()
            _draw_treatment(c, theme, kind, f / fps, w, h, rng)
            yield c

    result = await write_video(gen(), w, h, fps, out)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result


async def kinetic(theme: BrandTheme, out: Path, w: int, h: int, fps: int,
                  duration: float, headline: str, kicker: str = "",
                  source: str = "", seed: int = 0, treatment: str = "") -> Path:
    """TIER 2 — the beat's key line, built on screen over a live branded field.

    Lines arrive in sequence rather than all at once: the eye reads the first
    while the second is still arriving, which is what makes kinetic type feel
    authored instead of like a slide.
    """
    key = cache_key("kinetic", theme, w, h, fps, duration, seed, treatment,
                    headline=headline, kicker=kicker, source=source)
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    kind = brand_treatment(theme, rng, treatment)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))

    size = theme.size("headline", h)
    lines = tx.wrap(theme.display.apply_case(headline), size, w, max_lines=4)
    leading = int(size * 1.20)
    block_h = leading * len(lines)
    # Centre the block on the upper-middle third: high enough to clear the caption
    # band at ~0.775, low enough that the frame doesn't read as top-heavy.
    y_top = int(h * 0.44 - block_h / 2)

    # per-line stagger, finishing comfortably before the beat ends
    build = min(1.05, max(0.5, duration * 0.45))
    step = build / max(1, len(lines))
    rule_y = y_top + block_h + int(size * 0.42)

    def gen():
        for f in range(frames):
            t = f / fps
            c = base.copy()
            _draw_treatment(c, theme, kind, t, w, h, rng)
            # an accent rule that grows under the text as the lines land
            prog = ease_out_cubic(t / max(0.3, build))
            rule_w = w * 0.60 * prog
            c.rect((w - rule_w) / 2, rule_y, rule_w, 5, theme.rgb("primary"),
                   alpha=1.0, radius=3)
            yield c

    filters: list[str] = []
    if kicker:
        ksize = theme.size("lower_third", h)
        filters.append(tx.drawtext(
            theme.body.apply_case(kicker), font=theme.body.path, size=ksize,
            color=theme.ff("primary"), x="(w-text_w)/2",
            y=str(max(0, y_top - int(ksize * 2.0))),
            alpha=tx.fade_alpha(0.05, duration + 1.0, fade=0.28), shadow=3))

    for i, line in enumerate(lines):
        start = i * step
        filters.append(tx.drawtext(
            line, font=theme.display.path, size=size, color=theme.ff("ink"),
            x="(w-text_w)/2", y=str(y_top + i * leading),
            alpha=tx.fade_alpha(start, duration + 1.0, fade=0.24), shadow=4))

    if source:
        filters.append(tx.drawtext(
            source[:60], font=theme.body.path, size=theme.size("source", h),
            color=theme.ff("ink_dim"), x="(w-text_w)/2",
            y=str(rule_y + int(h * 0.045)),
            alpha=tx.fade_alpha(build * 0.6, duration + 1.0, fade=0.3), shadow=2))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result
