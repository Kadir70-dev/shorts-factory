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
_CACHE_VERSION = 3  # bumped: fixed label fade-out staying visible 0.6s past the next label's start (ghosting)


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
    # Wrapping against the full frame width let a long multi-clause line
    # (e.g. "Housing, food, transportation, medical care...") land flush with
    # or past the horizontal safe edges once centred — `chars_for`'s budget
    # is an average-width estimate, not exact, so it has no built-in margin.
    # An 88%-width budget leaves a real ~6% gutter each side.
    lines = tx.wrap(theme.display.apply_case(headline), size, int(w * 0.88), max_lines=4)
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


# --------------------------------------------------------------------------- #
# Mechanism diagram — TIER 2b. A business PROCESS explained as a moving 2D
# icon sequence (not a static claim card): built from the same Canvas
# primitives as kinetic()/plate(), so it costs nothing new and depends on
# nothing beyond ffmpeg. Purpose-built for "how does the mechanism work"
# beats where a bare kinetic-type sentence explains a physical transformation
# better shown than told (assembly → flat-pack → denser stacking → more units
# per shipment) — the flat-pack Short's own logistics beat is the reference case.
def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _window(t: float, t0: float, t1: float) -> float:
    """Eased 0..1 progress of `t` inside [t0, t1); 0 before, 1 at/after."""
    if t1 <= t0:
        return 1.0 if t >= t1 else 0.0
    return ease_out_cubic(max(0.0, min(1.0, (t - t0) / (t1 - t0))))


