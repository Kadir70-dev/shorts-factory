"""Small motion-graphics engine for the K70 Aurora USA-finance Short (v2 look).

Why this exists: the stock dataviz plates are a flat navy panel with one flat-coloured line, which reads as
a 2020 explainer.  Here every beat is real graded footage with a live graphics layer on top:

  * charts are glass panels over blurred, darkened real footage -- glowing cyan->violet line, gradient area,
    pulsing head dot, a moving counter, direction-coloured readout and annotated callouts
  * stat beats are big counting numbers (gold) with a red/green direction triangle
  * headlines are kinetic: words pop in one by one

Everything is drawn with Pillow into RGBA frames and piped into ffmpeg, which does the grade, push-in zoom,
grain and vignette.  Pure functions of (data, time): no network, no randomness.
"""
from __future__ import annotations

import math
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
FONT_DIR = Path(__file__).resolve().parents[1] / "config" / "brand" / "fonts"
DISPLAY = FONT_DIR / "ArchivoBlack-Regular.ttf"
BODY = FONT_DIR / "BarlowCondensed-Bold.ttf"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def eo3(x: float) -> float:
    return 1 - (1 - clamp(x)) ** 3


def eio(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def eback(x: float, s: float = 1.9) -> float:
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1, c2))


@lru_cache(maxsize=64)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=256)
def text_tile(text: str, face: str, size: int, fill, glow=None, glow_r: int = 14, shadow: int = 4,
              spacing: float = 0.0) -> Image.Image:
    """Text -> padded RGBA tile.  `fill` is an RGB tuple or a (top, bottom) gradient."""
    f = font(face, size)
    pad = glow_r * 2 + shadow + 8
    adv = [f.getlength(c) + spacing for c in text]
    w = int(sum(adv)) + pad * 2
    asc, desc = f.getmetrics()
    h = asc + desc + pad * 2
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    x = pad
    for c, a in zip(text, adv):
        d.text((x, pad), c, font=f, fill=255)
        x += a
    if isinstance(fill[0], tuple):
        grad = Image.new("RGBA", (w, h))
        gp = ImageDraw.Draw(grad)
        for yy in range(h):
            gp.line([(0, yy), (w, yy)], fill=mix(fill[0], fill[1], yy / max(1, h - 1)) + (255,))
        body = grad
    else:
        body = Image.new("RGBA", (w, h), tuple(fill) + (255,))
    body.putalpha(mask)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        sh.putalpha(mask.point(lambda v: int(v * 0.8)))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(shadow)), (shadow // 2, shadow))
    if glow:
        gl = Image.new("RGBA", (w, h), tuple(glow) + (255,))
        gl.putalpha(mask.point(lambda v: int(v * 0.9)))
        out.alpha_composite(gl.filter(ImageFilter.GaussianBlur(glow_r)))
    out.alpha_composite(body)
    return out


def put(layer: Image.Image, tile: Image.Image, x: float, y: float, alpha: float = 1.0, scale: float = 1.0,
        anchor: str = "lt") -> None:
    """Alpha-composite a tile at (x, y); anchor: l/c/r  x  t/m/b."""
    if alpha <= 0.003 or scale <= 0.01:
        return
    if scale != 1.0:
        tile = tile.resize((max(1, int(tile.width * scale)), max(1, int(tile.height * scale))), Image.BICUBIC)
    if alpha < 0.999:
        a = tile.getchannel("A").point(lambda v: int(v * alpha))
        tile = tile.copy()
        tile.putalpha(a)
    ax, ay = anchor[0], anchor[1]
    px = x - (tile.width / 2 if ax == "c" else tile.width if ax == "r" else 0)
    py = y - (tile.height / 2 if ay == "m" else tile.height if ay == "b" else 0)
    layer.alpha_composite(tile, (int(round(px)), int(round(py))))


def vgrad(w: int, h: int, top_a: float, bot_a: float, color=(0, 0, 0)) -> Image.Image:
    a = np.linspace(top_a, bot_a, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = color
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- #
# shared furniture: legibility gradients, start-of-scene flash
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _shade() -> Image.Image:
    s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s.alpha_composite(vgrad(W, 760, 0.72, 0.0), (0, 0))
    s.alpha_composite(vgrad(W, 820, 0.0, 0.70), (0, H - 820))
    return s


def base_layer(t: float, flash: bool, shade: bool = True) -> Image.Image:
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if shade:
        L.alpha_composite(_shade())
    return L


def add_flash(L: Image.Image, t: float, strength: float = 0.30, dur: float = 0.16) -> None:
    if t < dur:
        a = int(255 * strength * (1 - t / dur) ** 2)
        L.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))


