"""
FFmpeg multi-layer cinematic compositor (Phase 3).

Consumes `scene.visual.layers` (filled by the Phase-2 Storyboard Agent) and
stacks them BACK-TO-FRONT into a single silent scene clip:

    background  →  subject (alpha overlay)  →  fx (screen blend)

Doctrine (CPU-first, anime/cartoon storytelling, no GPU):
  • ALL motion + compositing is FFmpeg. Never AnimateDiff/RIFE/depth models.
  • Parallax is faked with 2 planes given DIFFERENT drift rates — the far
    background barely moves (slow zoompan), the near subject drifts more
    (animated overlay position). 2-layer parallax max; fx is a blend, not a
    parallax plane.
  • Motion is SUBTLE and cinematic — a few px of sinusoidal drift + a ~6% push,
    never a fast snap.
  • Subject alpha is produced ONCE and cached (data/cache/layers/) so the hot
    filtergraph just overlays a ready RGBA still — cheap per frame, and a cache
    hit on re-render. Cutout strategy is config-driven: rembg if available,
    else a CPU-only feathered-oval matte (no extra dependency).

CONTRACT: `compose()` returns True on success, False to tell the caller to fall
back to the simple single-asset render. It NEVER raises for an expected
condition (missing asset, too few planes, low RAM, ffmpeg error) — every one of
those just returns False so the short still ships. This is what makes the whole
layered path safe to gate on and 100% backward compatible: with LAYERED_RENDER
off (or any failure) the renderer behaves exactly as before.

RAM safety (12GB box): a pre-flight `ram.budget_ok()` check refuses to start the
composite when free memory is already below the floor (→ simple render instead),
ffmpeg threads are pinned, and the child's peak RSS is reported for QA.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

from ..config import settings
from ..schemas.scene import Layer, Scene
from . import ram

# Composite at most these roles (back-to-front). "ui" is reserved for Phase 4.
_STACK_ORDER = ("background", "subject", "fx")

# blend modes we expose for the fx plane (anything else → screen).
_BLEND = {"screen", "add", "multiply", "overlay", "normal"}

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
async def compose(scene: Scene, out: Path, W: int, H: int, fps: int, *,
                  draw: str = "", grade: str = "", tail: str = "",
                  hook: bool = False) -> bool:
    """Composite scene.visual.layers → a silent WxH clip at `out`.

    `draw`/`grade`/`tail` are the SAME filter fragments the simple renderer
    applies (overlay drawtext, color grade, motion-blur + dip transition) so a
    layered scene looks consistent with the rest of the short. Each already
    carries its leading comma where present.

    Returns True if it wrote a finished clip; False if the caller should render
    this scene the simple (single-asset) way.
    """
    s = settings()
    if not s.layered_render:
        return False                                  # gate off → simple render
    if s.layered_force_fallback:                      # test hook
        print(f"[layers] {scene.id}: forced fallback → simple render", flush=True)
        return False

    planes = _usable_planes(scene)
    bg = planes.get("background")
    if bg is None:
        return False                                  # no base plate → simple render
    # Compositing one lone plane buys nothing over the simple path. Require the
    # background PLUS at least one of subject/fx (i.e. an actual hero stack).
    extras = [r for r in ("subject", "fx") if r in planes]
    if not extras:
        return False

    # RAM guard — refuse to start a multi-plane filtergraph when memory is already
    # tight; the caller falls back to the lighter single-asset render. On a host
    # where /proc/meminfo is unreadable this is a no-op (never blocks).
    if not ram.budget_ok(s.layered_min_free_mb):
        print(f"[layers] {scene.id}: free RAM {ram.available_mb():.0f}MB < floor "
              f"{s.layered_min_free_mb}MB → graceful simple render", flush=True)
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    dur = scene.duration_sec
    try:
        args = await _build_args(scene, planes, out, W, H, fps, dur,
                                 draw=draw, grade=grade, tail=tail)
    except Exception as e:                            # any prep failure → fallback
        print(f"[layers] {scene.id}: layer prep failed ({type(e).__name__}: "
              f"{str(e)[:90]}) → simple render", flush=True)
        return False

    t0 = time.monotonic()
    ok, err, peak = await _run_ffmpeg(args, threads=s.layered_ffmpeg_threads)
    if not ok or not out.exists() or out.stat().st_size == 0:
        print(f"[layers] {scene.id}: ffmpeg composite failed → simple render\n"
              f"         {err[:200]}", flush=True)
        return False

    free = ram.available_mb()
    free_s = f"{free:.0f}MB" if free is not None else "n/a"
    print(f"[layers] {scene.id}: composited {1 + len(extras)} planes "
          f"({'+'.join(['bg'] + extras)}) in {time.monotonic() - t0:.1f}s "
          f"— ffmpeg peak RSS ~{peak:.0f}MB, free {free_s}", flush=True)
    return True


# --------------------------------------------------------------------------- #
# plane selection
# --------------------------------------------------------------------------- #
def _usable_planes(scene: Scene) -> dict[str, Layer]:
    """The composable layers that actually have a file on disk, keyed by role.
    Only ONE layer per role is composited (first wins); unknown/empty roles and
    layers with no resolvable asset are skipped. fx layers may carry a bare
    filename (e.g. 'scanlines.png') — those are resolved against data/assets/fx/."""
    out: dict[str, Layer] = {}
    for layer in scene.visual.layers:
        if layer.role not in _STACK_ORDER or layer.role in out:
            continue
        resolved = _resolve_asset(layer)
        if resolved:
            layer.asset_path = resolved                # normalize to a real path
            out[layer.role] = layer
    return out


def _fx_dir() -> Path:
    return settings().data_dir / "assets" / "fx"


def _resolve_asset(layer: Layer) -> str | None:
    """Resolve a layer's asset to an existing absolute-ish path, or None. fx
    planes accept a bare filename (in asset_path OR query) resolved against the
    FX asset dir."""
    p = (layer.asset_path or "").strip()
    if p and Path(p).exists():
        return p
    if layer.role == "fx":
        name = (layer.asset_path or layer.query or "").strip()
        if name and "/" not in name and (_fx_dir() / name).exists():
            return str(_fx_dir() / name)
    return None


# --------------------------------------------------------------------------- #
# filtergraph construction
# --------------------------------------------------------------------------- #
async def _build_args(scene: Scene, planes: dict[str, Layer], out: Path,
                      W: int, H: int, fps: int, dur: float, *,
                      draw: str, grade: str, tail: str) -> list[str]:
    s = settings()
    inputs: list[str] = []
    fc: list[str] = []
    ii = 0
    cur = ""

    # ---- background plane: slow zoompan push (far / minimal parallax) -------- #
    bg = planes["background"]
    inputs += _input_args(bg.asset_path, dur)
    fc.append(f"[{ii}:v]{_bg_chain(bg, W, H, fps, dur, s.layered_oversize)}[bg]")
    cur = "[bg]"
    ii += 1

    # ---- subject plane: ready RGBA still overlaid with near-plane drift ------ #
    if "subject" in planes:
        subj = planes["subject"]
        matte = await _prepare_subject(subj, W, H)    # cached rgba png
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(matte)]
        sw = max(2, int(W * s.layered_subject_scale))
        fc.append(f"[{ii}:v]scale={sw}:-1:flags=bicubic,format=rgba,"
                  f"fps={fps}[subj]")
        # parallax: amplitude scales with the layer's `parallax` (near ≈ 0.6).
        amp = subj.parallax * s.layered_drift_px
        anchor = s.layered_subject_anchor
        x = f"(W-w)/2+{amp:.1f}*sin(2*PI*t/7)"
        y = f"(H-h)*{anchor:.3f}+{amp * 0.7:.1f}*sin(2*PI*t/9)"
        fc.append(f"{cur}[subj]overlay=x='{x}':y='{y}':eval=frame:"
                  f"format=auto[comp]")
        cur = "[comp]"
        ii += 1

    # ---- fx plane: looped texture, screen-blended at low opacity ------------ #
    if "fx" in planes:
        fx = planes["fx"]
        inputs += _input_args(fx.asset_path, dur)
        mode = fx.blend if fx.blend in _BLEND else "screen"
        op = max(0.0, min(1.0, fx.opacity))
        # blend in RGB (gbrp) so 'screen' is photometrically correct, not on luma.
        fc.append(f"[{ii}:v]scale={W}:{H},setsar=1,fps={fps},format=gbrp[fxs]")
        fc.append(f"{cur}format=gbrp[cb];[cb][fxs]"
                  f"blend=all_mode={mode}:all_opacity={op:.3f}[comp2]")
        cur = "[comp2]"
        ii += 1

    # ---- final: grade + burned overlays + dip transition (match simple path) -#
    final = f"{cur}setsar=1,format=yuv420p"
    if grade:
        final += f",{grade}"
    final += (draw or "") + (tail or "")
    final += "[vout]"
    fc.append(final)

    # A composited hero beat is a scene clip like any other and is concatenated
    # with `-c copy` alongside them, so it MUST carry the renderer's intermediate
    # encoder settings — mismatched codec parameters break the concat demuxer.
    from .render_ffmpeg import _INTERMEDIATE

    return [
        *inputs,
        "-filter_complex", ";".join(fc),
        "-map", "[vout]",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", *_INTERMEDIATE, "-pix_fmt", "yuv420p", "-r", str(fps),
        "-an", "-y", str(out),
    ]


def _bg_chain(layer: Layer, W: int, H: int, fps: int, dur: float,
              oversize: float) -> str:
    """Background motion: a gentle ~6% push (or pan) with a few px of parallax
    drift scaled by the layer's `parallax` (far plane ≈ 0.1 → barely moves).
    Pre-scales `oversize`× for headroom so the drift never exposes a border."""
    n = max(1, round(dur * fps))
    ow, oh = int(W * oversize), int(H * oversize)
    base = (f"scale={ow}:{oh}:force_original_aspect_ratio=increase,"
            f"crop={ow}:{oh}")
    drift = layer.parallax * 6.0                       # px — far plane: very small
    sx = f"{drift:.2f}*sin(on/22)"
    sy = f"{drift:.2f}*cos(on/26)"
    cx = f"x='iw/2-(iw/zoom/2)+{sx}'"
    cy = f"y='ih/2-(ih/zoom/2)+{sy}'"
    m = layer.motion
    if m == "zoom_out":
        z = f"z='max(1.06-0.06*on/{n},1.0)'"
    elif m == "pan_lr":
        z = "z='1.05'"
        cx = f"x='(iw-iw/zoom)*on/{n}+{sx}'"
    elif m == "none":
        z = "z='1.0'"
    else:                                              # zoom_in / ken_burns
        z = f"z='min(1.0+0.06*on/{n},1.06)'"
    zp = f"zoompan={z}:d={n}:{cx}:{cy}:s={W}x{H}:fps={fps}"
    return f"{base},{zp},setsar=1"


def _input_args(path: str, dur: float) -> list[str]:
    """ffmpeg input args for a plane asset: loop a still for `dur`, or loop a
    video to fill `dur`."""
    if path.lower().endswith(_IMG_EXT):
        return ["-loop", "1", "-t", f"{dur:.3f}", "-i", path]
    return ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", path]


# --------------------------------------------------------------------------- #
# subject alpha matte — produced ONCE, content-addressed, reused across runs
# --------------------------------------------------------------------------- #
def _matte_dir() -> Path:
    d = settings().data_dir / "cache" / "layers"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _prepare_subject(layer: Layer, W: int, H: int) -> Path:
    """Return an RGBA cutout for the subject still, generating + caching it the
    first time. Strategy from `layered_subject_matte`:
        rembg → true cutout (only if the rembg package is importable)
        oval  → CPU-only feathered-elliptical matte (no dependency) [default]
        none  → straight RGBA passthrough (use when the asset already has alpha)
        auto  → rembg if importable, else oval
    On ANY failure we fall back to the oval matte, then to passthrough — the
    compositor must always get a usable file."""
    s = settings()
    src = Path(layer.asset_path)
    mode = (s.layered_subject_matte or "oval").strip().lower()
    sw = max(2, int(W * s.layered_subject_scale))
    key = hashlib.sha1(
        f"{src}:{src.stat().st_mtime_ns}:{mode}:{sw}".encode()).hexdigest()[:20]
    cached = _matte_dir() / f"subj_{key}.png"
    if cached.exists() and cached.stat().st_size > 0:
        return cached                                  # cache hit — no work

    if mode == "auto":
        mode = "rembg" if _rembg_available() else "oval"

    if mode == "rembg":
        try:
            return await _matte_rembg(src, cached)
        except Exception as e:
            print(f"[layers] rembg cutout failed ({type(e).__name__}) → oval "
                  f"matte", flush=True)
            mode = "oval"

    if mode == "none":
        await _matte_passthrough(src, cached, sw)
        return cached

    await _matte_oval(src, cached, sw)
    return cached


def _rembg_available() -> bool:
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


async def _matte_rembg(src: Path, out: Path) -> Path:
    """True background removal via rembg (lazy import; CPU onnxruntime). Runs in a
    thread so it never blocks the event loop."""
    from rembg import remove                            # type: ignore

    def _work() -> None:
        data = remove(src.read_bytes())                 # PNG bytes w/ alpha
        out.write_bytes(data)

    await asyncio.to_thread(_work)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("rembg produced no output")
    return out


async def _matte_oval(src: Path, out: Path, sw: int) -> None:
    """CPU-only feathered ELLIPTICAL alpha — a believable foreground vignette
    cutout with NO model dependency. Generated once on a single frame (so the
    per-pixel geq runs exactly once, then it's cached). Alpha falls smoothly to 0
    toward the frame edge so the subject reads as a soft-edged near-plane element
    over the background rather than a hard rectangle."""
    # Normalized radius from center; feather the outer ~22% of each axis.
    a_expr = ("clip(255*(1-(pow((2*X/W-1)/0.92\\,2)+pow((2*Y/H-1)/0.96\\,2)))*"
              "3.2\\,0\\,255)")
    vf = (f"scale={sw}:-1:flags=bicubic,format=rgba,"
          f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{a_expr}'")
    ok, err, _ = await _run_ffmpeg(
        ["-i", str(src), "-vf", vf, "-frames:v", "1", "-y", str(out)],
        threads=settings().layered_ffmpeg_threads)
    if not ok or not out.exists():
        # last resort: a plain rectangular RGBA still (no feather) so compose runs.
        await _matte_passthrough(src, out, sw)


async def _matte_passthrough(src: Path, out: Path, sw: int) -> None:
    """Straight RGBA still (keeps existing alpha if the source already has it)."""
    ok, err, _ = await _run_ffmpeg(
        ["-i", str(src), "-vf", f"scale={sw}:-1:flags=bicubic,format=rgba",
         "-frames:v", "1", "-y", str(out)],
        threads=settings().layered_ffmpeg_threads)
    if not ok or not out.exists():
        raise RuntimeError(f"could not prepare subject matte: {err[:160]}")


# --------------------------------------------------------------------------- #
# ffmpeg runner with thread pin + child peak-RSS readout
# --------------------------------------------------------------------------- #
async def _run_ffmpeg(args: list[str], *, threads: int) -> tuple[bool, str, float]:
    """Run ffmpeg with a pinned thread count (CPU-safe). Returns
    (ok, stderr_tail, child_peak_rss_mb). Never raises — the caller decides what
    a failure means (almost always: fall back to the simple render)."""
    full = ["ffmpeg", "-hide_banner", "-loglevel", "error",
            "-threads", str(max(1, threads)),
            "-filter_complex_threads", str(max(1, threads)), *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *full, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
    except Exception as e:                              # ffmpeg missing / spawn fail
        return False, f"{type(e).__name__}: {e}", ram.child_peak_mb()
    return proc.returncode == 0, err.decode(errors="replace"), ram.child_peak_mb()
