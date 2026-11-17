"""
Top-5 boundary detection for ranking-format source videos (CPU only, no OCR).

A countdown video is an optional intro, five ranked moments and an optional
outro. Boundaries between moments leave four independent traces:

  cut      scene change in the picture          (ffmpeg scene score)
  overlay  the rank graphic changes: pixels that are STILL within each side
           of t but DIFFERENT across t (a "5" turning into a "4"). Moving
           content never qualifies, so this is robust to busy footage.
  audio    loudness steps and dips              (ebur128 momentary)
  timing   moments are roughly similar in length (soft prior)

Candidate boundaries are local maxima of the fused signal. The best four
interior boundaries are chosen by exhaustive search under a length-regularity
penalty. The report carries per-boundary signal agreement and an overall
confidence. Below the threshold nothing is saved automatically: the suggestion
is stored for the clip browser and a human sets the boundaries.

Also measured, so the clips can be reused without the source's own graphics:
  content_crop  bounding box of the live picture (static title bars excluded)
  overlay_box   per-moment box of the rank graphic inside the picture, which
                the renderer removes with ffmpeg `delogo`
"""
from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import numpy as np

from . import probe

HZ = 5                      # analysis frames per second
SW = 120                    # analysis width (px)
CONF_SAVE = 0.6             # auto-save five clips at or above this confidence


def frames(path: Path, width: int, height: int) -> np.ndarray:
    sh = round(SW * height / width / 2) * 2
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                        "-vf", f"fps={HZ},scale={SW}:{sh}:flags=area,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=900)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (SW * sh)
    return a[: n * SW * sh].reshape(n, sh, SW).astype(np.float32)


def _norm(x: np.ndarray) -> np.ndarray:
    hi = np.percentile(x, 99) if x.size else 0
    return np.clip(x / hi, 0, 1) if hi > 1e-9 else np.zeros_like(x)


def overlay_change(f: np.ndarray, w: int = HZ, g: int = 2) -> np.ndarray:
    """Per-frame fraction of pixels stable on both sides of t but changed across.
    The windows skip `g` frames either side of t, so a crossfade or flash at the
    boundary itself doesn't break "stable"."""
    n = len(f)
    out = np.zeros(n, dtype=np.float32)
    for t in range(w + g, n - w - g):
        a, b = f[t - g - w:t - g], f[t + g:t + g + w]
        stable = (a.std(0) < 6) & (b.std(0) < 6)
        changed = np.abs(a.mean(0) - b.mean(0)) > 40
        out[t] = (stable & changed).mean()
    return out


def cut_signal(f: np.ndarray, g: int = 2) -> np.ndarray:
    """Picture change between t-g and t+g: a hard cut and a 0.4 s crossfade both
    register, ordinary motion over 0.8 s mostly doesn't."""
    n = len(f)
    d = np.zeros(n, dtype=np.float32)
    for t in range(g, n - g):
        d[t] = np.abs(f[t + g] - f[t - g]).mean()
    hard = np.zeros(n, dtype=np.float32)
    if n > 1:
        hard[1:] = np.abs(np.diff(f, axis=0)).mean((1, 2))
    return np.maximum(d * 0.7, hard)