async def flatpack_mechanism(theme: BrandTheme, out: Path, w: int, h: int, fps: int,
                             duration: float, seed: int = 0) -> Path:
    """TABLE -> legs detach -> flattens -> stacks denser than the assembled
    piece -> more units fit per truck. Four beats, each labelled, on the
    channel's own branded background."""
    key = cache_key("flatpack_mechanism", theme, w, h, fps, duration, seed, "")
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))
    ink, accent, dim = theme.rgb("ink"), theme.rgb("primary"), theme.rgb("grid")

    cx, cy = w * 0.5, h * 0.40
    P1, P2, P3, P4 = 0.24, 0.46, 0.70, 0.90   # phase boundaries, fraction of duration

    def gen():
        for f in range(frames):
            t = f / fps
            p = t / duration
            c = base.copy()
            _draw_treatment(c, theme, "grid_drift", t, w, h, rng)

            # -- Phase 0->1: an assembled table, legs visible ------------------ #
            table_w, table_h = w * 0.30, h * 0.018
            leg_len = h * 0.10
            detach = _window(p, P1, P2)          # 0 (assembled) -> 1 (flat-packed)
            top_y = cy - h * 0.05
            c.rect(cx - table_w / 2, top_y, table_w, table_h, ink, alpha=1.0, radius=4)
            if detach < 1.0:
                # four legs, sliding outward and shortening as they detach
                for i, sx in enumerate((-1, -1, 1, 1)):
                    sy = -1 if i % 2 == 0 else 1
                    lx = cx + sx * table_w * 0.42
                    ly0 = top_y + table_h
                    spread = 1.0 + detach * 1.4        # legs kick outward as they come off
                    ly1 = ly0 + leg_len * (1 - detach) + h * 0.05 * detach
                    c.segment(lx, ly0, lx + sx * 10 * spread * detach, ly1,
                             w * 0.012, ink, alpha=max(0.0, 1.0 - detach * 1.1))
            # flat panels stack up under the tabletop as legs finish detaching
            stack_n = 4
            for i in range(stack_n):
                appear = _window(p, P1 + 0.03 * i, P1 + 0.03 * i + 0.10)
                if appear <= 0:
                    continue
                py = top_y + table_h * 2 + i * (table_h * 2.6)
                pw = table_w * (0.55 + 0.45 * appear)
                c.rect(cx - pw / 2, py, pw, table_h * 1.6, dim, alpha=0.85 * appear, radius=3)

            # -- Phase 2->3: footprint comparison ------------------------------ #
            cmp_show = _window(p, P2, P2 + 0.02)
            if cmp_show > 0 and p < P3 + 0.02:
                box_y, box_h = h * 0.50, h * 0.16
                lx0, rx0 = w * 0.14, w * 0.56
                box_w = w * 0.30
                c.rect(lx0, box_y, box_w, box_h, dim, alpha=0.35 * cmp_show)
                c.rect(rx0, box_y, box_w, box_h, dim, alpha=0.35 * cmp_show)
                # left: one bulky footprint (the assembled table's real footprint)
                c.rect(lx0 + box_w * 0.18, box_y + box_h * 0.15, box_w * 0.64, box_h * 0.7,
                      ink, alpha=0.9 * cmp_show, radius=6)
                # right: five thin flat-packs sharing the SAME footprint
                n = 5
                for i in range(n):
                    reveal = _window(p, P2 + 0.02 + 0.02 * i, P2 + 0.10 + 0.02 * i)
                    if reveal <= 0:
                        continue
                    fh = box_h * 0.68 / n
                    fy = box_y + box_h * 0.18 + i * fh * 1.08
                    c.rect(rx0 + box_w * 0.14, fy, box_w * 0.72 * reveal, fh * 0.8,
                          accent, alpha=0.92 * cmp_show, radius=2)

            # -- Phase 3->4: truck / container fills up ------------------------ #
            truck_show = _window(p, P3, P3 + 0.04)
            if truck_show > 0:
                ty = h * 0.60
                tw_, th_ = w * 0.62, h * 0.11
                tx0 = cx - tw_ / 2
                c.segment(tx0, ty, tx0 + tw_, ty, w * 0.006, ink, alpha=0.9 * truck_show)
                c.segment(tx0, ty + th_, tx0 + tw_, ty + th_, w * 0.006, ink, alpha=0.9 * truck_show)
                c.segment(tx0, ty, tx0, ty + th_, w * 0.006, ink, alpha=0.9 * truck_show)
                c.segment(tx0 + tw_, ty, tx0 + tw_, ty + th_, w * 0.006, ink, alpha=0.9 * truck_show)
                c.circle(tx0 + tw_ * 0.18, ty + th_ + h * 0.012, h * 0.012, ink, alpha=0.9 * truck_show)
                c.circle(tx0 + tw_ * 0.82, ty + th_ + h * 0.012, h * 0.012, ink, alpha=0.9 * truck_show)
                cargo_n = 6
                cell_w = tw_ * 0.9 / cargo_n
                for i in range(cargo_n):
                    fill = _window(p, P3 + 0.05 + 0.03 * i, P3 + 0.12 + 0.03 * i)
                    if fill <= 0:
                        continue
                    c.rect(tx0 + tw_ * 0.05 + i * cell_w, ty + th_ * 0.18, cell_w * 0.82,
                          th_ * 0.7 * fill, accent, alpha=0.9 * truck_show, radius=2)

            yield c

    labels = [
        (0.02, "ASSEMBLED"),
        (P1 + 0.03, "FLAT-PACKED"),
        (P2 + 0.05, "MORE FITS IN THE SAME SPACE"),
        (P3 + 0.06, "MORE UNITS PER TRUCK"),
    ]
    ksize = theme.size("lower_third", h)
    filters: list[str] = []
    for i, (start_p, text) in enumerate(labels):
        start = start_p * duration
        end = (labels[i + 1][0] * duration) if i + 1 < len(labels) else duration
        filters.append(tx.drawtext(
            text, font=theme.body.path, size=ksize, color=theme.ff("primary"),
            x="(w-text_w)/2", y=str(int(h * 0.775)),
            alpha=tx.fade_alpha(start, end, fade=0.22), shadow=3))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result


