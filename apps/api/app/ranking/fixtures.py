"""
Ranking-style test compilations with KNOWN boundaries, for measuring the Top-5
segmenter. They are built here from rights-cleared raw clips, so every frame's
provenance is known. They are never presented as real ranking channel videos.

Five deliberately different styles, plus a decoy with only four moments:

  A  rank number inside the picture (top-left), white flash cuts, whoosh
  B  rank number in a static band above the picture, hard cuts, no SFX
  C  1.5 s intro card + 1 s outro, 0.4 s crossfades, number bottom-centre
  D  dip-to-black transitions, number inside the picture (top-right)
  E  hard cuts with a 0.25 s audio gap, number in the band below the picture
  F  decoy: four moments only (must NOT be auto-saved as a Top 5)

Each compilation gets `<name>.truth.json` (boundaries, content box, per-moment
number box) and a licenses.yaml record: kind=compilation, unverified, with the
underlying clip proofs listed so a human can verify both levels.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from .plates import FONT_DIR

W, H, FPS = 540, 960, 30
CW, CH = 540, 405                       # 4:3 picture box
STYLES = {
    "A": {"cy": 300, "num": ("x=16+{cx}", "y={cy}+10"), "trans": "flash", "sfx": True},
    "B": {"cy": 360, "num": ("x=(w-tw)/2", "y=200"), "trans": "cut", "sfx": False},
    "C": {"cy": 300, "num": ("x=(w-tw)/2", "y={cy}+{ch}-110"), "trans": "xfade", "sfx": True,
          "intro": 1.5, "outro": 1.0},
    "D": {"cy": 280, "num": ("x={cx}+{cw}-tw-18", "y={cy}+10"), "trans": "dip", "sfx": False},
    "E": {"cy": 260, "num": ("x=30", "y={cy}+{ch}+30"), "trans": "gap", "sfx": False},
    "F": {"cy": 300, "num": ("x=16+{cx}", "y={cy}+10"), "trans": "flash", "sfx": True, "n": 4},
}
LENGTHS = {"A": [5.0, 4.2, 6.0, 3.6, 5.4], "B": [4.0, 5.5, 4.4, 6.2, 4.8],
           "C": [3.8, 5.0, 4.6, 5.6, 4.2], "D": [4.6, 3.8, 5.2, 4.4, 5.8],
           "E": [5.2, 4.6, 3.9, 5.0, 4.4], "F": [5.0, 5.0, 5.0, 5.0]}
XF = 0.4


def _slug_label(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    words = [w for w in slug.split("-") if not w.isdigit()]
    return " ".join(words)


def _ff(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-700:])


def _dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True,
                                text=True).stdout.strip())


def _has_audio(p: Path) -> bool:
    return bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                                "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
                               capture_output=True, text=True).stdout.strip())


def allocate(raw: list[Path], plan: dict[str, list[float]]) -> dict[str, list[tuple[Path, float]]]:
    """Give each compilation windows from DIFFERENT raw clips, never overlapping."""
    dur = {p: _dur(p) for p in raw}
    out: dict[str, list[tuple[Path, float]]] = {}
    turn = 0
    cursor = {p: 0.3 for p in raw}
    for name, lens in plan.items():
        if name == "F":                    # decoy: may reuse footage, never mixed
            cursor = {p: 0.3 for p in raw}
        picks, used = [], set()
        for L in lens:
            for k in range(len(raw)):
                p = raw[(turn + k) % len(raw)]
                if p not in used and cursor[p] + L + 0.2 <= dur[p]:
                    picks.append((p, cursor[p]))
                    cursor[p] += L + 0.4
                    used.add(p)
                    turn = (turn + k + 1) % len(raw)
                    break
            else:
                raise RuntimeError(f"not enough raw footage for compilation {name}")
        out[name] = picks
    return out


def _moment(src: Path, t0: float, L: float, rank: int, st: dict, name: str,
            idx: int, out: Path) -> None:
    cy, cx = st["cy"], 0
    nx, ny = (s.format(cx=cx, cy=cy, cw=CW, ch=CH) for s in st["num"])
    font = FONT_DIR / "Anton-Regular.ttf"
    v = (f"[0:v]fps={FPS},scale={CW}:{CH}:force_original_aspect_ratio=increase,"
         f"crop={CW}:{CH},setsar=1[pic];"
         f"color=c=0x101010:s={W}x{H}:r={FPS}:d={L}[bg];[bg][pic]overlay=0:{cy}:shortest=1,"
         f"drawtext=fontfile='{font}':text='TOP 5 ANIMAL MOMENTS':fontsize=46:"
         f"fontcolor=white:x=(w-tw)/2:y=70,"
         f"drawtext=fontfile='{font}':text='{rank}':fontsize=96:fontcolor=0xffd400:"
         f"borderw=5:bordercolor=black:{nx}:{ny}")
    tr = st["trans"]
    if tr == "flash":
        v += ",fade=t=in:st=0:d=0.15:color=white"
    elif tr == "dip":
        v += f",fade=t=in:st=0:d=0.2,fade=t=out:st={L - 0.2:.2f}:d=0.2"
    v += ",format=yuv420p[v]"
    amp = [0.05, 0.12, 0.03, 0.09, 0.06][idx % 5]
    if _has_audio(src):
        a = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={0.6 + idx * 0.25:.2f}[c];"
    else:
        a = f"anoisesrc=d={L}:c=brown:a={amp}:r=48000,aformat=channel_layouts=stereo[c];"
    if st["sfx"]:
        a += ("anoisesrc=d=0.3:c=pink:a=0.5:r=48000,highpass=f=500,afade=t=out:st=0.05:d=0.25,"
              "aformat=channel_layouts=stereo[w];[c][w]amix=inputs=2:duration=first:normalize=0")
    else:
        a += "[c]anull"
    if tr == "gap":
        a += ",volume=enable='lt(t,0.25)':volume=0"
    a += f",apad,atrim=0:{L}[a]"
    _ff(["-ss", f"{t0:.2f}", "-t", f"{L + 0.5:.2f}", "-i", str(src), "-filter_complex",
         v + ";" + a, "-map", "[v]", "-map", "[a]", "-frames:v", str(round(L * FPS)),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "pcm_s16le",
         str(out)])


def _card(text: str, d: float, out: Path) -> None:
    font = FONT_DIR / "Anton-Regular.ttf"
    _ff(["-f", "lavfi", "-i", f"color=c=0x101010:s={W}x{H}:r={FPS}:d={d}",
         "-f", "lavfi", "-i", f"anoisesrc=d={d}:c=brown:a=0.02:r=48000",
         "-vf", f"drawtext=fontfile='{font}':text='{text}':fontsize=60:fontcolor=white:"
                f"x=(w-tw)/2:y=(h-th)/2,format=yuv420p", "-ac", "2",
         "-frames:v", str(round(d * FPS)), "-c:v", "libx264", "-preset", "veryfast",
         "-c:a", "pcm_s16le", str(out)])


def build(raw_dir: Path, out_dir: Path, names: str = "ABCDEF") -> list[dict]:
    raw_lic = yaml.safe_load((raw_dir / "licenses.yaml").read_text()) or {}
    raw = sorted(p for p in raw_dir.glob("*.mp4") if p.name in raw_lic)
    plan = {n: LENGTHS[n] for n in names}
    alloc = allocate(raw, plan)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_parts"
    tmp.mkdir(exist_ok=True)
    licenses, report = {}, []
    for name in names:
        st, lens = STYLES[name], plan[name]
        n = len(lens)
        ranks = list(range(n, 0, -1))
        parts = []
        for i, ((src, t0), L, rank) in enumerate(zip(alloc[name], lens, ranks)):
            p = tmp / f"{name}_{i}.mkv"
            _moment(src, t0, L, rank, st, name, i, p)
            parts.append(p)
        dest = out_dir / f"ranking_style_{name}.mp4"
        intro, outro = st.get("intro", 0.0), st.get("outro", 0.0)
        if st["trans"] == "xfade":
            ins, chain, last, off = [], "", "0:v", 0.0
            for i, p in enumerate(parts):
                ins += ["-i", str(p)]
            alast = "0:a"
            for i in range(1, n):
                off += lens[i - 1] - XF
                chain += (f"[{last}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{i}];"
                          f"[{alast}][{i}:a]acrossfade=d={XF}[y{i}];")
                last, alast = f"x{i}", f"y{i}"
            body = tmp / f"{name}_body.mkv"
            _ff([*ins, "-filter_complex", chain.rstrip(";"), "-map", f"[{last}]", "-map",
                 f"[{alast}]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-c:a", "pcm_s16le", str(body)])
            seq = []
            if intro:
                _card("RANKING THE CRAZIEST", intro, tmp / f"{name}_in.mkv")
                seq.append(tmp / f"{name}_in.mkv")
            seq.append(body)
            if outro:
                _card("FOLLOW FOR MORE", outro, tmp / f"{name}_out.mkv")
                seq.append(tmp / f"{name}_out.mkv")
            starts, t = [], intro
            for i, L in enumerate(lens):
                starts.append(round(t + (XF / 2 if i else 0), 3))
                t += L - XF
            end = round(intro + sum(lens) - XF * (n - 1), 3)
        else:
            seq = parts
            starts, t = [], 0.0
            for L in lens:
                starts.append(round(t, 3))
                t += L
            end = round(t, 3)
        lst = tmp / f"{name}.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in seq))
        _ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy", "-c:a", "aac",
             "-b:a", "160k", "-movflags", "+faststart", str(dest)])
        truth = {"name": name, "style": st["trans"], "moments": n, "bounds": starts + [end],
                 "ranks": ranks, "content_box": [CW, CH, 0, st["cy"]], "size": [W, H],
                 "sources": [{"file": s.name, "t0": t0, "len": L,
                              "origin_url": raw_lic[s.name].get("origin_url", ""),
                              "attribution": raw_lic[s.name].get("attribution", "")}
                             for (s, t0), L in zip(alloc[name], lens)]}
        dest.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1))
        credits = sorted({s["attribution"] for s in truth["sources"]})
        # moment descriptions an annotator would write; here taken from each
        # clip's page slug ("…/video/goose-chasing-a-duck-1234/")
        labels = [_slug_label(s["origin_url"]) for s in truth["sources"]]
        licenses[dest.name] = {
            "kind": "compilation", "license": "owned", "verified": False,
            "proof": "test compilation built locally by app.ranking.fixtures",
            "underlying_proof": "; ".join(s["origin_url"] for s in truth["sources"]),
            "underlying_verified": False, "attribution": "; ".join(credits),
            "category": "animals", "title": f"Ranking-style test compilation {name}",
            "moment_labels": labels,
            "moment_origins": [s["origin_url"] for s in truth["sources"]],
        }
        report.append({"file": dest.name, "moments": n, "style": st["trans"],
                       "duration": round(_dur(dest), 2)})
    (out_dir / "licenses.yaml").write_text(yaml.safe_dump(licenses, sort_keys=True,
                                                          allow_unicode=True))
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return report


def evaluate(det: dict, truth: dict, tol: float = 0.5) -> dict:
    """Boundary error vs ground truth. Interior = the 4 moment-to-moment cuts."""
    if not det.get("bounds") or truth["moments"] != 5:
        return {"saved": det.get("status") == "auto", "confidence": det.get("confidence", 0)}
    db, tb = det["bounds"], truth["bounds"]
    inner = [abs(a - b) for a, b in zip(db[1:5], tb[1:5])]
    edges = [abs(db[0] - tb[0]), abs(db[5] - tb[5])]
    cw, ch, cx, cy = det["content_crop"]
    tw, th, tx, ty = truth["content_box"]
    ix = max(0, min(cx + cw, tx + tw) - max(cx, tx)) * max(0, min(cy + ch, ty + th) - max(cy, ty))
    iou = ix / (cw * ch + tw * th - ix)
    return {"interior_mae": round(sum(inner) / 4, 3), "interior_max": round(max(inner), 3),
            "interior_within_tol": sum(e <= tol for e in inner), "edge_err": [round(e, 2) for e in edges],
            "all_within_tol": all(e <= tol for e in inner + edges), "crop_iou": round(iou, 3),
            "confidence": det["confidence"], "status": det["status"]}