def audio_signal(loud: list[float], n: int, w: int = HZ) -> np.ndarray:
    """Loudness step + dip, resampled from 10 Hz to the analysis rate."""
    if not loud:
        return np.zeros(n, dtype=np.float32)
    l10 = np.asarray(loud, dtype=np.float32)
    lv = l10[:: probe.SAMPLE_HZ // HZ][:n]
    lv = np.pad(lv, (0, max(0, n - len(lv))), mode="edge")
    out = np.zeros(n, dtype=np.float32)
    for t in range(w, n - w):
        before, after = lv[t - w:t].mean(), lv[t:t + w].mean()
        dip = max(0.0, min(before, after) - lv[max(0, t - 1):t + 2].min())
        out[t] = abs(before - after) + dip
    return out


def content_crop(f: np.ndarray, full_w: int, full_h: int) -> tuple[int, int, int, int]:
    """(w, h, x, y) in source pixels of the region with real motion."""
    # 75th-percentile frame difference: flashes and fades are rare events and
    # don't make a static title band look "live"; real footage moves most frames
    act = np.percentile(np.abs(np.diff(f, axis=0)), 75, axis=0) if len(f) > 1 else f[0] * 0
    dyn = act > max(1.0, np.percentile(act, 90) * 0.12)
    rows = np.where(dyn.mean(1) > 0.25)[0]
    cols = np.where(dyn.mean(0) > 0.25)[0]
    if rows.size == 0 or cols.size == 0:
        return full_w, full_h, 0, 0
    sy, sx = full_h / f.shape[1], full_w / f.shape[2]
    y0, y1 = int(rows[0] * sy), int((rows[-1] + 1) * sy)
    x0, x1 = int(cols[0] * sx), int((cols[-1] + 1) * sx)
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    if w < full_w * 0.3 or h < full_h * 0.2:          # implausible: keep full frame
        return full_w, full_h, 0, 0
    return w, h, x0, y0


def _still_mask(seg: np.ndarray) -> np.ndarray:
    """Still pixels that stand out by brightness OR sit on a strong edge — a
    yellow number on a pale sky has little luma contrast but a crisp outline."""
    still = seg.std(0) < 5
    mean = seg.mean(0)
    gy, gx = np.gradient(mean)
    edge = np.hypot(gx, gy) > 28
    return still & ((np.abs(mean - np.median(mean)) > 45) | edge)


def _dilate(m: np.ndarray, r: int = 1) -> np.ndarray:
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _largest_blob(mask: np.ndarray) -> np.ndarray:
    """Largest 8-connected component (masks are ~120x90, so plain BFS is fine)."""
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    h, w = mask.shape
    for y, x in zip(*np.where(mask)):
        if seen[y, x]:
            continue
        stack, comp = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            comp.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(comp) > len(best):
            best = comp
    out = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        out[y, x] = True
    return out


def overlay_region(f: np.ndarray, bounds_s: list[float], crop: tuple[int, int, int, int],
                   full_w: int, full_h: int) -> list[int] | None:
    """Box (x, y, w, h, source px) of the rank graphic INSIDE the picture.

    Within one moment a static wall looks just like a static graphic. What
    separates them: the rank graphic sits in the same place in EVERY moment,
    while static scenery changes with each clip. So per-moment still/contrast
    masks are dilated and voted; pixels present in >= 4 of 5 moments win."""
    sy, sx = f.shape[1] / full_h, f.shape[2] / full_w
    cw, ch, cx, cy = crop
    x0, y0 = int(cx * sx), int(cy * sy)
    x1, y1 = int((cx + cw) * sx), int((cy + ch) * sy)
    m = max(2, int(0.03 * (y1 - y0)))                 # stay off the picture edge
    y0, y1, x0, x1 = y0 + m, y1 - m, x0 + m, x1 - m
    votes = np.zeros((y1 - y0, x1 - x0), dtype=np.int32)
    for s0, s1 in zip(bounds_s, bounds_s[1:]):
        a, z = int(s0 * HZ) + 2, int(s1 * HZ) - 1
        if z - a >= 3:
            votes += _dilate(_still_mask(f[a:z, y0:y1, x0:x1]), 1)
    mask = votes >= 4
    mask[mask.mean(1) > 0.5] = False                  # full-width lines are edges, not text
    mask[:, mask.mean(0) > 0.5] = False
    if mask.mean() < 0.002:
        return None
    mask = _largest_blob(mask)              # stray still pixels elsewhere don't widen it
    if mask.mean() < 0.002:
        return None
    ys, xs = np.where(mask)
    pad = 0.03 * full_w
    bx0 = max(1, (x0 + xs.min()) / sx - pad)
    by0 = max(1, (y0 + ys.min()) / sy - pad)
    bx1 = min(full_w - 2, (x0 + xs.max() + 1) / sx + pad)
    by1 = min(full_h - 2, (y0 + ys.max() + 1) / sy + pad)
    if (bx1 - bx0) * (by1 - by0) > 0.12 * cw * ch:    # too big to be a rank graphic
        return None
    return [int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)]