async def amortization_mechanism(theme: BrandTheme, out: Path, w: int, h: int, fps: int,
                                 duration: float, seed: int = 0) -> Path:
    """MONTHLY PAYMENT splits into INTEREST + PRINCIPAL, then that split shifts
    from interest-heavy (EARLY YEARS) to principal-heavy (LATER YEARS) — the
    same payment bar, its proportions changing. Purpose-built for amortization
    beats where the mechanism (a changing split, not a changing number) is the
    story; uses only generic labels, no invented loan figures."""
    key = cache_key("amortization_mechanism", theme, w, h, fps, duration, seed, "")
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))
    ink, accent, dim = theme.rgb("ink"), theme.rgb("primary"), theme.rgb("secondary")

    bar_x, bar_w = w * 0.14, w * 0.72
    bar_h = h * 0.075
    early_y, mid_y, late_y = h * 0.42, h * 0.53, h * 0.64
    P1, P2 = 0.30, 0.62   # early-years hold -> shift -> later-years hold

    def split_at(p: float) -> float:
        """Fraction of the bar that is INTEREST at progress p (0..1)."""
        if p < P1:
            return 0.86
        if p < P2:
            return _lerp(0.86, 0.30, (p - P1) / (P2 - P1))
        return 0.30

    def gen():
        for f in range(frames):
            t = f / fps
            p = t / duration
            c = base.copy()
            _draw_treatment(c, theme, "rule_field", t, w, h, rng)

            appear = _window(p, 0.0, 0.06)
            if appear > 0:
                c.rect(bar_x, mid_y - bar_h * 0.5, bar_w, bar_h * 0.16, dim,
                      alpha=0.5 * appear, radius=3)

            bar_show = _window(p, 0.10, 0.16)
            if bar_show > 0:
                frac = split_at(p)
                y = mid_y - bar_h / 2
                c.rect(bar_x, y, bar_w * bar_show, bar_h, dim, alpha=0.35, radius=4)
                c.rect(bar_x, y, bar_w * frac * bar_show, bar_h, accent, alpha=0.95, radius=4)
                c.rect(bar_x + bar_w * frac * bar_show, y,
                      bar_w * (1 - frac) * bar_show, bar_h, ink, alpha=0.85, radius=4)

            yield c

    labels = [
        (0.0, "MONTHLY PAYMENT"),
        (0.10, "INTEREST  vs  PRINCIPAL"),
        (0.14, "EARLY YEARS: MOSTLY INTEREST"),
        (P1 + 0.02, "THE SPLIT SHIFTS OVER TIME"),
        (P2 + 0.04, "LATER YEARS: MOSTLY PRINCIPAL"),
    ]
    ksize = theme.size("lower_third", h)
    filters: list[str] = []
    for i, (start_p, text) in enumerate(labels):
        start = start_p * duration
        end = (labels[i + 1][0] * duration) if i + 1 < len(labels) else duration
        filters.append(tx.drawtext(
            text, font=theme.body.path, size=ksize, color=theme.ff("ink"),
            x="(w-text_w)/2", y=str(int(h * 0.775)),
            alpha=tx.fade_alpha(start, end, fade=0.22), shadow=3))
    # static legend under the bar once it's on screen
    legend_y = mid_y + bar_h * 1.1
    filters.append(tx.drawtext(
        "INTEREST", font=theme.body.path, size=int(ksize * 0.7), color=theme.ff("primary"),
        x=str(int(bar_x)), y=str(int(legend_y)),
        alpha=tx.fade_alpha(0.16 * duration, duration + 1.0, fade=0.2), shadow=2))
    filters.append(tx.drawtext(
        "PRINCIPAL", font=theme.body.path, size=int(ksize * 0.7), color=theme.ff("ink"),
        x=str(int(bar_x + bar_w - 140)), y=str(int(legend_y)),
        alpha=tx.fade_alpha(0.16 * duration, duration + 1.0, fade=0.2), shadow=2))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result

    labels = [
        (0.02, "ASSEMBLED"),
        (P1 + 0.03, "FLAT-PACKED"),
        (P2 + 0.05, "MORE FITS IN THE SAME SPACE"),
        (P3 + 0.06, "MORE UNITS PER TRUCK"),
    ]
    ksize = theme.size("lower_third", h)
    filters: list[str] = []
    for i, (start_p, text) in enumerate(labels):
        start = start_p * duration
        end = (labels[i + 1][0] * duration) if i + 1 < len(labels) else duration
        filters.append(tx.drawtext(
            text, font=theme.body.path, size=ksize, color=theme.ff("primary"),
            x="(w-text_w)/2", y=str(int(h * 0.775)),
            alpha=tx.fade_alpha(start, end, fade=0.22), shadow=3))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result


