"""
Orchestrator for a long-form ambience job: spec in, finished master out.

Stages, all resumable — each writes a file and is skipped if that file already
exists, because a 4K loop render is measured in hours and losing it to a typo in
a later stage would be painful:

    plate  -> render the static 4K hearth (once)
    loop   -> render + encode exactly one loop period
    audio  -> synthesise + write the seamless stereo loop
    master -> stream-copy the loop to full length, mux continuous audio
    qa     -> verify duration, resolution, fps, streams, loop seam
    seo    -> title/description/tags JSON + thumbnail PNG

This mirrors how the rest of the factory is driven (a YAML preset selects the
creative parameters, code stays generic), so a second ambience theme — rain on a
window, a thunderstorm — is a new preset plus a new scene module, not a new
pipeline.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .audio import AudioConfig, render_audio, seam_error, write_wav
from .compositor import Compositor, SceneConfig
from .encode import EncodeConfig, build_master, open_frame_writer, probe
from .hearth import build_plate
from .imaging import write_png


@dataclass
class AmbienceSpec:
    slug: str = "cozy_fireplace"
    total_seconds: float = 7200.0          # exactly 2 hours
    loop_seconds: float = 90.0
    width: int = 3840
    height: int = 2160
    fps: int = 60
    seed: int = 7
    sim_divisor: int = 3
    crf: int = 17
    preset: str = "medium"
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    thumbnail_prompt: str = ""

    def scene(self) -> SceneConfig:
        return SceneConfig(
            width=self.width, height=self.height, fps=self.fps,
            loop_seconds=self.loop_seconds, sim_divisor=self.sim_divisor,
            seed=self.seed,
        )


def _log(msg: str) -> None:
    print(f"[ambience] {time.strftime('%H:%M:%S')}  {msg}", flush=True)


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def render_loop(spec: AmbienceSpec, out: Path, *, comp: Compositor | None = None,
                progress_every: int = 60) -> Compositor:
    """Render one loop period straight into an x264 encoder over a pipe."""
    cfg = spec.scene()
    comp = comp or Compositor(cfg)
    enc = EncodeConfig(crf=spec.crf, preset=spec.preset)

    proc = open_frame_writer(out, spec.width, spec.height, spec.fps, enc)
    assert proc.stdin is not None
    t0 = time.time()
    try:
        for i in range(cfg.frames):
            proc.stdin.write(comp.frame(i).tobytes())
            if progress_every and i and i % progress_every == 0:
                el = time.time() - t0
                fps_now = i / el
                eta = (cfg.frames - i) / max(fps_now, 1e-6)
                _log(f"loop frame {i}/{cfg.frames}  {fps_now:.2f} fps  eta {eta/60:.1f} min")
        proc.stdin.close()
    except BrokenPipeError as exc:
        err = (proc.stderr.read().decode() if proc.stderr else "")
        raise RuntimeError(f"encoder died mid-render:\n{err}") from exc

    if proc.wait() != 0:
        err = (proc.stderr.read().decode() if proc.stderr else "")
        raise RuntimeError(f"encoder exited {proc.returncode}:\n{err}")

    _log(f"loop encoded in {(time.time()-t0)/60:.1f} min -> {out.name} "
         f"({out.stat().st_size/1e6:.1f} MB)")
    return comp


def render_audio_loop(spec: AmbienceSpec, out: Path) -> float:
    cfg = AudioConfig(seconds=spec.loop_seconds, seed=spec.seed + 400)
    a = render_audio(cfg)
    write_wav(out, a)
    err = seam_error(a)
    _log(f"audio {out.name}  peak={float(np.abs(a).max()):.3f}  "
         f"rms={float(np.sqrt((a**2).mean())):.4f}  seam_ratio={err:.3f}")
    return err


def render_thumbnail(spec: AmbienceSpec, comp: Compositor, out: Path) -> None:
    """A frame chosen for a big, well-formed flame rather than an arbitrary one."""
    cfg = spec.scene()
    probe_ids = range(0, cfg.frames, max(1, cfg.frames // 40))
    best = max(probe_ids, key=lambda i: comp.flame.step(i).intensity)
    write_png(out, comp.frame(best))
    _log(f"thumbnail from frame {best} -> {out.name}")


def write_seo(spec: AmbienceSpec, out: Path, extra: dict) -> None:
    out.write_text(json.dumps({
        "title": spec.title,
        "description": spec.description,
        "tags": spec.tags,
        "thumbnail_prompt": spec.thumbnail_prompt,
        "spec": asdict(spec),
        **extra,
    }, indent=2), encoding="utf-8")


def qa(spec: AmbienceSpec, master: Path, seam_ratio: float) -> dict:
    """Hard checks against the brief. Returns a report; raises on a real failure."""
    info = probe(master)
    dur = float(info.get("duration", "0"))
    w, h = int(info.get("width", 0)), int(info.get("height", 0))
    rate = info.get("r_frame_rate", "0/1")
    num, den = (int(x) for x in rate.split("/"))
    fps = num / max(den, 1)

    problems: list[str] = []
    if abs(dur - spec.total_seconds) > 1.0:
        problems.append(f"duration {dur:.2f}s != {spec.total_seconds}s")
    if (w, h) != (spec.width, spec.height):
        problems.append(f"resolution {w}x{h} != {spec.width}x{spec.height}")
    if abs(fps - spec.fps) > 0.01:
        problems.append(f"fps {fps} != {spec.fps}")
    if info.get("channels") != "2":
        problems.append(f"audio channels {info.get('channels')} != 2")
    if info.get("sample_rate") != "48000":
        problems.append(f"sample rate {info.get('sample_rate')} != 48000")
    if seam_ratio > 1.5:
        problems.append(f"audio seam discontinuity ratio {seam_ratio:.2f} > 1.5")

    report = {
        "duration_s": dur, "width": w, "height": h, "fps": fps,
        "size_bytes": int(info.get("size", 0)),
        "video_codec": info.get("codec_name"),
        "audio_channels": info.get("channels"),
        "audio_sample_rate": info.get("sample_rate"),
        "audio_seam_ratio": seam_ratio,
        "loops": int(round(spec.total_seconds / spec.loop_seconds)),
        "problems": problems,
    }
    if problems:
        raise RuntimeError("QA failed: " + "; ".join(problems))
    return report


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def produce(spec: AmbienceSpec, workdir: Path) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    loop_v = workdir / f"{spec.slug}_loop.mp4"
    loop_a = workdir / f"{spec.slug}_loop.wav"
    master = workdir / f"{spec.slug}_2h_4k60.mp4"
    thumb = workdir / f"{spec.slug}_thumbnail.png"
    seo = workdir / f"{spec.slug}_seo.json"

    _log(f"spec: {spec.width}x{spec.height}@{spec.fps}  loop={spec.loop_seconds}s  "
         f"total={spec.total_seconds}s  "
         f"({int(round(spec.total_seconds/spec.loop_seconds))} loops)")

    comp: Compositor | None = None
    if not loop_v.exists():
        _log("building 4K hearth plate...")
        plate = build_plate(spec.width, spec.height, spec.seed)
        comp = Compositor(spec.scene(), plate=plate)
        _log("rendering loop...")
        render_loop(spec, loop_v, comp=comp)
    else:
        _log(f"reusing existing {loop_v.name}")

    seam = 0.0
    if not loop_a.exists():
        _log("synthesising audio...")
        seam = render_audio_loop(spec, loop_a)
    else:
        _log(f"reusing existing {loop_a.name}")

    _log(f"building 2-hour master (stream-copy x"
         f"{int(round(spec.total_seconds/spec.loop_seconds))})...")
    t0 = time.time()
    build_master(loop_v, loop_a, master,
                 total_seconds=spec.total_seconds,
                 loop_seconds=spec.loop_seconds,
                 cfg=EncodeConfig(crf=spec.crf, preset=spec.preset))
    _log(f"master built in {(time.time()-t0)/60:.1f} min")

    if not thumb.exists():
        comp = comp or Compositor(spec.scene())
        render_thumbnail(spec, comp, thumb)

    report = qa(spec, master, seam)
    write_seo(spec, seo, {"qa": report, "outputs": {
        "master": str(master), "thumbnail": str(thumb),
        "loop_video": str(loop_v), "loop_audio": str(loop_a),
    }})
    _log("QA passed: " + json.dumps(report))
    return report
