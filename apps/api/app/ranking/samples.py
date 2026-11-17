"""
Locally generated test sources — rights-cleared because they are created here
from ffmpeg's built-in generators (no third-party footage at all).

Each source is a sequence of hard-cut "shots" of moving procedural imagery with
a quiet ambience bed and one sudden visual + audio "payoff" per shot, so scene
detection, interest scoring, near-duplicate detection and the renderer are all
exercised end to end. Also produced, to prove the guards work:

  * a re-encoded, resized copy of source A  (must be caught as a near-duplicate)
  * an unverified source                    (must never be selected)
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

PATTERNS = [
    "testsrc2=s=1280x720:r=30",
    "mandelbrot=s=1280x720:r=30:start_scale=3:end_scale=0.01",
    "life=s=320x180:r=30:mold=10:ratio=0.35:death_color=#1b2a49:life_color=#ffcc33,scale=1280:720:flags=neighbor",
    "cellauto=s=1280x720:r=30:rule=110:random_fill_ratio=0.3",
    "gradients=s=1280x720:r=30:speed=0.06:n=5",
    "smptehdbars=s=1280x720:r=30,hue=H=2*PI*t/3",
]
SPECS = {
    "src_a": {"shots": [(0, 5.5, 3.6), (1, 6.0, 4.1), (4, 5.0, 3.2), (3, 6.5, 4.6)],
              "category": "unexpected", "color": "#ff3b3b"},
    "src_b": {"shots": [(2, 6.0, 4.0), (5, 5.5, 3.5), (0, 6.0, 4.3), (4, 5.0, 3.1)],
              "category": "unexpected", "color": "#33c3ff"},
    "src_c": {"shots": [(1, 5.0, 3.3), (3, 6.0, 4.2), (2, 5.5, 3.8), (5, 6.5, 4.4)],
              "category": "unexpected", "color": "#7dff5a"},
    "src_d": {"shots": [(4, 6.0, 4.0), (2, 6.0, 3.8)], "category": "animals",
              "color": "#ffa63b"},
}


def _ff(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])


def _shot(pattern: int, dur: float, payoff: float, color: str, seed: int, out: Path):
    """One shot: moving pattern, ambience, and a flash + boom at `payoff`."""
    p0, p1 = payoff, payoff + 0.45
    v = (f"{PATTERNS[pattern]},trim=duration={dur},setpts=PTS-STARTPTS,format=yuv420p,"
         f"drawbox=x=0:y=0:w=iw:h=ih:color={color}@0.55:t=fill:enable='between(t,{p0},{p1})',"
         f"drawbox=x=iw*0.3:y=ih*0.3:w=iw*0.4:h=ih*0.4:color=white@0.8:t=fill:"
         f"enable='between(t,{p0 + 0.05},{p0 + 0.25})'")
    a = (f"anoisesrc=d={dur}:c=brown:a=0.05:r=48000:seed={seed}[amb];"
         f"sine=f={160 + seed * 7}:d=0.6:r=48000,volume=6,afade=t=out:st=0.05:d=0.55,"
         f"adelay={int(p0 * 1000)}|{int(p0 * 1000)},apad,atrim=0:{dur}[boom];"
         f"[amb][boom]amix=inputs=2:duration=first:normalize=0,aformat=channel_layouts=stereo[a]")
    _ff(["-f", "lavfi", "-i", v, "-filter_complex", a, "-map", "0:v", "-map", "[a]",
         "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
         "-c:a", "aac", "-b:a", "128k", str(out)])


def generate(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_shots"
    tmp.mkdir(exist_ok=True)
    made, manifest = [], {}
    for n, (name, spec) in enumerate(SPECS.items()):
        parts = []
        for i, (pat, dur, pay) in enumerate(spec["shots"]):
            shot = tmp / f"{name}_{i}.mp4"
            _shot(pat, dur, pay, spec["color"], n * 10 + i, shot)
            parts.append(shot)
        lst = tmp / f"{name}.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        dest = out_dir / f"{name}.mp4"
        _ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])
        made.append(dest)
        manifest[dest.name] = {"license": "original-synthetic", "verified": True,
                               "proof": "generated locally by app.ranking.samples",
                               "attribution": "", "category": spec["category"]}
    # near-duplicate of A: different resolution + bitrate, same content
    dup = out_dir / "src_a_reupload.mp4"
    _ff(["-i", str(out_dir / "src_a.mp4"), "-vf", "scale=960:540", "-c:v", "libx264",
         "-crf", "30", "-preset", "veryfast", "-c:a", "aac", str(dup)])
    manifest[dup.name] = dict(manifest["src_a.mp4"], proof="re-encode of src_a (dup test)")
    made.append(dup)
    # rights NOT verified: catalogued, never selectable
    unv = out_dir / "src_unverified.mp4"
    shutil.copy(out_dir / "src_d.mp4", unv)
    manifest[unv.name] = {"license": "unknown", "verified": False, "category": "unexpected"}
    made.append(unv)
    import yaml
    (out_dir / "licenses.yaml").write_text(yaml.safe_dump(manifest, sort_keys=True))
    shutil.rmtree(tmp)
    (out_dir / "README.txt").write_text(json.dumps(
        {"note": "synthetic test sources; safe to delete"}, indent=1))
    return made