async def fleet_commonality_mechanism(theme: BrandTheme, out: Path, w: int, h: int,
                                      fps: int, duration: float, seed: int = 0) -> Path:
    """THREE DIFFERENT aircraft (separate training/parts/crews each) collapse
    into ONE shared aircraft type feeding a single shared system — the fleet-
    commonality cost mechanism, in silhouettes and connecting lines only."""
    key = cache_key("fleet_commonality_mechanism", theme, w, h, fps, duration, seed, "")
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))
    ink, accent, dim = theme.rgb("ink"), theme.rgb("primary"), theme.rgb("secondary")

    row_y = h * 0.40
    slot_x = (w * 0.22, w * 0.50, w * 0.78)
    P1, P2 = 0.34, 0.62

    def plane(c: Canvas, cx: float, cy: float, scale: float, color, alpha: float) -> None:
        body_w, body_h = 120 * scale, 20 * scale
        c.rect(cx - body_w / 2, cy - body_h / 2, body_w, body_h, color, alpha=alpha, radius=8)
        c.rect(cx - 12 * scale, cy - body_h * 1.6, 24 * scale, body_h * 1.4,
              color, alpha=alpha * 0.9, radius=4)

    def gen():
        for f in range(frames):
            t = f / fps
            p = t / duration
            c = base.copy()
            _draw_treatment(c, theme, "pulse_dots", t, w, h, rng)

            merge = _window(p, P1, P2)   # 0 = three different planes, 1 = merged
            scales = (0.65, 1.0, 0.8)
            for i, sx in enumerate(slot_x):
                scale = _lerp(scales[i], 1.0, merge)
                cx = _lerp(sx, w * 0.5, merge)
                appear = _window(p, 0.02 + 0.03 * i, 0.08 + 0.03 * i)
                if appear <= 0:
                    continue
                plane(c, cx, row_y, scale * appear, ink, 0.92 * appear)
                if merge < 0.5:
                    tag_y = row_y + 50
                    c.rect(cx - 30, tag_y, 60, 14, dim, alpha=0.6 * appear, radius=3)

            if merge > 0.15:
                hub_y = row_y + 120
                hub_show = _window(p, P1 + 0.05, P1 + 0.15)
                if hub_show > 0:
                    c.rect(w * 0.5 - 90, hub_y, 180, 30, accent, alpha=0.9 * hub_show, radius=6)
                    for sx in slot_x:
                        cx = _lerp(sx, w * 0.5, merge)
                        c.segment(cx, row_y + 20, w * 0.5, hub_y,
                                 3, accent, alpha=0.6 * hub_show * merge)

            yield c

    labels = [
        (0.02, "MULTIPLE AIRCRAFT TYPES"),
        (0.16, "= SEPARATE TRAINING, PARTS, CREWS"),
        (P1 + 0.02, "ONE AIRCRAFT TYPE"),
        (P2 + 0.04, "= ONE SHARED SYSTEM"),
    ]
    ksize = theme.size("lower_third", h)
    filters: list[str] = []
    for i, (start_p, text) in enumerate(labels):
        start = start_p * duration
        end = (labels[i + 1][0] * duration) if i + 1 < len(labels) else duration
        filters.append(tx.drawtext(
            text, font=theme.body.path, size=ksize, color=theme.ff("ink"),
            x="(w-text_w)/2", y=str(int(h * 0.775)),
            alpha=tx.fade_alpha(start, end, fade=0.22), shadow=3))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result


