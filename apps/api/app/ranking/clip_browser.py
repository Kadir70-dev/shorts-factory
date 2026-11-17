"""
Clip browser: data/ranking/gallery/clips.html

Every catalogued source with its video, a clickable timeline of its detected
moments (colour = original rank, click to play just that clip), and a row per
clip: thumbnail, original rank, timestamps, detected topic and subject,
detection confidence, interest score, and the exact command to correct it.
Rights are shown per source, with the reason whenever a source is NOT
selectable. The reference inventory appears as study material only.
"""
from __future__ import annotations

import json
import os
import subprocess
from html import escape
from pathlib import Path

from . import reference, topic
from .db import REUSABLE_LICENSES, RANKING_DIR
from .gallery import CSS, FAVICON

RANK_COLORS = {5: "#64748b", 4: "#0ea5e9", 3: "#22c55e", 2: "#f59e0b", 1: "#ef4444"}

EXTRA_CSS = """
.tl{position:relative;height:26px;background:#0b0d11;border:1px solid var(--line);
border-radius:6px;margin:8px 0 12px;overflow:hidden}
.tl span{position:absolute;top:0;bottom:0;cursor:pointer;color:#111;font:700 12px/26px system-ui;
text-align:center;opacity:.9}.tl span:hover{opacity:1;outline:2px solid #fff}
img.th{width:96px;border-radius:6px;display:block}
.bad{color:var(--red)}.ok{color:var(--green)}.ref{border-color:var(--amber)}
nav a{color:var(--blue);margin-right:14px}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch}.tbl table{min-width:640px}
"""

JS = """
document.querySelectorAll('.tl span, button.play').forEach(el => el.onclick = () => {
  const v = document.getElementById(el.dataset.v), a = +el.dataset.a, b = +el.dataset.b;
  v.currentTime = a; v.play();
  const stop = () => { if (v.currentTime >= b) { v.pause(); v.removeEventListener('timeupdate', stop); } };
  v.addEventListener('timeupdate', stop);
});
document.querySelectorAll('code.cmd').forEach(c => c.onclick = () => {
  navigator.clipboard && navigator.clipboard.writeText(c.textContent);
  c.style.borderColor = '#22c55e'; setTimeout(() => c.style.borderColor = '', 600); });
"""


def rights_status(src: dict) -> tuple[bool, list[str]]:
    """Same rules as db.eligible_source_sql(), spelled out for a human."""
    why = []
    if src["license"] not in REUSABLE_LICENSES:
        why.append(f"license '{src['license']}' is not reusable")
    if not src["license_verified"]:
        why.append("license not verified (verify-source)")
    if src["kind"] == "compilation" and not src["underlying_rights_verified"]:
        why.append("rights to the clips inside this compilation not verified")
    if src["provenance_ref"] and not src["permission_proof"]:
        why.append(f"traced to reference video {src['provenance_ref']}: no permission on file")
    return not why, why


def _thumb(seg: dict, src_path: str, out_dir: Path) -> Path:
    out = out_dir / f"seg_{seg['id']}.jpg"
    if not out.exists():
        t = (seg["start"] + seg["end"]) / 2
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", src_path, "-frames:v", "1", "-vf", "scale=192:-2", "-q:v", "4",
                        "-y", str(out)], capture_output=True, timeout=60)
    return out


def _rel(p: str | Path, base: Path) -> str:
    return escape(os.path.relpath(Path(p), base).replace(os.sep, "/"))