def source_line(L: Image.Image, text: str, t: float, t0: float = 0.3, y: int = 1385, pal=None) -> None:
    tile = text_tile(text.upper(), str(BODY), 34, pal["ink"], None, 0, 5, spacing=1.2)
    put(L, tile, W / 2, y, alpha=eo3((t - t0) / 0.4) * 0.95, anchor="cm")


# --------------------------------------------------------------------------- #
# kinetic headline
# --------------------------------------------------------------------------- #
def headline(L: Image.Image, lines: list[tuple[str, tuple, float]], t: float, pal, size: int = 128, x: int = 64,
             y0: int = 250, gap: float = 1.02, step: float = 0.09, align: str = "left") -> None:
    """lines = [(text, colour, t_in)], words pop in `step` seconds apart."""
    f = font(str(DISPLAY), size)
    y = y0
    for text, col, t_in in lines:
        words = text.split(" ")
        widths = [f.getlength(w) for w in words]
        space = f.getlength(" ")
        total = sum(widths) + space * (len(words) - 1)
        cx = x if align == "left" else (W - total) / 2
        for k, w in enumerate(words):
            tt = (t - t_in - k * step) / 0.28
            if tt > 0:
                tile = text_tile(w, str(DISPLAY), size, col if not isinstance(col, list) else tuple(col), pal["glow"], 18, 6)
                sc = lerp(1.35, 1.0, eback(tt))
                pad = (tile.width - f.getlength(w)) / 2
                put(L, tile, cx - pad + widths[k] / 2 + pad, y + size * 0.62, alpha=eo3(tt * 1.6), scale=sc, anchor="cm")
            cx += widths[k] + space
        y += size * gap + 6


# --------------------------------------------------------------------------- #
# big counting stat on footage
# --------------------------------------------------------------------------- #
def stat(L: Image.Image, t: float, pal, target: float, prefix: str, suffix: str, label: str, sub: str = "",
         direction: str | None = "up", y: int = 380, count: float = 0.9, decimals: int = 0, start: float | None = None,
         t_in: float = 0.12) -> None:
    start = target if start is None else start
    p = eio((t - t_in) / count)
    val = lerp(start if start != target else 0.0, target, p)
    txt = f"{prefix}{val:.{decimals}f}{suffix}"
    col = pal["gold"]
    tile = text_tile(txt, str(DISPLAY), 270, col, col, 26, 8)
    pop = lerp(1.22, 1.0, eback((t - t_in) / 0.35))
    put(L, tile, W / 2 + 28, y + 150, alpha=eo3((t - t_in) / 0.2), scale=pop, anchor="cm")
    if direction:
        tri = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        d = ImageDraw.Draw(tri)
        c = pal["red"] if direction == "up" else pal["green"]
        pts = [(48, 8), (92, 88), (4, 88)] if direction == "up" else [(4, 8), (92, 8), (48, 88)]
        d.polygon(pts, fill=c + (255,))
        tri = tri.filter(ImageFilter.GaussianBlur(0.6))
        tw = tile.width * pop
        put(L, tri, W / 2 + 28 - tw / 2 - 40, y + 150, alpha=eo3((t - t_in - 0.1) / 0.25), anchor="cm")
    lab = text_tile(label.upper(), str(BODY), 80, pal["ink"], None, 0, 7, spacing=5)
    put(L, lab, W / 2, y + 372, alpha=eo3((t - t_in - 0.25) / 0.3), anchor="cm")
    if sub:
        s = text_tile(sub.upper(), str(BODY), 44, pal["ink"], None, 0, 6, spacing=3)
        put(L, s, W / 2, y + 448, alpha=eo3((t - t_in - 0.4) / 0.3), anchor="cm")