def _peaks(s: np.ndarray, min_gap: int) -> list[int]:
    order = np.argsort(-s)
    picked: list[int] = []
    for i in order:
        if s[i] <= 0.08:
            break
        if all(abs(int(i) - p) >= min_gap for p in picked):
            picked.append(int(i))
        if len(picked) >= 24:
            break
    return sorted(picked)


def choose(fused: np.ndarray, sig: dict[str, np.ndarray], n: int,
           min_len: float = 2.5) -> dict:
    """Pick start, 4 interior boundaries and end. The start/end may be the
    video edges (no intro/outro) or strong early/late peaks (intro/outro)."""
    cands = _peaks(fused, int(1.2 * HZ))
    starts = [0] + [c for c in cands if c < 0.25 * n]
    ends = [n] + [c for c in cands if c > 0.8 * n]
    inner = [c for c in cands]
    best, best_score = None, -1e9
    ml = int(min_len * HZ)
    for st in starts:
        for en in ends:
            pool = [c for c in inner if st + ml <= c <= en - ml]
            for combo in itertools.combinations(pool, 4):
                b = [st, *combo, en]
                lens = np.diff(b)
                if lens.min() < ml:
                    continue
                cv = lens.std() / lens.mean()
                edge = 0.25 * (fused[st] if st else 0) + 0.25 * (fused[en - 1] if en < n else 0)
                score = fused[list(combo)].sum() + edge - 1.2 * cv
                if score > best_score:
                    best, best_score = b, score
    if best is None:
        return {"bounds": [], "confidence": 0.0}
    inner_b = best[1:5]
    agree = [sum(sig[k][i] > 0.35 for k in ("cut", "overlay", "audio")) for i in inner_b]
    lens = np.diff(best)
    regularity = float(max(0.0, 1 - lens.std() / lens.mean()))
    strengths = [float(fused[i]) for i in inner_b]
    strength = 0.5 * float(np.mean(strengths)) + 0.5 * min(strengths)   # weakest link
    agreement = float(np.mean([min(a, 2) / 2 for a in agree]))
    # If the video carries a rank graphic (most boundaries show an overlay
    # change), a boundary WITHOUT one is probably not a rank change.
    ov = [sig["overlay"][i] > 0.35 for i in inner_b]
    consistency = 1.0 if sum(ov) < 2 else sum(ov) / 4
    conf = round(0.45 * agreement + 0.35 * strength + 0.2 * regularity, 3)
    return {"bounds": [round(x / HZ, 2) for x in best], "confidence": conf,
            "agreement": [int(a) for a in agree], "strength": round(strength, 3),
            "regularity": round(regularity, 3), "overlay_consistency": round(consistency, 2)}


def detect(path: Path, info: dict, has_audio: bool, order: str = "countdown") -> dict:
    f = frames(path, info["width"], info["height"])
    n = len(f)
    if n < 10 * HZ:
        return {"status": "too_short", "confidence": 0.0, "bounds": []}
    loud = probe.loudness_curve(path) if has_audio else []
    sig = {"cut": _norm(cut_signal(f)), "overlay": _norm(overlay_change(f)),
           "audio": _norm(audio_signal(loud, n))}
    fused = 0.35 * sig["cut"] + 0.45 * sig["overlay"] + 0.2 * sig["audio"]
    res = choose(fused, sig, n)
    crop = content_crop(f, info["width"], info["height"])
    res.update(content_crop=list(crop), order=order, duration=round(n / HZ, 2))
    if not res["bounds"]:
        res["status"] = "no_structure"
        return res
    b = res["bounds"]
    ranks = [5, 4, 3, 2, 1] if order == "countdown" else [1, 2, 3, 4, 5]
    box = overlay_region(f, b, crop, info["width"], info["height"])
    res["overlay_box"] = box
    moments = [{"rank": ranks[k], "start": round(s0 + 0.3, 2), "end": round(s1 - 0.15, 2),
                "overlay_box": box} for k, (s0, s1) in enumerate(zip(b, b[1:]))]
    res["moments"] = moments
    res["status"] = "auto" if res["confidence"] >= CONF_SAVE else "needs_review"
    return res