async def money_multiplier_mechanism(theme: BrandTheme, out: Path, w: int, h: int,
                                     fps: int, duration: float, seed: int = 0) -> Path:
    """DEPOSIT splits into RESERVE (kept) + LOANED (re-lent); the loaned share
    becomes a new, smaller deposit that splits again — a shrinking cascade of
    bars visualising the fractional-reserve money-multiplier effect."""
    key = cache_key("money_multiplier_mechanism", theme, w, h, fps, duration, seed, "")
    hit = _cached(key, out)
    if hit is not None:
        return hit

    rng = random.Random(seed)
    base = _bg_base(theme, w, h)
    frames = max(1, int(round(duration * fps)))
    ink, accent, dim = theme.rgb("ink"), theme.rgb("primary"), theme.rgb("secondary")

    reserve_frac = 0.20
    rows = [
        (h * 0.34, w * 0.72, 1.00),
        (h * 0.34 + 70, w * 0.72 * 0.80, 0.80),
        (h * 0.34 + 140, w * 0.72 * 0.64, 0.64),
    ]
    bar_x0, bar_h = w * 0.14, h * 0.055
    windows = [(0.05, 0.30), (0.36, 0.58), (0.64, 0.86)]

    def gen():
        for f in range(frames):
            t = f / fps
            p = t / duration
            c = base.copy()
            _draw_treatment(c, theme, "rule_field", t, w, h, rng)

            for (y, bw, _scale), (w0, w1) in zip(rows, windows):
                show = _window(p, w0, w0 + 0.06)
                if show <= 0:
                    continue
                split = _window(p, w0 + 0.04, w1 * 0.5 + w0 * 0.5)
                c.rect(bar_x0, y, bw * show, bar_h, dim, alpha=0.9 * show, radius=3)
                if split > 0:
                    loan_w = bw * (1 - reserve_frac) * split
                    c.rect(bar_x0, y, bw * reserve_frac, bar_h, ink, alpha=0.85, radius=3)
                    c.rect(bar_x0 + bw * reserve_frac, y, loan_w, bar_h,
                          accent, alpha=0.92, radius=3)

            yield c

    labels = [
        (0.0, "YOU DEPOSIT MONEY"),
        (0.10, "RESERVE"),
        (0.20, "kept  vs  loaned out"),
        (0.36, "THE LOAN BECOMES A NEW DEPOSIT"),
        (0.64, "AND SPLITS AGAIN"),
        (0.88, "THE MONEY SUPPLY GROWS EACH CYCLE"),
    ]
    ksize = theme.size("lower_third", h)
    filters: list[str] = []
    for i, (start_p, text) in enumerate(labels):
        start = start_p * duration
        end = (labels[i + 1][0] * duration) if i + 1 < len(labels) else duration
        filters.append(tx.drawtext(
            text, font=theme.body.path, size=ksize, color=theme.ff("ink"),
            x="(w-text_w)/2", y=str(int(h * 0.78)),
            alpha=tx.fade_alpha(start, end, fade=0.2), shadow=3))
    filters.append(tx.drawtext(
        "RESERVE", font=theme.body.path, size=int(ksize * 0.6), color=theme.ff("ink"),
        x=str(int(bar_x0)), y=str(int(rows[0][0] - 26)),
        alpha=tx.fade_alpha(0.10 * duration, duration + 1.0, fade=0.2), shadow=2))
    filters.append(tx.drawtext(
        "LOANED OUT", font=theme.body.path, size=int(ksize * 0.6), color=theme.ff("primary"),
        x=str(int(bar_x0 + rows[0][1] * 0.4)), y=str(int(rows[0][0] - 26)),
        alpha=tx.fade_alpha(0.10 * duration, duration + 1.0, fade=0.2), shadow=2))

    result = await write_video(gen(), w, h, fps, out,
                               vf=",".join(filters) if filters else None)
    visual_cache_store(visual_cache_path("motiongfx", key), result)
    return result
