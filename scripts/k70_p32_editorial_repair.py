#!/usr/bin/env python3
"""P3.2: apply a REVIEWED editorial decision file to a NEW Bitcoin ep01 graph copy.

Fetches only the Wikimedia Commons files named in the decision file (free API,
no keys), builds portrait still plates, and writes a new SceneGraph. The P3.1
input, masters, voiceover and captions are read-only. No TTS, no render.

  .venv/bin/python scripts/k70_p32_editorial_repair.py \
    --graph data/finance_p31/bitcoin_repaired_v1/scene_graph_p31_repaired.json \
    --decisions data/finance_p32/bitcoin_editorial_v1/p32_decisions.json \
    --out-dir data/finance_p32/bitcoin_editorial_v1 --fetch
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))
from tools.k70_scene_engine import editorial_plates as plates  # noqa: E402
from tools.k70_scene_engine import explainer_graphics as graphics  # noqa: E402
from tools.k70_scene_engine.p32_editorial import apply_decisions  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "K70-P32-editorial/1.0 (local documentary review tool)"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get(url: str, tries: int = 5) -> bytes:
    """Polite GET: Wikimedia rate-limits bursts with HTTP 429."""
    for attempt in range(tries):
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                        timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch(source: dict, dest: Path) -> Path:
    """Download a 1800px rendition of one named Commons file (never search)."""
    if dest.is_file():
        return dest
    q = {"action": "query", "format": "json", "prop": "imageinfo", "titles": source["title"],
         "iiprop": "url", "iiurlwidth": 1800}
    data = _get(API + "?" + urllib.parse.urlencode(q))
    page = next(iter(json.loads(data)["query"]["pages"].values()))
    info = (page.get("imageinfo") or [{}])[0]
    if info.get("url") != source["file_url"]:
        raise RuntimeError(f"{source['title']}: Commons file URL changed; re-review")
    url = info.get("thumburl") or info["url"]
    if not url.startswith(("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")):
        raise RuntimeError("unexpected media host")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_get(url))
    return dest


def build(decisions: dict, out: Path, allow_fetch: bool) -> tuple[dict, dict]:
    built, provenance = {}, {}
    for d in decisions["scenes"]:
        sid, action = d["scene_id"], d["action"]
        if action not in ("archival_plate", "triptych", "typography_plate", "graphic_plate"):
            continue
        local = []
        for n, src in enumerate(d.get("sources", [])):
            if src.get("local"):
                path = Path(src["local"])
            else:
                ext = ".png" if src["file_url"].lower().endswith(".png") else ".jpg"
                # title hash: a replaced source never reuses a stale download
                tag = hashlib.sha1(src["title"].encode()).hexdigest()[:8]
                path = out / "assets" / "source" / f"{sid}_{n}_{tag}{ext}"
                if not path.is_file() and not allow_fetch:
                    raise FileNotFoundError(f"{sid}: source not cached; pass --fetch")
                fetch(src, path)
            if not path.resolve().is_relative_to(ROOT / "data"):
                raise ValueError(f"{sid}: source outside repository data/")
            local.append(path)
            provenance.setdefault(sid, []).append({**src, "local": str(path),
                                                   "sha256": _sha(path)})
        plate = out / "assets" / "plates" / f"{sid}.jpg"
        if action == "archival_plate":
            plates.archival_plate(local[0], plate, label=d.get("label", ""),
                                  crop=d.get("crop"), max_h=d.get("max_h", 1060),
                                  text=d.get("text", ()), credit=d.get("credit", ""))
        elif action == "graphic_plate":
            _graphic(d, plate, out)
        elif action == "triptych":
            plates.triptych_plate(list(zip(local, d["labels"])), plate)
        else:
            plates.typography_plate([tuple(x) for x in d["lines"]], plate,
                                    kicker=d.get("kicker", ""))
        built[sid] = str(plate)
    return built, provenance


def _graphic(d: dict, plate: Path, out: Path) -> None:
    """Original K70 explainer graphics; params come from the reviewed decision."""
    kind, p = d["kind"], dict(d.get("params") or {})
    if kind == "map":
        geo = (out / p.pop("geojson")).resolve()
        if not geo.is_relative_to(ROOT / "data") or not geo.is_file():
            raise FileNotFoundError(f"{d['scene_id']}: map data missing at {geo}")
        graphics.map_plate(geo, p.pop("country"), plate, marker=tuple(p.pop("marker")), **p)
    elif kind == "terminal":
        graphics.terminal_plate(p.pop("prefix"), plate, **p)
    elif kind == "shutter":
        graphics.shutter_plate(plate, **p)
    elif kind == "ledger":
        p["rows"] = [tuple(r) for r in p.get("rows", [])]
        graphics.ledger_plate(plate, **p)
    else:
        raise ValueError(f"{d['scene_id']}: unknown graphic kind {kind}")


def _validate_schema(graph: dict) -> None:
    """Pydantic check on a clamped COPY (P0 TTS clips may be < 0.8s)."""
    from app.schemas.scene import SceneGraph
    probe = copy.deepcopy(graph)
    for s in probe["scenes"]:
        if 0 < float(s["duration_sec"]) < 0.8:
            s["duration_sec"] = 0.8
    SceneGraph.model_validate(probe)


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.2 editorial repair on a NEW graph copy")
    ap.add_argument("--graph", type=Path, required=True, help="P3.1 graph, read-only")
    ap.add_argument("--decisions", type=Path, required=True, help="reviewed decision JSON")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--fetch", action="store_true", help="download named Commons files")
    args = ap.parse_args()
    try:
        out = args.out_dir.expanduser().resolve()
        src_path = args.graph.expanduser().resolve()
        if not out.is_relative_to(ROOT / "data") or out == src_path.parent:
            raise ValueError("--out-dir must be a separate folder under data/")
        target = out / "scene_graph_p32.json"
        if target.exists():
            raise FileExistsError(f"{target} exists; refusing to overwrite")
        source = json.loads(src_path.read_text(encoding="utf-8"))
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        built, provenance = build(decisions, out, args.fetch)
        graph, changes = apply_decisions(source, decisions, built)
        _validate_schema(graph)
        changes.update({"source_graph": str(src_path), "source_sha256": _sha(src_path),
                        "provenance": provenance})
        target.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "p32_changes.json").write_text(json.dumps(changes, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
        print(f"P3.2: {len(changes['visuals'])} visual repairs, "
              f"{len(changes['narration'])} narration text fixes, "
              f"{len(changes['transitions'])} crossfade->cut; wrote {target}")
    except (OSError, ValueError, AssertionError, RuntimeError, KeyError,
            json.JSONDecodeError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    main()
