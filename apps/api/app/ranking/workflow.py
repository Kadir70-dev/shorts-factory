"""
Batch workflow:  scan → select → draft review → approve → render → QA → upload dry-run

  batch          scan a folder, create up to N concepts, render a watermarked
                 DRAFT of each, rebuild the gallery, then STOP for human review
  batch-approve  for each reviewed id: approve → final render → QA → metadata →
                 upload DRY-RUN (no network) → gallery

Publishing stays off. Even after batch-approve, nothing leaves the machine until
a channel sets `uploads_enabled: true` and someone runs `upload` without
`--dry-run`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import catalog, channels, commentary, gallery, probe, qa, render, selector
from .db import output_root


def sources_for(con, concept: dict) -> dict[int, dict]:
    ids = {r["source_id"] for r in concept["payload"]["ranks"]}
    rows = con.execute(f"SELECT * FROM sources WHERE id IN ({','.join('?' * len(ids))})",
                       tuple(ids)).fetchall()
    return {r["id"]: {**dict(r), "has_audio": bool(r["has_audio"])} for r in rows}


def render_concept(con, concept_id: int, draft: bool = False) -> dict:
    concept = selector.get(con, concept_id)
    cfg = channels.load(concept["channel"])
    out_dir = output_root(cfg["_output_dir"]) / ("drafts" if draft else "renders")
    work = out_dir / f"concept_{concept_id}"
    if work.exists():
        shutil.rmtree(work)                       # never mix parts from two renders
    manifest = render.render(concept, sources_for(con, concept), cfg, out_dir, draft=draft)
    report = qa.analyze(manifest, concept, cfg)
    meta = commentary.metadata(concept, cfg)
    (work / "qa.json").write_text(json.dumps(report, indent=2))
    (work / "metadata.json").write_text(json.dumps(meta, indent=2))
    for part in work.glob("p*.mkv"):              # intermediates: ~30 MB, not needed
        part.unlink()
    if draft:
        Path(manifest["mp4"]).unlink()            # only the watermarked preview stays
        manifest["mp4"] = ""
    else:
        sha = probe.sha256(Path(manifest["mp4"]))
        con.execute("INSERT INTO renders (concept_id, path, sha256, qa_json, meta_json) "
                    "VALUES (?,?,?,?,?)", (concept_id, manifest["mp4"], sha,
                                           json.dumps(report), json.dumps(meta)))
        con.execute("UPDATE concepts SET status='rendered' WHERE id=? AND status='approved'",
                    (concept_id,))
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"manifest": manifest, "qa": report, "meta": meta, "work": str(work)}


def batch(con, directory: Path | None, channel: str, count: int,
          category: str | None = None, seed: int = 0, draft: bool = True) -> list[dict]:
    if directory is not None:
        for row in catalog.scan(con, directory):
            flag = "verified" if row["verified"] else "NOT verified (excluded)"
            print(f"[scan] {row['file']}: {row['segments']} moments, {row['license']} {flag}")
    rcfg = channels.load(channel).get("render", {})
    made = []
    for i in range(count):
        try:
            c = selector.select(con, channel, category=category, seed=seed + i,
                                min_total=rcfg.get("min_duration", 20),
                                max_total=rcfg.get("max_duration", 45))
        except selector.SelectionError as e:
            print(f"[select] stopping after {len(made)} concept(s): {e}")
            break
        con.commit()
        print(f"[select] concept {c['id']}: {c['title']} ({c['category']})")
        if draft:
            res = render_concept(con, c["id"], draft=True)
            print(f"[draft]  {res['manifest']['preview']}  QA "
                  f"{'PASS' if res['qa']['pass'] else 'FAIL'}")
        made.append(c)
    gallery.build(con)
    return made


def batch_approve(con, ids: list[int], reviewer: str) -> list[dict]:
    out = []
    for cid in ids:
        selector.approve(con, cid, reviewer)
        con.commit()
        res = render_concept(con, cid)
        con.commit()
        status = "PASS" if res["qa"]["pass"] else "FAIL"
        dry = None
        if res["qa"]["pass"]:
            from . import uploader
            concept = selector.get(con, cid)
            r = con.execute("SELECT * FROM renders WHERE concept_id=? ORDER BY id DESC LIMIT 1",
                            (cid,)).fetchone()
            dry = uploader.upload(con, concept["channel"],
                                  {"path": r["path"], "sha256": r["sha256"]}, concept,
                                  res["meta"], dry_run=True)
        print(f"[approve] concept {cid}: render {res['manifest']['mp4']}  QA {status}"
              + (f"  dry-run privacy={dry['body']['status']['privacyStatus']}, "
                 f"blocking={len(dry['blocking'])}" if dry else "  (no dry-run: QA failed)"))
        out.append({"id": cid, "qa": status, "dry_run": dry})
    gallery.build(con)
    return out