# --------------------------------------------------------------------------- #
# glass chart panel
# --------------------------------------------------------------------------- #
class Chart:
    """values: list[float|None] evenly spaced in time (None = never published; drawn as a dashed bridge)."""

    PX0, PX1, PY0, PY1 = 168, 985, 672, 1135

    def __init__(self, pal, title: str, values: list, keys: list[tuple[float, float]], x_labels: dict[int, str],
                 yticks: list[float], ymin: float, ymax: float, fmt, big, source: str, callouts=None, pill_fmt=None,
                 line_cols=None):
        self.pal, self.title, self.values, self.keys = pal, title, values, keys
        self.x_labels, self.yticks, self.ymin, self.ymax = x_labels, yticks, ymin, ymax
        self.fmt, self.big, self.source, self.callouts = fmt, big, source, callouts or []
        self.pill_fmt = pill_fmt or fmt
        self.line_cols = line_cols or (pal["secondary"], pal["primary"])
        self.n = len(values)
        self.valid = [i for i, v in enumerate(values) if v is not None]
        self._static = self._build_static()
        self._grad = self._build_area_gradient()

    # geometry
    def X(self, i: float) -> float:
        return self.PX0 + (self.PX1 - self.PX0) * i / max(1, self.n - 1)

    def Y(self, v: float) -> float:
        return self.PY1 - (v - self.ymin) / (self.ymax - self.ymin) * (self.PY1 - self.PY0)

    def head_index(self, t: float) -> float:
        k = self.keys
        if t <= k[0][0]:
            return k[0][1]
        for (t0, i0), (t1, i1) in zip(k, k[1:]):
            if t <= t1:
                return lerp(i0, i1, eio((t - t0) / (t1 - t0)))
        return k[-1][1]

    def value_at(self, h: float) -> float:
        pts = [i for i in self.valid if i <= h]
        if not pts:
            return self.values[self.valid[0]]
        i = pts[-1]
        nxt = [j for j in self.valid if j > i]
        if not nxt or h <= i:
            return self.values[i]
        j = nxt[0]
        return lerp(self.values[i], self.values[j], (h - i) / (j - i))

    # static layers
    def _build_static(self) -> Image.Image:
        p = self.pal
        S = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(panel)
        d.rounded_rectangle([48, 225, W - 48, 1300], 40, fill=(6, 14, 28, 168), outline=(255, 255, 255, 34), width=2)
        d.rounded_rectangle([48, 225, W - 48, 232], 4, fill=p["primary"] + (200,))
        S.alpha_composite(panel)
        S.alpha_composite(text_tile(self.title.upper(), str(BODY), 46, p["dim"], None, 0, 4, spacing=2.4), (84, 244))
        dr = ImageDraw.Draw(S)
        for v in self.yticks:
            y = self.Y(v)
            for x in range(self.PX0, self.PX1, 22):
                dr.line([(x, y), (x + 10, y)], fill=(255, 255, 255, 46), width=2)
            tl = text_tile(self.fmt(v), str(BODY), 31, p["dim"], None, 0, 0)
            S.alpha_composite(tl, (self.PX0 - 18 - tl.width + 16, int(y - tl.height / 2)))
        for i, txt in self.x_labels.items():
            tl = text_tile(txt.upper(), str(BODY), 33, p["dim"], None, 0, 0, spacing=1)
            x = min(max(self.X(i), 100 + tl.width / 2 - 16), self.PX1 + 24 - tl.width / 2 + 16)
            S.alpha_composite(tl, (int(x - tl.width / 2), self.PY1 + 14))
        src = text_tile(self.source, str(BODY), 31, p["dim"], None, 0, 0, spacing=0.6)
        S.alpha_composite(src, (78, 1222))
        return S

    def _build_area_gradient(self) -> Image.Image:
        h = self.PY1 - self.PY0 + 60
        a = np.linspace(0.34, 0.0, h, dtype=np.float32)[:, None] * np.ones((1, W), np.float32)
        arr = np.zeros((h, W, 4), np.uint8)
        c0, c1 = self.line_cols
        xs = np.clip((np.arange(W) - self.PX0) / (self.PX1 - self.PX0), 0, 1)
        for ch in range(3):
            arr[..., ch] = (c0[ch] + (c1[ch] - c0[ch]) * xs)[None, :]
        arr[..., 3] = (a * 255).astype(np.uint8)
        return Image.fromarray(arr, "RGBA")

    # per frame
    def frame(self, t: float) -> Image.Image:
        p = self.pal
        L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        panel_a = eo3(t / 0.35)
        st = self._static.copy()
        if panel_a < 0.999:
            st.putalpha(st.getchannel("A").point(lambda v: int(v * panel_a)))
        L.alpha_composite(st)
        h = min(self.head_index(t), self.n - 1)

        # points drawn so far (None = gap -> dashed bridge)
        drawn: list[tuple[float, float, float]] = []   # (x, y, frac_along)
        for i in self.valid:
            if i <= h:
                drawn.append((self.X(i), self.Y(self.values[i]), i))
        if h > (drawn[-1][2] if drawn else -1):
            j = [k for k in self.valid if k > h]
            if j and drawn:
                k0, k1 = drawn[-1][2], j[0]
                f = (h - k0) / (k1 - k0)
                drawn.append((lerp(self.X(k0), self.X(k1), f), lerp(self.Y(self.values[int(k0)]), self.Y(self.values[k1]), f), h))
        if len(drawn) >= 2:
            # area
            mask = Image.new("L", (W, H), 0)
            md = ImageDraw.Draw(mask)
            poly = [(x, y) for x, y, _ in drawn] + [(drawn[-1][0], self.PY1), (drawn[0][0], self.PY1)]
            md.polygon(poly, fill=255)
            area = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            area.paste(self._grad, (0, self.PY0 - 30))
            area.putalpha(ImageChops.multiply(area.getchannel("A"), mask))
            L.alpha_composite(area)
            # glow (quarter-res) + line
            gl = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0))
            gd = ImageDraw.Draw(gl)
            ld = ImageDraw.Draw(L)
            c0, c1 = self.line_cols
            for (x0, y0, i0), (x1, y1, i1) in zip(drawn, drawn[1:]):
                col = mix(c0, c1, clamp((x0 - self.PX0) / (self.PX1 - self.PX0)))
                gap = (i1 - i0) > 1.0001 and i0 == int(i0) and self.values[int(i0) + 1] is None
                if gap:
                    n = int(math.hypot(x1 - x0, y1 - y0) / 24)
                    for k in range(0, n, 2):
                        a0, a1 = k / max(1, n), min(1.0, (k + 1) / max(1, n))
                        ld.line([(lerp(x0, x1, a0), lerp(y0, y1, a0)), (lerp(x0, x1, a1), lerp(y0, y1, a1))], fill=col + (200,), width=7)
                else:
                    gd.line([(x0 / 4, y0 / 4), (x1 / 4, y1 / 4)], fill=col + (255,), width=5)
                    ld.line([(x0, y0), (x1, y1)], fill=col + (255,), width=11)
                    ld.ellipse([x1 - 5.5, y1 - 5.5, x1 + 5.5, y1 + 5.5], fill=col + (255,))
            gl = gl.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR)
            gl.putalpha(gl.getchannel("A").point(lambda v: int(min(255, v * 1.15))))
            under = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            under.alpha_composite(gl)
            under.alpha_composite(L)
            L = under
            hx, hy, _ = drawn[-1]
            val = self.value_at(h)
            ld = ImageDraw.Draw(L)
            pulse = 1 + 0.22 * math.sin(t * 7.5)
            r = 19 * pulse
            ld.ellipse([hx - r * 1.9, hy - r * 1.9, hx + r * 1.9, hy + r * 1.9], fill=p["secondary"] + (52,))
            ld.ellipse([hx - 15, hy - 15, hx + 15, hy + 15], fill=(255, 255, 255, 255))
            ld.ellipse([hx - 8, hy - 8, hx + 8, hy + 8], fill=mix(self.line_cols[0], self.line_cols[1], clamp((hx - self.PX0) / (self.PX1 - self.PX0))) + (255,))
            # value pill follows the head
            pill = text_tile(self.pill_fmt(val), str(DISPLAY), 40, p["bg"], None, 0, 0)
            pw, ph = pill.width - 20, pill.height - 20
            px = min(max(hx - pw / 2 - 18, 80), W - 80 - pw - 36)
            py = hy - ph - 52
            ld.rounded_rectangle([px, py, px + pw + 36, py + ph + 14], 18, fill=p["ink"] + (238,))
            L.alpha_composite(pill, (int(px + 18 - 10), int(py + 7 - 10)))
            # big counter
            col, arrow = self.big_color(h)
            big_txt, big_label = self.big(val, h)
            bt = text_tile(big_txt, str(DISPLAY), 170, col, col, 22, 8)
            put(L, bt, 84, 300, alpha=eo3((t - 0.1) / 0.3), anchor="lt")
            if arrow:
                tri = Image.new("RGBA", (84, 84), (0, 0, 0, 0))
                td = ImageDraw.Draw(tri)
                td.polygon([(42, 6), (80, 76), (4, 76)] if arrow == "up" else [(4, 8), (80, 8), (42, 78)], fill=col + (255,))
                put(L, tri, W - 118, 400, alpha=eo3((t - 0.3) / 0.3), anchor="rm")
            lb = text_tile(big_label.upper(), str(BODY), 42, p["ink"], None, 0, 4, spacing=2.5)
            put(L, lb, 90, 548, alpha=eo3((t - 0.25) / 0.3), anchor="lt")

        # callouts (peak / start markers)
        for (idx, text, sub, col, t_show) in self.callouts:
            a = eo3((t - t_show) / 0.35)
            if a <= 0 or self.values[idx] is None:
                continue
            x, y = self.X(idx), self.Y(self.values[idx])
            cd = ImageDraw.Draw(L)
            for yy in range(int(self.PY0 - 10), int(y - 14), 18):
                cd.line([(x, yy), (x, yy + 9)], fill=col + (int(200 * a),), width=3)
            lab = text_tile(text, str(DISPLAY), 36, col, None, 0, 0)
            sb = text_tile(sub.upper(), str(BODY), 31, p["dim"], None, 0, 0, spacing=1.2)
            tx = min(max(x - lab.width / 2, 70), W - 70 - lab.width)
            put(L, lab, tx, self.PY0 - 78 - 8 * (1 - a), alpha=a)
            put(L, sb, tx + 12, self.PY0 - 78 + lab.height - 26, alpha=a)
            r = 13
            cd.ellipse([x - r, y - r, x + r, y + r], outline=col + (int(255 * a),), width=4)
        return L

    def big_color(self, h: float):
        """Direction colour: up = red (prices/inflation rising is bad), down = green; None while flat."""
        i = int(h)
        prev = [self.values[j] for j in self.valid if j <= max(0, i - 3)]
        cur = self.value_at(h)
        if not prev:
            return self.pal["gold"], None
        d = cur - prev[-1]
        thr = 0.02 * (self.ymax - self.ymin)
        if d > thr:
            return self.pal["red"], "up"
        if d < -thr:
            return self.pal["green"], "down"
        return self.pal["gold"], None


