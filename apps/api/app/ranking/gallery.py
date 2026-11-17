"""
Local review gallery: data/ranking/gallery/index.html

One card per concept with the video (watermarked draft before approval, final
after), the contact sheet, QA results, every moment's source and license, the
upload metadata, and the exact commands to approve, edit or reject it. Static
HTML with relative paths, so it opens straight from disk (file://) or through
`python -m app.ranking gallery --serve` on 127.0.0.1 only.
"""
from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from urllib.parse import quote

from ..config import DATA_DIR
from . import channels
from .db import RANKING_DIR, output_root
from .gallery_server import FAVICON_SVG, make_server

# inline, so the icon also works when the page is opened from file://
FAVICON = "data:image/svg+xml," + quote(FAVICON_SVG.decode())

STATUS = {"pending_approval": ("Needs review", "amber"), "approved": ("Approved", "blue"),
          "rendered": ("Rendered", "green"), "rejected": ("Rejected", "grey")}

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--ink:#e9ecf2;--dim:#9aa3b2;
--amber:#f5b301;--green:#22c55e;--blue:#60a5fa;--grey:#6b7280;--red:#ef4444}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;
align-items:center;flex-wrap:wrap}h1{font-size:18px;margin:0 12px 0 0}
.f button{background:var(--card);color:var(--ink);border:1px solid var(--line);
border-radius:999px;padding:6px 12px;cursor:pointer}.f button.on{border-color:var(--ink)}
main{padding:20px 24px;display:grid;gap:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;
display:grid;grid-template-columns:300px 1fr;gap:20px}
.card>div{min-width:0}td{overflow-wrap:anywhere}
@media(max-width:820px){.card{grid-template-columns:1fr;padding:14px}
main,header{padding-left:16px;padding-right:16px}}
video{width:100%;aspect-ratio:9/16;background:#000;border-radius:10px}
.sheet img{width:100%;border-radius:8px;margin-top:10px;cursor:zoom-in}
h2{font-size:17px;margin:0 0 4px}.meta{color:var(--dim);margin-bottom:12px}
.chip{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;
font-weight:600;color:#111}.amber{background:var(--amber)}.green{background:var(--green)}
.blue{background:var(--blue)}.grey{background:var(--grey);color:#fff}
table{border-collapse:collapse;width:100%;margin:8px 0 14px}
td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12px}
.qa{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 14px}
.qa span{font-size:12px;padding:3px 8px;border-radius:6px;border:1px solid var(--line)}
.qa .ok{color:var(--green)}.qa .bad{color:var(--red);border-color:var(--red)}
pre{white-space:pre-wrap;background:#0b0d11;border:1px solid var(--line);border-radius:8px;
padding:10px;margin:6px 0 14px;font-size:12.5px}
code.cmd{display:block;background:#0b0d11;border:1px solid var(--line);border-radius:8px;
padding:8px 10px;margin:4px 0;font-size:12.5px;cursor:copy;overflow-x:auto}
.warn{color:var(--amber)}.none{color:var(--dim);padding:40px;text-align:center}
"""

JS = """
document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.f button').forEach(x=>x.classList.toggle('on',x===b));
 document.querySelectorAll('.card').forEach(c=>c.style.display=
  (b.dataset.s==='all'||c.dataset.s===b.dataset.s)?'':'none');});
document.querySelectorAll('code.cmd').forEach(c=>c.onclick=()=>{
 navigator.clipboard&&navigator.clipboard.writeText(c.textContent);
 c.style.borderColor='#22c55e';setTimeout(()=>c.style.borderColor='',600);});
