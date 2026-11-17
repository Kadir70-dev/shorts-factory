"""
Source catalog: register rights-tracked videos, analyse them, suggest moments.

Rights live next to each file as `<video>.license.json`, or in one
`licenses.yaml` manifest in the source directory:

    clip_a.mp4:
      license: licensed            # owned|licensed|cc0|cc-by|public-domain|...
      verified: true               # a HUMAN confirmed the proof below
      proof: "Storyblocks order #1234"
      attribution: "Video by Jane Doe"
      category: animals

Without `verified: true` a source is catalogued and analysed but never selected.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import probe
from .db import CATEGORIES, connect

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def _rights_for(video: Path) -> dict:
    side = video.with_suffix(video.suffix + ".license.json")
    if side.exists():
        return json.loads(side.read_text())
    manifest = video.parent / "licenses.yaml"
    if manifest.exists():
        data = yaml.safe_load(manifest.read_text()) or {}
        return data.get(video.name, {}) or {}
    return {}


def register(con, video: Path, rights: dict | None = None) -> int:
    from . import reference, topic
    video = video.resolve()
    rights = rights if rights is not None else _rights_for(video)
    info = probe.probe(video)
    digest = probe.sha256(video)
    kind = rights.get("kind", "clip")
    if kind not in ("clip", "compilation"):
        raise ValueError(f"kind must be clip or compilation, not {kind!r}")
    cat = rights.get("category", "")
    if cat and cat not in CATEGORIES:
        raise ValueError(f"unknown category {cat!r}; use one of {CATEGORIES}")
    cat, conf, _ = topic.detect(rights.get("title", ""), video.stem,
                                rights.get("origin_url", ""), " ".join(rights.get("moment_labels", [])),
                                declared=cat)
    ref = reference.match_ref(con, video, {"origin": rights.get("origin_url", "")})
    con.execute(
        """INSERT INTO sources (path, sha256, duration, width, height, fps, has_audio,
               license, license_verified, license_proof, attribution, origin_url, category,
               kind, title, provenance_ref, permission_proof, underlying_rights_verified,
               underlying_proof, topic_confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256,
               duration=excluded.duration, width=excluded.width, height=excluded.height,
               fps=excluded.fps, has_audio=excluded.has_audio, license=excluded.license,
               license_verified=excluded.license_verified,
               license_proof=excluded.license_proof, attribution=excluded.attribution,
               origin_url=excluded.origin_url, category=excluded.category,
               kind=excluded.kind, title=excluded.title,
               provenance_ref=excluded.provenance_ref,
               permission_proof=excluded.permission_proof,
               underlying_rights_verified=excluded.underlying_rights_verified,
               underlying_proof=excluded.underlying_proof,
               topic_confidence=excluded.topic_confidence""",
        (str(video), digest, info["duration"], info["width"], info["height"],
         info["fps"], int(info["has_audio"]), rights.get("license", "unknown"),
         int(bool(rights.get("verified", False))), rights.get("proof", ""),
         rights.get("attribution", ""), rights.get("origin_url", ""), cat,
         kind, rights.get("title", ""), ref, rights.get("permission_proof", ""),
         int(bool(rights.get("underlying_verified", False))),
         rights.get("underlying_proof", ""), conf))
    return con.execute("SELECT id FROM sources WHERE path=?", (str(video),)).fetchone()[0]


def _norm(xs: list[float]) -> list[float]:
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    return [0.0] * len(xs) if hi - lo < 1e-9 else [(x - lo) / (hi - lo) for x in xs]


def _smooth(xs: list[float], k: int = 5) -> list[float]:
    h = k // 2
    return [sum(xs[max(0, i - h):i + h + 1]) / len(xs[max(0, i - h):i + h + 1])
            for i in range(len(xs))]


def interest_curve(motion: list[float], loud: list[float]) -> list[float]:
    """0..1 per 0.1 s: motion energy blended with loudness above the median."""
    n = max(len(motion), len(loud))
    motion = (motion + [0.0] * n)[:n]
    if loud:
        med = sorted(loud)[len(loud) // 2]
        loud = [max(0.0, x - med) for x in (loud + [med] * n)[:n]]
        return _smooth([0.55 * m + 0.45 * l for m, l in
                        zip(_norm(_smooth(motion)), _norm(loud))])
    return _smooth(_norm(_smooth(motion)))


def suggest(duration: float, curve: list[float], cuts: list[float], *,
            want: int = 5, min_len: float = 2.5, max_len: float = 7.0) -> list[dict]:
    """Up to `want` non-overlapping windows, each bounded by its shot and placed
    so the interest peak lands ~65 % through — the payoff, not the setup.
    Returns FEWER than `want` when the footage doesn't contain them."""
    hz = probe.SAMPLE_HZ
    bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    # Stock clips are often one continuous shot: split long shots into
    # sub-shots so a 20 s clip can offer several moments, not one.
    spans: list[tuple[float, float]] = []
    for a, b in zip(bounds, bounds[1:]):
        n = max(1, int((b - a) // (max_len * 1.2)))
        step = (b - a) / n
        spans += [(a + i * step, a + (i + 1) * step) for i in range(n)]
    cands: list[dict] = []
    for a, b in spans:
        if b - a < min_len:
            continue
        seg = curve[int(a * hz):int(b * hz)] or [0.0]
        peak_t = a + seg.index(max(seg)) / hz
        length = min(max_len, b - a)
        start = min(max(a, peak_t - 0.65 * length), b - length)
        win = curve[int(start * hz):int((start + length) * hz)] or [0.0]
        score = 0.6 * max(win) + 0.4 * (sum(win) / len(win))
        cands.append({"start": round(start, 2), "end": round(start + length, 2),
                      "score": round(score, 4), "peak": round(peak_t, 2)})
    cands.sort(key=lambda c: -c["score"])
    picked: list[dict] = []
    for c in cands:
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) == want:
            break
    return sorted(picked, key=lambda c: c["start"])


def analyse(con, source_id: int, want: int = 5) -> list[dict]:
    src = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if src["kind"] == "compilation":                    # a Top-5 video: five ranked clips
        from . import compilation
        labels = _rights_for(Path(src["path"])).get("moment_labels")
        res = compilation.analyse_top5(con, source_id, labels=labels)
        return [{"top5": res}] * res["saved"]
    path = Path(src["path"])
    motion = probe.motion_curve(path)
    loud = probe.loudness_curve(path) if src["has_audio"] else []
    curve = interest_curve(motion, loud)
    cuts = probe.scene_cuts(motion)
    found = suggest(src["duration"], curve, cuts, want=want)
    # keep human-corrected segments and any moment a concept already uses;
    # replace only unused machine suggestions
    con.execute("""DELETE FROM segments WHERE source_id=? AND manual=0
                   AND id NOT IN (SELECT segment_id FROM segment_usage)""", (source_id,))
    for s in found:
        con.execute(
            """INSERT OR IGNORE INTO segments (source_id, start, end, score, category, phash)
               VALUES (?,?,?,?,?,?)""",
            (source_id, s["start"], s["end"], s["score"], src["category"],
             probe.segment_hash(path, s["start"], s["end"])))
    return found


def scan(con, directory: Path, want: int = 5) -> list[dict]:
    report = []
    for video in sorted(p for p in directory.rglob("*") if p.suffix.lower() in VIDEO_EXT):
        sid = register(con, video)
        segs = analyse(con, sid, want)
        row = con.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        entry = {"source_id": sid, "file": video.name, "segments": len(segs),
                 "license": row["license"], "verified": bool(row["license_verified"]),
                 "kind": row["kind"], "topic": row["category"] or "unknown"}
        if row["kind"] == "compilation":
            seg = json.loads(row["segmentation"] or "{}")
            entry.update(top5=seg.get("status"), confidence=seg.get("confidence"),
                         underlying_verified=bool(row["underlying_rights_verified"]))
        if row["provenance_ref"]:
            entry["provenance_ref"] = row["provenance_ref"]
        report.append(entry)
    return report


def edit_segment(con, segment_id: int, *, start: float | None = None,
                 end: float | None = None, category: str | None = None,
                 label: str | None = None, disabled: bool | None = None) -> dict:
    seg = con.execute("""SELECT g.*, s.path, s.duration FROM segments g
                         JOIN sources s ON s.id = g.source_id WHERE g.id=?""",
                      (segment_id,)).fetchone()
    if seg is None:
        raise KeyError(f"segment {segment_id} not found")
    st = seg["start"] if start is None else start
    en = seg["end"] if end is None else end
    if not 0 <= st < en <= seg["duration"] + 0.05:
        raise ValueError(f"invalid range {st}-{en} for a {seg['duration']}s source")
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}")
    ph = seg["phash"]
    if (st, en) != (seg["start"], seg["end"]):
        ph = probe.segment_hash(Path(seg["path"]), st, en)
    con.execute(
        """UPDATE segments SET start=?, end=?, phash=?, manual=1,
               category=COALESCE(?, category), label=COALESCE(?, label),
               disabled=COALESCE(?, disabled) WHERE id=?""",
        (st, en, ph, category, label, None if disabled is None else int(disabled),
         segment_id))
    return dict(con.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone())


def add_segment(con, source_id: int, start: float, end: float,
                category: str = "", label: str = "") -> int:
    src = con.execute("SELECT path, category FROM sources WHERE id=?", (source_id,)).fetchone()
    cur = con.execute(
        """INSERT INTO segments (source_id, start, end, score, category, label, phash, manual)
           VALUES (?,?,?,?,?,?,?,1)""",
        (source_id, start, end, 0.5, category or src["category"], label,
         probe.segment_hash(Path(src["path"]), start, end)))
    return cur.lastrowid


def verify_source(con, source_id: int, reviewer: str, *, underlying_proof: str = "",
                  permission_proof: str = "") -> dict:
    """Human confirmation that the license record and its proof are genuine.

    A compilation also needs proof of rights to the clips INSIDE it (the
    original creators'), and a source traced to a reference inventory needs
    recorded permission. Written back to the rights file too, so a re-scan
    keeps the decision."""
    if not reviewer.strip():
        raise ValueError("verification needs a reviewer name")
    src = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if src is None:
        raise KeyError(f"source {source_id} not found")
    if src["license"] in ("", "unknown") or not src["license_proof"]:
        raise ValueError("record a license and proof before verifying")
    underlying = underlying_proof or src["underlying_proof"]
    permission = permission_proof or src["permission_proof"]
    if src["kind"] == "compilation" and not underlying.strip():
        raise ValueError("compilation: record proof of rights to the clips inside it "
                         "(--underlying-proof); the compilation license alone isn't enough")
    if src["provenance_ref"] and not permission.strip():
        raise ValueError(f"traced to reference video {src['provenance_ref']}: record the "
                         "owner's written permission (--permission-proof) first")
    video = Path(src["path"])
    fields = {"verified": True, "verified_by": reviewer, "license": src["license"],
              "proof": src["license_proof"]}
    if src["kind"] == "compilation":
        fields.update(underlying_verified=True, underlying_proof=underlying)
    if permission:
        fields["permission_proof"] = permission
    side = video.with_suffix(video.suffix + ".license.json")
    if side.exists():
        data = json.loads(side.read_text())
        data.update(fields)
        side.write_text(json.dumps(data, indent=2))
    else:
        manifest = video.parent / "licenses.yaml"
        data = (yaml.safe_load(manifest.read_text()) if manifest.exists() else {}) or {}
        data.setdefault(video.name, {}).update(fields)
        manifest.write_text(yaml.safe_dump(data, sort_keys=True, allow_unicode=True))
    con.execute("""UPDATE sources SET license_verified=1, underlying_proof=?, permission_proof=?,
                   underlying_rights_verified=CASE WHEN kind='compilation' THEN 1
                   ELSE underlying_rights_verified END WHERE id=?""",
                (underlying, permission, source_id))
    return dict(con.execute("SELECT id, path, kind, license, license_verified, "
                            "underlying_rights_verified, provenance_ref FROM sources "
                            "WHERE id=?", (source_id,)).fetchone())