def _source_card(con, src: dict, base: Path, thumbs: Path) -> str:
    ok, why = rights_status(src)
    seg = json.loads(src["segmentation"] or "{}")
    segs = [dict(r) for r in con.execute(
        "SELECT g.*, (SELECT MIN(concept_id) FROM segment_usage u WHERE u.segment_id=g.id) "
        "AS used FROM segments g WHERE source_id=? ORDER BY start", (src["id"],))]
    vid = f"v{src['id']}"
    dur = max(src["duration"] or 1, 0.1)
    spans = "".join(
        f'<span data-v="{vid}" data-a="{g["start"]}" data-b="{g["end"]}" '
        f'style="left:{100 * g["start"] / dur:.2f}%;width:{100 * (g["end"] - g["start"]) / dur:.2f}%;'
        f'background:{RANK_COLORS.get(g["source_rank"], "#a78bfa")}" '
        f'title="{g["start"]:.1f}–{g["end"]:.1f}s">{"#" + str(g["source_rank"]) if g["source_rank"] else ""}</span>'
        for g in segs if not g["disabled"])
    rows = ""
    for g in segs:
        label = g["label"] or ""
        subj = topic.subject(label, src["title"] or "", src["origin_url"] or "")
        sig = json.loads(g["signals"] or "{}")
        rows += (
            f"<tr><td><img class='th' src='{_rel(_thumb(g, src['path'], thumbs), base)}' alt=''></td>"
            f"<td><b>{'#' + str(g['source_rank']) if g['source_rank'] else '—'}</b><br>"
            f"<span class='meta'>seg {g['id']}{' · manual' if g['manual'] else ''}"
            f"{' · disabled' if g['disabled'] else ''}</span></td>"
            f"<td>{g['start']:.2f}–{g['end']:.2f}s<br><span class='meta'>{g['end'] - g['start']:.1f}s</span>"
            f"<br><button class='play' data-v='{vid}' data-a='{g['start']}' data-b='{g['end']}'>▶ play</button></td>"
            f"<td>{escape(g['category'] or src['category'] or 'unknown')}<br>"
            f"<span class='meta'>{escape(subj or '—')} · {escape(label[:48]) or 'no label'}</span></td>"
            f"<td>conf {g['confidence'] or 0:.2f}<br><span class='meta'>interest {g['score']:.2f}"
            f"{'<br>rank box ' + str(sig['overlay_box']) if sig.get('overlay_box') else ''}</span></td>"
            f"<td>{'concept #' + str(g['used']) if g['used'] else '<span class=meta>unused</span>'}</td>"
            f"<td><code class='cmd'>python -m app.ranking segment {g['id']} --start {g['start']:.2f} "
            f"--end {g['end']:.2f} --label \"…\"</code></td></tr>")
    detect = ""
    if src["kind"] == "compilation":
        b = seg.get("bounds") or []
        detect = (f"<div class='meta'>Top-5 detection: <b>{escape(str(seg.get('status', 'not run')))}</b>"
                  f" · confidence {seg.get('confidence', 0)} · signal agreement {seg.get('agreement')}"
                  f" · picture crop {escape(src['content_crop'] or 'full')}"
                  f" · rank box {seg.get('overlay_box')}</div>")
        if b:
            detect += (f"<code class='cmd'>python -m app.ranking top5-set {src['id']} --bounds "
                       f"{','.join(f'{x:.2f}' for x in b)}</code>")
    chips = (f"<span class='chip {'green' if ok else 'grey'}'>{'selectable' if ok else 'not selectable'}</span> "
             f"<span class='chip blue'>{escape(src['kind'])}</span> ")
    reasons = "".join(f"<div class='bad'>✗ {escape(w)}</div>" for w in why)
    return f"""<section class="card {'ref' if src['provenance_ref'] else ''}"><div>
<video id="{vid}" controls preload="metadata" src="{_rel(src['path'], base)}"></video></div><div>
<h2>{escape(Path(src['path']).name)}</h2>
<div class="meta">{chips}topic <b>{escape(src['category'] or 'unknown')}</b>
 ({src['topic_confidence'] or 0:.2f}) · {src['duration']:.1f}s · {src['width']}×{src['height']}
 · license {escape(src['license'])} {'✓' if src['license_verified'] else '✗'}
 {('· clips inside ' + ('✓' if src['underlying_rights_verified'] else '✗')) if src['kind'] == 'compilation' else ''}
 · {escape(src['attribution'] or '')}</div>{reasons}{detect}
<div class="tl">{spans}</div>
<div class="tbl"><table><tr><th></th><th>Rank</th><th>Time</th><th>Topic / subject</th><th>Detection</th><th>Used</th><th>Correct</th></tr>{rows or '<tr><td colspan=7 class=meta>no clips saved</td></tr>'}</table></div>
</div></section>"""


def build(con, out: Path | None = None) -> Path:
    out = out or (RANKING_DIR / "gallery" / "clips.html")
    thumbs = out.parent / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    sources = [dict(r) for r in con.execute(
        "SELECT * FROM sources ORDER BY kind DESC, id DESC")]
    cards = "".join(_source_card(con, s, out.parent, thumbs) for s in sources)
    refs = con.execute("SELECT channel, COUNT(*), SUM(downloaded) FROM reference_videos "
                       "GROUP BY channel").fetchall()
    ref_html = ""
    for ch, n, local in refs:
        st = reference.study(con, ch)
        top = escape(st["most_repeated"][0][0]) if st.get("most_repeated") else ""
        ref_html += (f"<section class='card ref' style='display:block'><h2>Reference: @{escape(ch)}</h2>"
                     f"<div class='meta'>{n} videos catalogued as metadata · {local or 0} with local media · "
                     f"study only, never selectable · {st.get('distinct_titles', 0)} distinct titles; "
                     f"most repeated: “{top}” ×{st['most_repeated'][0][1] if top else 0}</div></section>")
    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Clip Browser</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}"><style>{CSS}{EXTRA_CSS}</style></head><body>
<header><h1>Ranking Shorts — clip browser</h1><nav><a href="index.html">Concept review →</a></nav>
<span class="meta">Colours = original rank (#5 grey … #1 red). Click a band to play that clip.</span></header>
<main>{ref_html}{cards}</main><script>{JS}</script></body></html>""")
    return out
