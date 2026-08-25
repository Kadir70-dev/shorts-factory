#!/usr/bin/env python3
"""generate_gallery.py — build a fully static, self-contained browse UI.

Output: gallery/index.html — one file, no build step, no server deps.
Filters: provider, kind, grade, free-text search (client-side over embedded JSON).
Thumbnails: hotlinked from providers (we host nothing); lazy-loaded; click-to-copy asset id.

Usage: python3 scripts/generate_gallery.py [data/assets.jsonl] [gallery/index.html]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CC0 Asset Index — Gallery</title>
<style>
  :root { --bg:#121216; --panel:#1c1c22; --text:#e8e8ec; --muted:#9a9aa5; --accent:#ffb02e; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.4 system-ui,sans-serif; }
  header { position:sticky; top:0; background:var(--panel); padding:12px 16px; display:flex; gap:10px;
           flex-wrap:wrap; align-items:center; border-bottom:1px solid #2a2a33; z-index:10; }
  header input, header select { background:#121216; color:var(--text); border:1px solid #33333d;
           border-radius:6px; padding:7px 10px; font-size:14px; }
  header input[type=search] { flex:1; min-width:200px; }
  .count { color:var(--muted); }
  main { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; padding:16px; }
  .card { background:var(--panel); border:1px solid #2a2a33; border-radius:10px; overflow:hidden;
          display:flex; flex-direction:column; }
  .card img { width:100%; aspect-ratio:1; object-fit:cover; background:#0c0c0f; }
  .card .noimg { width:100%; aspect-ratio:1; display:flex; align-items:center; justify-content:center;
          color:var(--muted); background:#0c0c0f; font-size:12px; text-align:center; padding:8px; }
  .card .body { padding:10px; display:flex; flex-direction:column; gap:6px; flex:1; }
  .card .name { font-weight:600; }
  .card .meta { color:var(--muted); font-size:12px; }
  .badges { display:flex; gap:5px; flex-wrap:wrap; }
  .badge { font-size:11px; padding:2px 7px; border-radius:20px; background:#26262e; color:var(--muted); }
  .badge.kit { background:#3d2e12; color:var(--accent); }
  .badge.gold { background:#3d3412; color:#ffd75e; }
  .card .id { font-family:ui-monospace,monospace; font-size:11px; color:var(--muted);
          cursor:pointer; word-break:break-all; }
  .card .id:hover { color:var(--accent); }
  .card a { color:var(--accent); text-decoration:none; font-size:12px; }
  #toast { position:fixed; bottom:18px; left:50%; transform:translateX(-50%); background:var(--accent);
          color:#121216; padding:8px 16px; border-radius:20px; font-weight:600; display:none; }
</style>
</head>
<body>
<header>
  <strong>CC0 Asset Index</strong>
  <input type="search" id="q" placeholder="Search name, tags, description...">
  <select id="provider"><option value="">All providers</option></select>
  <select id="kind"><option value="">All kinds</option>
    <option>kit</option><option>model</option><option>hdri</option><option>material</option><option>scene</option>
  </select>
  <select id="grade"><option value="">Active (hide archived)</option>
    <option value="all">Include archived</option><option value="gold">Gold only</option>
  </select>
  <span class="count" id="count"></span>
</header>
<main id="grid"></main>
<div id="toast">asset id copied</div>
<script id="data" type="application/json">
"""

HTML_TAIL = """
</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const grid = document.getElementById('grid');
const providers = [...new Set(DATA.map(r => r.source.provider))].sort();
const ps = document.getElementById('provider');
providers.forEach(p => { const o = document.createElement('option'); o.textContent = p; ps.appendChild(o); });

function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function render() {
  const q = document.getElementById('q').value.toLowerCase().trim();
  const prov = ps.value, kind = document.getElementById('kind').value, grade = document.getElementById('grade').value;
  const terms = q.split(/\\s+/).filter(Boolean);
  let hits = DATA.filter(r => {
    if (prov && r.source.provider !== prov) return false;
    if (kind && r.kind !== kind) return false;
    if (grade === '' && r.grade === 'archive') return false;
    if (grade === 'gold' && r.grade !== 'gold') return false;
    const hay = (r.name + ' ' + r.tags.join(' ') + ' ' + r.description).toLowerCase();
    return terms.every(t => hay.includes(t));
  });
  // kits first, then gold, then name
  hits.sort((a,b) => (b.kind==='kit')-(a.kind==='kit') || (b.grade==='gold')-(a.grade==='gold') || a.name.localeCompare(b.name));
  const shown = hits.slice(0, 500);
  document.getElementById('count').textContent = hits.length + ' assets' + (hits.length > 500 ? ' (showing first 500)' : '');
  grid.innerHTML = shown.map(r => `
    <div class="card">
      ${r.preview_url
        ? `<img loading="lazy" src="${esc(r.preview_url)}" alt="${esc(r.name)}" onerror="this.outerHTML='<div class=noimg>no preview</div>'">`
        : `<div class="noimg">${esc(r.kind)} pack<br>see provider page</div>`}
      <div class="body">
        <div class="name">${esc(r.name)}</div>
        <div class="badges">
          <span class="badge ${r.kind}">${r.kind}</span>
          ${r.grade === 'gold' ? '<span class="badge gold">gold</span>' : ''}
          <span class="badge">${esc(r.source.provider)}</span>
        </div>
        <div class="meta">${r.tags.slice(0,6).map(esc).join(' · ')}</div>
        <div class="id" title="click to copy id" onclick="copyId('${esc(r.id)}')">${esc(r.id)}</div>
        <a href="${esc(r.source.url)}" target="_blank" rel="noopener">source page ↗</a>
      </div>
    </div>`).join('');
}

function copyId(id) {
  navigator.clipboard.writeText(id).then(() => {
    const t = document.getElementById('toast');
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 1200);
  });
}

document.querySelectorAll('header input, header select').forEach(el => el.addEventListener('input', render));
render();
</script>
</body>
</html>
"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "assets.jsonl")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "gallery", "index.html")
    records = [json.loads(l) for l in open(src) if l.strip()]
    # keep gallery payload lean
    slim = [
        {k: r.get(k) for k in ("id", "name", "kind", "grade", "tags", "description", "preview_url")}
        | {"source": {"provider": r["source"]["provider"], "url": r["source"]["url"]}}
        for r in records
    ]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(HTML_HEAD)
        json.dump(slim, f, separators=(",", ":"))
        f.write(HTML_TAIL)
    print(f"gallery: {len(records)} assets -> {out} ({os.path.getsize(out) / 1e6:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
