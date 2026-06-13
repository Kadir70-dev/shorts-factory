"""
Pure-FFmpeg renderer — the no-Remotion fallback.

Produces a real vertical .mp4 from a SceneGraph WITHOUT Node/Remotion: per-scene
backgrounds (image/video/solid) + burned headline/stat overlays + ASS-styled
captions + muxed voiceover & ducked music. Lower production value than Remotion
(no spring physics), but it ships a finished short anywhere ffmpeg runs.

render.py uses this automatically when the Remotion service/CLI is unavailable.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import settings
from ..schemas.scene import Scene, SceneGraph

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
EMPH = {"normal": "white", "alert": "#f5c518", "positive": "#16c784", "negative": "#ea3943"}
# cinematic grade + vignette for the premium documentary look (Vox/Bloomberg)
GRADE = "eq=contrast=1.07:saturation=1.08:brightness=-0.02,vignette=PI/5"


def _stat_windows(graph: SceneGraph) -> list[tuple[float, float]]:
    """[start,end] of scenes whose dominant element is a big stat — captions
    yield to the number there (one-dominant-element rule)."""
    out, acc = [], 0.0
    for s in graph.scenes:
        if any(o.type == "stat" and o.sub for o in s.overlays):
            out.append((acc, acc + s.duration_sec))
        acc += s.duration_sec
    return out


async def render(graph: SceneGraph, out: Path) -> str:
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    W, H, fps = graph.width, graph.height, graph.fps

    # 1. build each scene as its own clip (background + overlays, no audio)
    clips: list[Path] = []
    for i, scene in enumerate(graph.scenes):
        clip = work / f"scene_{i:02d}.mp4"
        await _scene_clip(scene, clip, W, H, fps, hook=(i == 0))
        clips.append(clip)

    # 2. concat scene clips
    concat_list = work / "scenes.txt"
    concat_list.write_text("\n".join(f"file '{c}'" for c in clips))
    silent = work / "silent.mp4"
    await _ff("-f", "concat", "-safe", "0", "-i", str(concat_list),
              "-c", "copy", "-y", str(silent))

    # 3. burn captions (ASS) and mux audio
    ass = work / "captions.ass"
    ass.write_text(_build_ass(graph))
    await _mux(graph, silent, ass, out)
    return str(out)


async def _scene_clip(scene: Scene, out: Path, W: int, H: int, fps: int,
                      hook: bool = False) -> None:
    v = scene.visual
    dur = scene.duration_sec
    draw = _overlay_filters(scene, H, hook=hook)

    # CPU multi-layer cinematic stack (Phase 3). Only when LAYERED_RENDER=1 and the
    # Storyboard Agent populated this beat's layers. The composer reuses the SAME
    # grade / overlay / transition fragments below so a layered scene matches the
    # rest of the short, and returns False on too-few planes / low RAM / any ffmpeg
    # failure → we silently continue to the simple single-asset render. Fully
    # backward compatible: off or on-failure, the original path runs untouched.
    if settings().layered_render and v.layers:
        from . import layers as _layers
        try:
            tail = _mblur() + _transition(dur, hook)
            if await _layers.compose(scene, out, W, H, fps, draw=draw,
                                     grade=GRADE, tail=tail, hook=hook):
                return
        except Exception as e:  # noqa: BLE001 — never let layering break a render
            print(f"[layers] {scene.id}: composite error ({type(e).__name__}: "
                  f"{str(e)[:90]}) → simple render", flush=True)
        # Composite declined/failed AND this layered beat has no single asset of its
        # own → fall back to the BACKGROUND plane's still so the simple render below
        # shows a real frame, never a near-black solid (Phase-4 QA stability fix).
        if not (v.asset_path and Path(v.asset_path).exists()):
            bg = next((ly for ly in v.layers if ly.role == "background"
                       and ly.asset_path and Path(ly.asset_path).exists()), None)
            if bg:
                v.asset_path = bg.asset_path
                v.type = "ai_image" if bg.kind == "ai_image" else "image"
                if v.motion == "none":
                    v.motion = "ken_burns"

    if v.asset_path and Path(v.asset_path).exists():
        is_img = v.asset_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        if is_img and v.motion != "none":
            # still photo -> Ken Burns / pan + subtle handheld shake (never static)
            inp = ["-i", v.asset_path]
            vf = _kenburns_vf(v.motion, W, H, fps, dur) + f",{GRADE}" + draw
        elif is_img:
            inp = ["-loop", "1", "-t", f"{dur}", "-i", v.asset_path]
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},setsar=1,fps={fps},{GRADE}" + draw)
        else:  # video: loop to fill, trim to dur
            inp = ["-stream_loop", "-1", "-t", f"{dur}", "-i", v.asset_path]
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},setsar=1,fps={fps},{GRADE}" + draw)
    else:  # solid color background
        color = v.fallback_color
        inp = ["-f", "lavfi", "-t", f"{dur}",
               "-i", f"color=c={color}:s={W}x{H}:r={fps}"]
        vf = "setsar=1" + draw

    # cinematic motion blur (optional) + duration-preserving dip transitions.
    vf += _mblur() + _transition(dur, hook)

    await _ff(*inp, "-vf", vf, "-t", f"{dur}",
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
              "-an", "-y", str(out))


def _kenburns_vf(motion: str, W: int, H: int, fps: int, dur: float) -> str:
    """zoompan filter that animates a single still over `dur`. Pre-scales 2x so
    the zoom/pan stays smooth (no pixel jitter), then renders WxH frames."""
    n = max(1, round(dur * fps))
    base = (f"scale={2*W}:{2*H}:force_original_aspect_ratio=increase,"
            f"crop={2*W}:{2*H}")
    # Subtle handheld SHAKE baked into the crop window — a few px of sinusoidal
    # drift on each axis. The 2x pre-scale gives ample headroom so the shake never
    # exposes a border. Reads as a living, cinematic camera, not a static frame.
    sx = "sin(on/4)*5"
    sy = "cos(on/5)*5"
    cx = f"x='iw/2-(iw/zoom/2)+{sx}'"
    cy = f"y='ih/2-(ih/zoom/2)+{sy}'"
    # Gentle documentary push (matches the toned-down Remotion cameraFor): ~15%
    # travel over the whole clip, not a fast snap.
    if motion == "zoom_out":
        zp = (f"zoompan=z='max(1.15-0.15*on/{n},1.0)':d={n}:"
              f"{cx}:{cy}:s={W}x{H}:fps={fps}")
    elif motion == "pan_lr":
        zp = (f"zoompan=z='1.14':d={n}:x='(iw-iw/zoom)*on/{n}+{sx}':"
              f"{cy}:s={W}x{H}:fps={fps}")
    else:  # zoom_in / ken_burns / anything else -> slow push in
        zp = (f"zoompan=z='min(1.0+0.15*on/{n},1.15)':d={n}:"
              f"{cx}:{cy}:s={W}x{H}:fps={fps}")
    return f"{base},{zp},setsar=1"


def _mblur() -> str:
    """Optional cinematic motion blur via short frame-blending. OFF by default
    (FFMPEG_MOTION_BLUR=1 to enable) — it costs CPU. Frame count is preserved."""
    return ",tmix=frames=3:weights='1 1 1'" if settings().ffmpeg_motion_blur else ""


def _transition(dur: float, hook: bool) -> str:
    """Duration-PRESERVING dip transitions: a short fade-in (skipped on the hook so
    the opening hits instantly) + a short fade-out at the tail. Each clip keeps its
    EXACT length, so the separately-built voiceover/captions stay perfectly in sync
    while cuts read as soft cinematic dips instead of hard jumps."""
    d = min(0.2, max(0.0, dur / 6))
    if d <= 0:
        return ""
    parts = []
    if not hook:
        parts.append(f"fade=t=in:st=0:d={d:.2f}")
    parts.append(f"fade=t=out:st={max(0.0, dur - d):.2f}:d={d:.2f}")
    return "," + ",".join(parts)


_CHARS = {60: 18, 46: 24, 34: 32}   # chars/line that fit ~1000px at each size


def _overlay_filters(scene: Scene, H: int, hook: bool = False) -> str:
    """drawtext for overlays, with the ONE-dominant-element rule: a big stat is
    the hero (else a single headline); everything else is dropped except a tiny
    source credit. The hook may carry both a headline and the shock number.
    Captions are added later."""
    overlays = scene.overlays
    stat = next((o for o in overlays if o.type == "stat" and o.sub), None)
    headline = next((o for o in overlays if o.type == "headline"), None)
    source = next((o for o in overlays if o.type == "source"), None)

    parts: list[str] = []
    if headline and (hook or not stat):
        y = int(headline.y * H)
        col = EMPH.get(headline.emphasis, "white").replace("#", "0x")
        parts += _dt_wrapped(headline.text, 76 if hook else 60, col, y, box=True)
    if stat:
        y = int(stat.y * H)
        col = EMPH.get(stat.emphasis, "white").replace("#", "0x")
        parts += _dt_wrapped(stat.sub, 168 if hook else 150, col, y, box=False)
        parts += _dt_wrapped(stat.text, 46, "white", y + 180, box=False)
    if source:                      # tiny dim attribution, top of frame
        parts += _dt_wrapped(source.text, 30, "0xd6d6d6", int(0.065 * H), box=False)
    return ("," + ",".join(parts)) if parts else ""


def _dt_wrapped(text: str, size: int, color: str, y: int, box: bool) -> list[str]:
    """Word-wrap into stacked drawtext lines so nothing overflows the frame."""
    import textwrap
    lines = textwrap.wrap(text, width=_CHARS.get(size, 20)) or [text]
    line_h = int(size * 1.25)
    return [_dt(ln, size, color, y + i * line_h, box) for i, ln in enumerate(lines)]


def _dt(text: str, size: int, color: str, y: int, box: bool = False) -> str:
    safe = text.replace(":", r"\:").replace("'", "").replace(",", r"\,")
    b = ":box=1:boxcolor=black@0.6:boxborderw=18" if box else ""
    return (f"drawtext=fontfile={FONT}:text='{safe}':fontsize={size}:"
            f"fontcolor={color}:x=(w-text_w)/2:y={y}:"
            f"borderw=4:bordercolor=black{b}")


def _build_ass(graph: SceneGraph) -> str:
    """Styled karaoke-ish captions, centered-low, heavy outline."""
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV\n"
        "Style: Cap,DejaVu Sans,64,&H00FFFFFF,&H00000000,&H00000000,1,5,2,2,360\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
    ) % (graph.width, graph.height)
    mute = _stat_windows(graph)
    lines = [head]
    for c in graph.captions:
        # one-dominant rule: drop captions that sit under a big stat
        mid = (c.start + c.end) / 2
        if any(s <= mid < e for s, e in mute):
            continue
        lines.append(f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Cap,"
                     f"{c.text.upper()}\n")
    return "".join(lines)


def _ts(sec: float) -> str:
    h = int(sec // 3600); m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


_AFMT = "aformat=sample_rates=44100:channel_layouts=stereo"


def _sfx_file(sound: str) -> Path:
    from . import sfx as sfx_mod
    return sfx_mod.sfx_path(sound)


def _env_expr(envelope) -> str:
    """Piecewise-LINEAR (in amplitude) volume expression from music keyframes,
    for `volume=volume=<expr>:eval=frame`. Commas are escaped (\\,) so the
    expression survives filter_complex parsing. Clamps flat outside the range —
    so the bed swells/settles smoothly between keyframes, never an abrupt jump."""
    pts = sorted(((k.at, _g(k.gain_db)) for k in envelope), key=lambda p: p[0])
    if not pts:
        return "1.0"
    e = f"{pts[-1][1]:.5f}"                      # t >= last keyframe -> hold
    for i in range(len(pts) - 2, -1, -1):
        t0, a0 = pts[i]; t1, a1 = pts[i + 1]
        dt = (t1 - t0) or 1e-6
        seg = f"({a0:.5f}+({a1 - a0:.5f})*(t-{t0:.3f})/{dt:.3f})"
        e = f"if(lt(t\\,{t1:.3f})\\,{seg}\\,{e})"
    t0, a0 = pts[0]
    return f"if(lt(t\\,{t0:.3f})\\,{a0:.5f}\\,{e})"   # t < first keyframe -> hold


async def _mux(graph: SceneGraph, silent: Path, ass: Path, out: Path) -> None:
    """Mux video + audio. Audio chain (premium documentary):
      VO ─┐
           ├─ amix(normalize=0) ─ [a]
      music ─ sidechaincompress(keyed by VO) ──┘   (ducks under narration)
      sfx[i] ─ adelay(cue.at) ─ volume(cue.gain) ──┘  (emphasis-only one-shots)
    Per-stream volumes are honoured (normalize=0), so the mix is deterministic
    and the narration always sits on top."""
    a = graph.audio
    inputs: list[str] = ["-i", str(silent)]
    filters: list[str] = [f"[0:v]subtitles={ass}[v]"]
    maps: list[str] = ["-map", "[v]"]
    idx = 1

    have_vo = bool(a.voiceover_path and Path(a.voiceover_path).exists())
    have_mus = bool(a.music_path and Path(a.music_path).exists())
    duck = have_vo and have_mus and a.duck_music

    vo_idx = mus_idx = None
    if have_vo:
        vo_idx = idx; inputs += ["-i", a.voiceover_path]; idx += 1
    if have_mus:
        # loop the bed to cover the video, but BOUND it to the timeline so amix
        # never keys `duration=first` on an unbounded stream (runaway encode).
        mus_idx = idx
        inputs += ["-stream_loop", "-1", "-t", f"{graph.total_duration_sec:.3f}",
                   "-i", a.music_path]
        idx += 1

    sfx_cues = []
    for cue in graph.sfx:
        f = _sfx_file(cue.sound)
        if f.exists():
            sfx_cues.append((idx, cue)); inputs += ["-i", str(f)]; idx += 1

    mix: list[str] = []

    # Voiceover — split off a key copy for sidechain ducking when music ducks.
    if have_vo:
        base = f"[{vo_idx}:a]{_AFMT},volume={_g(a.voiceover_gain_db)}"
        if duck:
            filters.append(f"{base},asplit=2[vo][vokey]")
        else:
            filters.append(f"{base}[vo]")
        mix.append("[vo]")

    # Music — niche bed with the smart intensity envelope + smooth top/tail
    # fades, then ducked under the VO so speech always stays clear.
    if have_mus:
        total = graph.total_duration_sec
        chain = f"[{mus_idx}:a]{_AFMT}"
        if a.music_fade_in_sec > 0:
            chain += f",afade=t=in:st=0:d={a.music_fade_in_sec:.3f}"
        if a.music_fade_out_sec > 0:
            chain += (f",afade=t=out:st={max(0.0, total - a.music_fade_out_sec):.3f}"
                      f":d={a.music_fade_out_sec:.3f}")
        if a.music_envelope:
            chain += f",volume=volume={_env_expr(a.music_envelope)}:eval=frame"
        else:
            chain += f",volume={_g(a.music_gain_db)}"
        filters.append(f"{chain}[mus0]")
        if duck:
            filters.append(
                "[mus0][vokey]sidechaincompress=threshold=0.04:ratio=8:"
                "attack=20:release=320[mus]"
            )
            mix.append("[mus]")
        else:
            mix.append("[mus0]")

    # SFX — each cue delayed to its timeline position at its own low gain.
    for j, (i, cue) in enumerate(sfx_cues):
        ms = max(0, int(round(cue.at * 1000)))
        filters.append(f"[{i}:a]{_AFMT},adelay={ms}|{ms},"
                       f"volume={_g(cue.gain_db)}[sfx{j}]")
        mix.append(f"[sfx{j}]")

    if len(mix) == 1:
        maps += ["-map", mix[0]]
    elif mix:
        filters.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:"
                       f"duration=first:dropout_transition=0[a]")
        maps += ["-map", "[a]"]

    await _ff(*inputs, "-filter_complex", ";".join(filters), *maps,
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
              "-shortest", "-movflags", "+faststart", "-y", str(out))


def _g(db: float) -> float:
    return round(10 ** (db / 20), 4)


async def _ff(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(args)[:200]}\n{err.decode()[:600]}")