# --------------------------------------------------------------------------- #
# scene compositor
# --------------------------------------------------------------------------- #
def render_scene(out: Path, frames: int, segments: list[tuple[Path, float, float]], overlay_fn, mode: str = "plain",
                 first_scene: bool = False) -> None:
    """segments = [(clip, start_s, seconds)] hard-cut inside the scene.  mode 'chart' = blurred + darkened bg."""
    n = len(segments)
    inputs, parts = [], []
    for k, (clip, start, dur) in enumerate(segments):
        inputs += ["-ss", f"{start:.3f}", "-t", f"{dur + 0.25:.3f}", "-i", str(clip)]
        bump = "" if (k > 0 or first_scene) else "+0.075*max(0,1-t/0.22)"
        z = f"(1+0.07*t/{max(dur, 0.2):.3f}{bump})"
        parts.append(
            f"[{k}:v]scale=w='ceil(1080*{z}/2)*2':h='ceil(1920*{z}/2)*2':eval=frame:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS,setsar=1[v{k}]")
    cat = "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[bg0]" if n > 1 else "[v0]null[bg0]"
    if mode == "chart":
        grade = "gblur=sigma=16,eq=contrast=1.05:saturation=0.85:brightness=-0.24"
    else:
        grade = "eq=contrast=1.12:saturation=1.08:brightness=-0.035,colorbalance=rs=-0.04:bs=0.07:rm=-0.01:bm=0.03:rh=0.06:bh=-0.05"
    chain = (";".join(parts) + ";" + cat + f";[bg0]{grade}[bg];[bg][{n}:v]overlay=0:0:format=auto,"
             "vignette=PI/4.6,noise=alls=6:allf=t+u,format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "pipe:0", "-filter_complex", chain, "-map", "[v]", "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast",
           "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)]
    logf = open(out.with_suffix(".log"), "wb")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=logf)
    try:
        for f in range(frames):
            t = f / FPS
            proc.stdin.write(overlay_fn(t).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    rc = proc.wait()
    logf.close()
    if rc != 0:
        raise RuntimeError(f"ffmpeg scene render failed ({out.name}): {out.with_suffix('.log').read_text()[-500:]}")
    out.with_suffix(".log").unlink(missing_ok=True)
