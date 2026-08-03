"""
Pure-FFmpeg renderer — builds the finished vertical MP4 from a SceneGraph.

Two things changed from the original:

  BRANDED. Typography, colour grade, captions, watermark, lower thirds, intro
  stamp and end card all come from `app.brand` rather than being hard-coded here.
  Change config/brand/k70.yaml and every future render re-skins, which is what
  makes a thousand Shorts look like one channel.

  VARIED. Caption animation, transition palette, camera motion, zoom travel and
  grade variant come from the per-video variety plan, so consecutive uploads
  don't share a rhythm. The variation is bounded: it can change how a cut feels,
  never whether the video still looks like this channel.

Structural constraint worth knowing before editing: scene clips are built
separately and concatenated with `-c copy`. That keeps the separately-built
voiceover and captions in exact sync — but it also means a true cross-clip
transition is impossible. Every transition is therefore expressed WITHIN a clip
and preserves its exact duration. Breaking that rule desyncs the whole video.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..brand import brand_manager, theme_for
from ..brand import overlays as ov
from ..brand.theme import BrandTheme
from ..config import settings
from ..schemas.scene import Scene, SceneGraph
from .compliance import policy as compliance_policy

# Locally-rendered visuals already carry the brand palette and their own motion.
# Grading them again shifts the colours away from the palette they were drawn in,
# and Ken Burns on an animated chart is just wobble.
_PRERENDERED = ("dataviz", "motion_gfx", "branded", "threejs")


async def render(graph: SceneGraph, out: Path) -> str:
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    W, H, fps = graph.width, graph.height, graph.fps
    theme = theme_for(graph, "compositor")
    grade = theme.grade(graph.variety.get("grade", ""))
    zoom = _zoom_travel(graph)

    # 1. build each scene as its own clip (background + overlays, no audio)
    clips: list[Path] = []
    for i, scene in enumerate(graph.scenes):
        clip = work / f"scene_{i:02d}.mp4"
        transition = brand_manager.transition(graph, scene.transition_in)
        await _scene_clip(scene, clip, W, H, fps, theme, grade, zoom,
                          transition=transition,
                          hook=(i == 0))
        clips.append(clip)

    # 2. concat scene clips
    concat_list = work / "scenes.txt"
    # ABSOLUTE paths: the concat demuxer resolves relative entries against the
    # LIST's directory, so a relative path silently becomes work/work/scene_00.mp4
    # whenever the process cwd isn't the repo root.
    concat_list.write_text(
        "\n".join(f"file '{c.resolve()}'" for c in clips))
    silent = work / "silent.mp4"
    await _ff("-f", "concat", "-safe", "0", "-i", str(concat_list),
              "-c", "copy", "-y", str(silent))

    # 3. brand furniture + captions + audio, in one pass
    await _finish(graph, silent, out, theme)
    return str(out)


def _zoom_travel(graph: SceneGraph) -> float:
    from .variety import ZOOM_STYLES
    return ZOOM_STYLES.get(graph.variety.get("zoom", "standard"), 0.15)


# --------------------------------------------------------------------------- #
# Scene clips
# --------------------------------------------------------------------------- #
async def _scene_clip(scene: Scene, out: Path, W: int, H: int, fps: int,
                      theme: BrandTheme, grade, zoom: float,
                      transition: str | None = None,
                      hook: bool = False) -> None:
    v = scene.visual
    dur = scene.duration_sec
    prerendered = v.type in _PRERENDERED

    # Locally-rendered graphics already contain their own type; adding the scene
    # overlay typography on top would double up the headline and the number.
    draw = ("" if prerendered else
            _join(ov.scene_overlay_filters(scene, theme, W, H, hook=hook)))
    if settings().brand_identity_enabled and not prerendered:
        lower = next((item for item in scene.overlays
                      if item.type == "lower_third"), None)
        if lower:
            _, lower_draws = ov.lower_third_filters(
                theme, lower.text, lower.sub or "", W, H, 0, dur)
            draw += _join(lower_draws)

    # Layered cinematic stack (opt-in). Unchanged behaviour, now grade-aware.
    if settings().layered_render and v.layers and not prerendered:
        from . import layers as _layers
        try:
            tail = _mblur() + _transition(transition or scene.transition_in, dur, hook, H)
            if await _layers.compose(scene, out, W, H, fps, draw=draw,
                                     grade=grade.ffmpeg(), tail=tail, hook=hook):
                return
        except Exception as e:                   # noqa: BLE001
            print(f"[layers] {scene.id}: composite error ({type(e).__name__}: "
                  f"{str(e)[:90]}) → simple render", flush=True)
        if not (v.asset_path and Path(v.asset_path).exists()):
            bg = next((ly for ly in v.layers if ly.role == "background"
                       and ly.asset_path and Path(ly.asset_path).exists()), None)
            if bg:
                v.asset_path = bg.asset_path
                v.type = "ai_image" if bg.kind == "ai_image" else "image"
                if v.motion == "none":
                    v.motion = "ken_burns"

    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
           f"crop={W}:{H},setsar=1,fps={fps}")

    if v.asset_path and Path(v.asset_path).exists():
        is_img = v.asset_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        if prerendered:
            # already 1080x1920, already branded, already animating
            inp = ["-i", v.asset_path]
            vf = f"{fit},vignette=PI/{grade.vignette}" + draw
        elif is_img and v.motion != "none":
            inp = ["-i", v.asset_path]
            vf = (_kenburns_vf(v.motion, W, H, fps, dur, zoom)
                  + f",{grade.ffmpeg()}" + draw)
        elif is_img:
            inp = ["-loop", "1", "-t", f"{dur}", "-i", v.asset_path]
            vf = f"{fit},{grade.ffmpeg()}" + draw
        else:
            inp = ["-stream_loop", "-1", "-t", f"{dur}", "-i", v.asset_path]
            vf = f"{fit},{grade.ffmpeg()}" + draw
    else:
        color = theme.hex("bg", v.fallback_color)
        inp = ["-f", "lavfi", "-t", f"{dur}",
               "-i", f"color=c={color}:s={W}x{H}:r={fps}"]
        vf = "setsar=1" + draw

    vf += _mblur() + _transition(transition or scene.transition_in, dur, hook, H)

    await _ff(*inp, "-vf", vf, "-t", f"{dur}",
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
              "-an", "-y", str(out))


def _kenburns_vf(motion: str, W: int, H: int, fps: int, dur: float,
                 travel: float) -> str:
    """zoompan that animates a still over `dur`.

    `travel` is the variety plan's zoom style — a restrained video moves ~8% over
    a shot, an assertive one ~22%. Pre-scaling 2x keeps the motion smooth and
    gives the handheld shake room to work without exposing a border.
    """
    n = max(1, round(dur * fps))
    base = (f"scale={2*W}:{2*H}:force_original_aspect_ratio=increase,"
            f"crop={2*W}:{2*H}")
    sx, sy = "sin(on/4)*5", "cos(on/5)*5"
    cx = f"x='iw/2-(iw/zoom/2)+{sx}'"
    cy = f"y='ih/2-(ih/zoom/2)+{sy}'"
    t = max(0.04, min(0.35, travel))
    if motion == "zoom_out":
        zp = (f"zoompan=z='max({1 + t:.3f}-{t:.3f}*on/{n},1.0)':d={n}:"
              f"{cx}:{cy}:s={W}x{H}:fps={fps}")
    elif motion == "pan_lr":
        zp = (f"zoompan=z='{1 + t * 0.9:.3f}':d={n}:x='(iw-iw/zoom)*on/{n}+{sx}':"
              f"{cy}:s={W}x{H}:fps={fps}")
    else:                                        # zoom_in / ken_burns
        zp = (f"zoompan=z='min(1.0+{t:.3f}*on/{n},{1 + t:.3f})':d={n}:"
              f"{cx}:{cy}:s={W}x{H}:fps={fps}")
    return f"{base},{zp},setsar=1"


def _mblur() -> str:
    return ",tmix=frames=3:weights='1 1 1'" if settings().ffmpeg_motion_blur else ""


def _transition(kind: str, dur: float, hook: bool, H: int) -> str:
    """Duration-PRESERVING transitions.

    Every one of these is an in-clip effect. The scene clips are concatenated with
    `-c copy` so the separately-built voiceover and captions stay in exact sync;
    a real cross-clip transition would consume frames and desync the whole video.
    """
    if hook:
        # The hook never eases in — the opening frame has to land instantly.
        d = min(0.18, max(0.0, dur / 6))
        return f",fade=t=out:st={max(0.0, dur - d):.2f}:d={d:.2f}" if d else ""

    parts: list[str] = []
    short = min(0.20, max(0.05, dur / 6))
    if kind == "dip_to_black":
        d = min(0.34, max(0.12, dur / 5))
        parts.append(f"fade=t=in:st=0:d={d:.2f}")
    elif kind == "crossfade":
        d = min(0.45, max(0.18, dur / 4))
        parts.append(f"fade=t=in:st=0:d={d:.2f}")
    elif kind == "push_up":
        # crop's y accepts an expression, so the frame slides up into place from a
        # slightly over-scaled source — motion without spending any frames.
        rise = 0.055
        parts.append(
            f"scale=-1:ih*{1 + rise:.3f},"
            f"crop=iw:ih/{1 + rise:.3f}:0:'if(lt(t,0.34),"
            f"(ih-ih/{1 + rise:.3f})*(1-t/0.34),0)'")
        parts.append(f"fade=t=in:st=0:d={short:.2f}")
    elif kind == "whip":
        parts.append(f"fade=t=in:st=0:d={min(0.12, short):.2f}")
    elif kind == "slide_l":
        parts.append(
            f"crop=iw:ih:'if(lt(t,0.28),(iw*0.06)*(1-t/0.28),0)':0")
        parts.append(f"fade=t=in:st=0:d={short:.2f}")
    elif kind == "fade":
        parts.append(f"fade=t=in:st=0:d={short:.2f}")
    # `cut` adds nothing on entry

    d_out = min(0.18, max(0.0, dur / 7))
    if d_out:
        parts.append(f"fade=t=out:st={max(0.0, dur - d_out):.2f}:d={d_out:.2f}")
    return ("," + ",".join(parts)) if parts else ""


def _join(filters: list[str]) -> str:
    return ("," + ",".join(filters)) if filters else ""


# --------------------------------------------------------------------------- #
# Finish pass — brand furniture, captions, audio
# --------------------------------------------------------------------------- #
def _dominant_windows(graph: SceneGraph) -> list[tuple[float, float]]:
    """Spans where something else owns the frame and captions must yield: a hero
    stat, and kinetic-typography beats where the words are already on screen."""
    out, acc = [], 0.0
    for s in graph.scenes:
        big_stat = (any(o.type == "stat" and o.sub for o in s.overlays)
                    and s.visual.type not in _PRERENDERED)
        if big_stat or s.visual.type == "motion_gfx":
            out.append((acc, acc + s.duration_sec))
        acc += s.duration_sec
    return out


async def _finish(graph: SceneGraph, silent: Path, out: Path,
                  theme: BrandTheme) -> None:
    """Brand furniture + captions + audio in ONE pass.

    A second encode of the full timeline just to add a watermark would cost a
    complete re-compress on every one of thousands of renders, so everything that
    operates on absolute time is composited here together.

    Input order is deliberate: video, then brand PLATES, then audio. The overlay
    chain builder numbers its inputs from a fixed offset, and interleaving audio
    inputs would shift those indices out from under it.
    """
    from ..brand import assets as brand_assets

    work = out.parent
    W, H = graph.width, graph.height
    total = graph.total_duration_sec
    a = graph.audio
    pol = compliance_policy()

    paths = await brand_assets.ensure_assets(theme)

    # ---- collect brand elements -------------------------------------------- #
    plates: list[ov.ImageOverlay] = []
    draws: list[str] = []
    mute = _dominant_windows(graph)

    outro_plates, outro_draws, outro_window = ov.outro_filters(
        theme, W, H, total, cta=_cta_text(graph),
        disclaimer=(graph.meta.disclaimer or pol.disclaimer_short
                    if pol.show_on_outro else ""),
        endcard=paths.get("endcard.png"))
    hide_wm = outro_window[0] if outro_window[1] > outro_window[0] else None
    if outro_window[1] > outro_window[0]:
        mute.append(outro_window)

    wm_plates, wm_draws = ov.watermark_overlay(
        theme, W, H, paths.get("watermark.png"), hide_after=hide_wm, total=total)
    plates += wm_plates
    draws += wm_draws

    if pol.show_early and (graph.meta.disclaimer or pol.disclaimer_short):
        dp, dd = ov.disclaimer_filters(
            theme, W, H, graph.meta.disclaimer or pol.disclaimer_short,
            start=1.2, duration=min(3.2, max(1.6, total * 0.14)),
            strip=paths.get("disclaimer_strip.png"))
        plates += dp
        draws += dd

    draws += ov.intro_filters(theme, W, H)
    plates += outro_plates
    draws += outro_draws

    ass = work / "captions.ass"
    ass.write_text(ov.caption_ass(
        graph, theme, animation=graph.variety.get("caption_animation", "word_pop"),
        mute_windows=mute))

    # ---- assemble the filtergraph ------------------------------------------ #
    inputs: list[str] = ["-i", str(silent)]
    filters: list[str] = [f"[0:v]subtitles={_esc_path(ass)}[vsub]"]
    label = "vsub"

    plate_inputs, plate_chain, label = ov.build_image_overlay_chain(
        plates, label, first_input_index=1)
    inputs += plate_inputs
    filters += plate_chain

    if draws:
        filters.append(f"[{label}]{','.join(draws)}[vout]")
        label = "vout"
    maps: list[str] = ["-map", f"[{label}]"]

    # ---- audio -------------------------------------------------------------- #
    idx = 1 + len(plates)
    have_vo = bool(a.voiceover_path and Path(a.voiceover_path).exists())
    have_mus = bool(a.music_path and Path(a.music_path).exists())
    duck = have_vo and have_mus and a.duck_music

    vo_idx = mus_idx = None
    if have_vo:
        vo_idx = idx
        inputs += ["-i", a.voiceover_path]
        idx += 1
    if have_mus:
        mus_idx = idx
        inputs += ["-stream_loop", "-1", "-t", f"{total:.3f}", "-i", a.music_path]
        idx += 1

    sfx_cues = []
    for cue in graph.sfx:
        f = _sfx_file(cue.sound)
        if f.exists():
            sfx_cues.append((idx, cue))
            inputs += ["-i", str(f)]
            idx += 1

    mix: list[str] = []
    if have_vo:
        base = f"[{vo_idx}:a]{_AFMT},volume={_g(a.voiceover_gain_db)}"
        filters.append(f"{base},asplit=2[vo][vokey]" if duck else f"{base}[vo]")
        mix.append("[vo]")

    if have_mus:
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
            filters.append("[mus0][vokey]sidechaincompress=threshold=0.04:"
                           "ratio=8:attack=20:release=320[mus]")
            mix.append("[mus]")
        else:
            mix.append("[mus0]")

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


def _cta_text(graph: SceneGraph) -> str:
    """The end card's line: the closing beat's headline, else the final narration."""
    if not graph.scenes:
        return ""
    last = graph.scenes[-1]
    headline = next((o.text for o in last.overlays if o.type == "headline"), "")
    return headline or last.narration


def _esc_path(p: Path) -> str:
    """Escape a path for use inside a filtergraph value (the subtitles filter)."""
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


_AFMT = "aformat=sample_rates=44100:channel_layouts=stereo"


def _sfx_file(sound: str) -> Path:
    from . import sfx as sfx_mod
    return sfx_mod.sfx_path(sound)


def _env_expr(envelope) -> str:
    """Piecewise-linear (in amplitude) volume expression from music keyframes, for
    `volume=volume=<expr>:eval=frame`. Commas are escaped so the expression
    survives filter_complex parsing; the level holds flat outside the range so the
    bed swells and settles instead of jumping."""
    pts = sorted(((k.at, _g(k.gain_db)) for k in envelope), key=lambda p: p[0])
    if not pts:
        return "1.0"
    e = f"{pts[-1][1]:.5f}"
    for i in range(len(pts) - 2, -1, -1):
        t0, a0 = pts[i]
        t1, a1 = pts[i + 1]
        dt = (t1 - t0) or 1e-6
        seg = f"({a0:.5f}+({a1 - a0:.5f})*(t-{t0:.3f})/{dt:.3f})"
        e = f"if(lt(t\\,{t1:.3f})\\,{seg}\\,{e})"
    t0, a0 = pts[0]
    return f"if(lt(t\\,{t0:.3f})\\,{a0:.5f}\\,{e})"


def _g(db: float) -> float:
    return round(10 ** (db / 20), 4)


async def _ff(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(args)[:200]}\n"
                           f"{err.decode()[:600]}")