"""


def _rel(path: str | Path, base: Path) -> str:
    return escape(os.path.relpath(Path(path), base).replace(os.sep, "/"))


def _work_dir(cfg: dict, concept: dict) -> tuple[Path | None, bool]:
    root = output_root(cfg["_output_dir"])
    final = root / "renders" / f"concept_{concept['id']}"
    draft = root / "drafts" / f"concept_{concept['id']}"
    if (final / "final.mp4").exists():
        return final, False
    if (draft / "preview.mp4").exists():
        return draft, True
    return None, False


def _card(con, c: dict, base: Path) -> str:
    cfg = channels.load(c["channel"])
    work, is_draft = _work_dir(cfg, c)
    label, color = STATUS.get(c["status"], (c["status"], "grey"))
    p = c["payload"]
    media = '<div class="none">Not rendered yet<br>run <code>preview %d</code></div>' % c["id"]
    qa_html = meta_html = ""
    if work:
        vid = work / ("preview.mp4" if is_draft else "final.mp4")
        poster = work / "thumbnail.jpg"
        media = (f'<video controls preload="metadata" src="{_rel(vid, base)}" '
                 f'poster="{_rel(poster, base)}"></video>')
        if (work / "preview_sheet.png").exists():
            s = _rel(work / "preview_sheet.png", base)
            media += f'<a class="sheet" href="{s}" target="_blank"><img src="{s}" alt="contact sheet"></a>'
        if (work / "qa.json").exists():
            rep = json.loads((work / "qa.json").read_text())
            qa_html = '<div class="qa">' + "".join(
                f'<span class="{"ok" if k["pass"] else "bad"}" title="{escape(k["detail"])}">'
                f'{"✓" if k["pass"] else "✗"} {escape(k["check"])}</span>' for k in rep["checks"]) + "</div>"
        if (work / "metadata.json").exists():
            m = json.loads((work / "metadata.json").read_text())
            meta_html = (f"<b>Upload title</b><pre>{escape(m['title'])}</pre>"
                         f"<b>Description</b><pre>{escape(m['description'])}</pre>")
    src = {r["id"]: dict(r) for r in con.execute(
        "SELECT id, path, license, license_verified FROM sources")}
    rows = "".join(
        f"<tr><td><b>#{r['rank']}</b></td><td>{escape(r['caption'])}</td>"
        f"<td>{escape(Path(r['path']).name)}<br><span class='meta'>{r['in']:.1f}–{r['out']:.1f}s</span></td>"
        f"<td>{escape(r['license'])} {'✓' if src.get(r['source_id'], {}).get('license_verified') else '<span class=warn>unverified</span>'}"
        f"<br><span class='meta'>{escape(r.get('attribution') or '—')}</span></td></tr>"
        for r in sorted(p["ranks"], key=lambda r: -r["rank"]))
    cmds = []
    if c["status"] == "pending_approval":
        cmds = [f"python -m app.ranking approve {c['id']} --by YOUR_NAME",
                f"python -m app.ranking batch-approve {c['id']} --by YOUR_NAME",
                f"python -m app.ranking show {c['id']} > c{c['id']}.json   # then: edit {c['id']} c{c['id']}.json",
                f"python -m app.ranking reject {c['id']}"]
    elif c["status"] in ("approved", "rendered"):
        cmds = [f"python -m app.ranking render {c['id']}",
                f"python -m app.ranking upload {c['id']} --channel {c['channel']} --dry-run"]
    draft_note = ' <span class="chip amber">DRAFT preview</span>' if is_draft else ""
    return f"""<section class="card" data-s="{escape(c['status'])}"><div>{media}</div><div>
<h2>#{c['id']} · {escape(c['title'])}</h2>
<div class="meta"><span class="chip {color}">{label}</span>{draft_note} · {escape(c['category'])}
 · {escape(cfg['display_name'])} · hook “{escape(p['copy']['hook'])}” · outro “{escape(p['copy']['outro'])}”
 {('· approved by ' + escape(c['approved_by'])) if c['approved_by'] else ''}</div>
{qa_html}<table><tr><th>Rank</th><th>Caption</th><th>Source / range</th><th>License</th></tr>{rows}</table>
{meta_html}{''.join(f'<code class="cmd">{escape(x)}</code>' for x in cmds)}</div></section>"""


def build(con, out: Path | None = None) -> Path:
    out = out or (RANKING_DIR / "gallery" / "index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    concepts = [dict(r) | {"payload": json.loads(r["payload"])}
                for r in con.execute("SELECT * FROM concepts ORDER BY id DESC")]
    cards = "".join(_card(con, c, out.parent) for c in concepts) or \
        '<div class="none">No concepts yet — run <code>batch</code>.</div>'
    filters = "".join(f'<button data-s="{k}">{v[0]}</button>' for k, v in STATUS.items())
    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ranking Review</title><link rel="icon" type="image/svg+xml" href="{FAVICON}"><style>{CSS}</style></head><body>
<header><h1>Ranking Shorts — review</h1><a href="clips.html" style="color:#60a5fa">Clip browser →</a><div class="f"><button class="on" data-s="all">All</button>{filters}</div>
<span class="meta">Publishing is disabled by default. Commands run from <code>apps/api</code>.</span></header>
<main>{cards}</main><script>{JS}</script></body></html>""")
    return out


def serve(port: int = 8765) -> None:
    """Serve data/ on localhost only (Range-capable, quiet on disconnects);
    the gallery's relative paths resolve. Read-only: no approve/publish."""
    rel = (RANKING_DIR / "gallery" / "index.html").relative_to(DATA_DIR)
    server = make_server(DATA_DIR, port)
    print(f"gallery: http://127.0.0.1:{port}/{rel.as_posix()}   (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ngallery stopped")
    finally:
        server.server_close()
