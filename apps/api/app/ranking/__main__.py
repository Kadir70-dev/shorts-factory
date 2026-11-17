"""
CLI:  cd apps/api && python -m app.ranking <command> ...

  samples   --out DIR                   generate rights-cleared synthetic test sources
  scan      DIR                         register + analyse every video in DIR
  sources | segments [--source N]       inspect the catalog
  segment   ID [--start --end --category --label --disable/--enable]
  add-segment SOURCE START END          manual moment
  stock                                 eligible moments per category
  select    --channel C [--category X] [--seed N]
  show      CONCEPT                     print concept JSON (edit + `edit` it back)
  edit      CONCEPT FILE.json           replace captions/title (resets approval)
  approve   CONCEPT --by NAME | reject CONCEPT
  render    CONCEPT                     render + QA + metadata (approved only)
  preview   CONCEPT                     watermarked DRAFT render for review (no approval)
  gallery   [--serve]                   rebuild the review page (and serve on 127.0.0.1)
  batch     [DIR] --count N             scan → select → draft previews → gallery, then stop
  batch-approve IDS... --by NAME        approve → render → QA → upload dry-run → gallery
  fetch-pexels --category X QUERY...    download Pexels-licensed clips (unverified)
  verify-source SOURCE --by NAME [--underlying-proof P] [--permission-proof P]
  (+ source workflow: see app/ranking/cli_sources.py — import-reference,
     reference-study, import-sources, top5-detect, top5-set, clips, eval-fixtures)
  channels                              isolation check for every channel
  slots     --channel C [--count N]     next DST-aware posting slots
  auth      --channel C                 one-off OAuth for that channel
  upload    CONCEPT --channel C [--privacy private] [--schedule --allow-public] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog, channels, cli_sources, gallery, qa, schedule, selector, workflow
from .db import RANKING_DIR, connect


def _p(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_render(con, args, draft: bool = False) -> int:
    res = workflow.render_concept(con, args.concept, draft=draft)
    gallery.build(con)
    m = res["manifest"]
    print(qa.format_report(res["qa"]))
    print(f"\n{'preview' if draft else 'mp4'}:   {m['preview'] if draft else m['mp4']}\n"
          f"sheet:     {m['preview_sheet']}\nmetadata:  {res['work']}/metadata.json\n"
          f"render:    {m['render_seconds']}s")
    return 0 if res["qa"]["pass"] else 2


def cmd_upload(con, args) -> int:
    from . import uploader
    concept = selector.get(con, args.concept)
    r = con.execute("SELECT * FROM renders WHERE concept_id=? ORDER BY id DESC LIMIT 1",
                    (concept["id"],)).fetchone()
    if r is None:
        sys.exit("render the concept first")
    if not json.loads(r["qa_json"]).get("pass"):
        sys.exit("latest render failed QA; fix and re-render before uploading")
    res = uploader.upload(con, args.channel, {"path": r["path"], "sha256": r["sha256"]},
                          concept, json.loads(r["meta_json"]), privacy=args.privacy,
                          schedule_slot=args.schedule, allow_public=args.allow_public,
                          dry_run=args.dry_run)
    _p(res)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.ranking")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("samples").add_argument("--out", type=Path,
                                           default=RANKING_DIR / "sources" / "samples")
    s = sub.add_parser("scan"); s.add_argument("dir", type=Path)
    s.add_argument("--want", type=int, default=5)
    sub.add_parser("sources")
    s = sub.add_parser("segments"); s.add_argument("--source", type=int)
    s = sub.add_parser("segment"); s.add_argument("id", type=int)
    for f in ("--start", "--end"):
        s.add_argument(f, type=float)
    s.add_argument("--category"); s.add_argument("--label")
    s.add_argument("--disable", action="store_true"); s.add_argument("--enable", action="store_true")
    s = sub.add_parser("add-segment"); s.add_argument("source", type=int)
    s.add_argument("start", type=float); s.add_argument("end", type=float)
    s.add_argument("--category", default=""); s.add_argument("--label", default="")
    sub.add_parser("stock")
    s = sub.add_parser("select"); s.add_argument("--channel", default="ranking_shorts")
    s.add_argument("--category"); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--min-sources", type=int, default=3)
    s.add_argument("--writer", choices=["template", "claude"], default="template")
    s = sub.add_parser("show"); s.add_argument("concept", type=int)
    s = sub.add_parser("edit"); s.add_argument("concept", type=int); s.add_argument("file", type=Path)
    s = sub.add_parser("approve"); s.add_argument("concept", type=int); s.add_argument("--by", required=True)
    s = sub.add_parser("reject"); s.add_argument("concept", type=int)
    s = sub.add_parser("render"); s.add_argument("concept", type=int)
    s = sub.add_parser("preview"); s.add_argument("concept", type=int)
    s = sub.add_parser("gallery"); s.add_argument("--serve", action="store_true")
    s.add_argument("--port", type=int, default=8765)
    s = sub.add_parser("batch"); s.add_argument("dir", type=Path, nargs="?")
    s.add_argument("--channel", default="ranking_shorts"); s.add_argument("--count", type=int, default=3)
    s.add_argument("--category"); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--no-draft", action="store_true")
    s = sub.add_parser("batch-approve"); s.add_argument("ids", type=int, nargs="+")
    s.add_argument("--by", required=True)
    s = sub.add_parser("fetch-pexels"); s.add_argument("queries", nargs="+")
    s.add_argument("--category", required=True)
    s.add_argument("--out", type=Path, default=RANKING_DIR / "sources" / "pexels")
    s.add_argument("--per-query", type=int, default=1)
    s = sub.add_parser("verify-source"); s.add_argument("source", type=int, nargs="+")
    s.add_argument("--by", required=True)
    s.add_argument("--underlying-proof", default="")
    s.add_argument("--permission-proof", default="")
    cli_sources.add_parsers(sub)
    sub.add_parser("channels")
    s = sub.add_parser("slots"); s.add_argument("--channel", default="ranking_shorts")
    s.add_argument("--count", type=int, default=6)
    s = sub.add_parser("auth"); s.add_argument("--channel", required=True)
    s = sub.add_parser("upload"); s.add_argument("concept", type=int)
    s.add_argument("--channel", required=True)
    s.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    s.add_argument("--schedule", action="store_true")
    s.add_argument("--allow-public", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "samples":
        from . import samples
        for p in samples.generate(args.out):
            print(p)
        return 0
    if args.cmd == "channels":
        for ch in channels.all_channels():
            cfg = channels.load(ch)
            probs = channels.upload_readiness(cfg)
            print(f"{ch:<16} out={cfg['output_dir']:<32} upload: "
                  f"{'READY' if not probs else 'blocked — ' + '; '.join(probs)}")
        errs = channels.isolation_errors()
        print("isolation:", "OK" if not errs else errs)
        return 1 if errs else 0
    if args.cmd == "slots":
        cfg = channels.load(args.channel)
        for s_ in schedule.next_slots(cfg, set(), args.count):
            print(f"{s_.strftime('%a %Y-%m-%d %I:%M %p %Z')}  →  {schedule.to_rfc3339(s_)}")
        return 0
    if args.cmd == "fetch-pexels":
        from . import stock
        for p in stock.fetch(args.queries, args.out, args.category, args.per_query):
            print(p)
        print(f"licenses recorded UNVERIFIED in {args.out / 'licenses.yaml'}; "
              "scan, review, then verify-source")
        return 0
    if args.cmd == "gallery" and args.serve:
        with connect() as con:
            gallery.build(con)
        gallery.serve(args.port)
        return 0
    if args.cmd == "auth":
        from . import uploader
        print(uploader.authorize(args.channel))
        return 0

    with connect() as con:
        if args.cmd == "scan":
            _p(catalog.scan(con, args.dir, args.want))
        elif args.cmd == "sources":
            for r in con.execute("SELECT id, path, duration, width, height, has_audio, "
                                 "license, license_verified, category FROM sources"):
                print(dict(r))
        elif args.cmd == "segments":
            q = "SELECT * FROM segments" + (" WHERE source_id=?" if args.source else "")
            for r in con.execute(q, (args.source,) if args.source else ()):
                print(dict(r))
        elif args.cmd == "segment":
            dis = True if args.disable else (False if args.enable else None)
            _p(catalog.edit_segment(con, args.id, start=args.start, end=args.end,
                                    category=args.category, label=args.label, disabled=dis))
        elif args.cmd == "add-segment":
            print(catalog.add_segment(con, args.source, args.start, args.end,
                                      args.category, args.label))
        elif args.cmd == "stock":
            _p(selector.category_stock(con))
        elif args.cmd == "select":
            cfg = channels.load(args.channel).get("render", {})
            c = selector.select(con, args.channel, category=args.category, seed=args.seed,
                                min_sources=args.min_sources,
                                min_total=cfg.get("min_duration", 20),
                                max_total=cfg.get("max_duration", 45),
                                writer=args.writer)
            _p(c)
            print(f"\nconcept {c['id']} is PENDING APPROVAL — review, then:\n"
                  f"  python -m app.ranking approve {c['id']} --by <your-name>")
        elif args.cmd == "show":
            _p(selector.get(con, args.concept))
        elif args.cmd == "edit":
            _p(selector.update_payload(con, args.concept, json.loads(args.file.read_text())))
        elif args.cmd == "approve":
            _p(selector.approve(con, args.concept, args.by)["status"])
        elif args.cmd == "reject":
            selector.reject(con, args.concept)
        elif args.cmd == "render":
            return cmd_render(con, args)
        elif args.cmd == "preview":
            return cmd_render(con, args, draft=True)
        elif args.cmd == "gallery":
            print(gallery.build(con))
        elif args.cmd == "batch":
            workflow.batch(con, args.dir, args.channel, args.count, args.category,
                           args.seed, draft=not args.no_draft)
            print(f"\nreview: {gallery.build(con)}")
        elif args.cmd == "batch-approve":
            workflow.batch_approve(con, args.ids, args.by)
            print(f"\ngallery: {gallery.build(con)}")
        elif args.cmd == "verify-source":
            for sid in args.source:
                _p(catalog.verify_source(con, sid, args.by,
                                         underlying_proof=args.underlying_proof,
                                         permission_proof=args.permission_proof))
        elif args.cmd in cli_sources.COMMANDS:
            return cli_sources.handle(con, args)
        elif args.cmd == "upload":
            return cmd_upload(con, args)
    return 0


if __name__ == "__main__":
    from .uploader import UploadBlocked
    try:
        sys.exit(main())
    except (PermissionError, ValueError, KeyError, selector.SelectionError,
            channels.ChannelConfigError, UploadBlocked) as e:
        sys.exit(f"[ranking] blocked: {e}")
