"""
Source-workflow commands for `python -m app.ranking` (registered from __main__):

  import-reference DIR --channel C     reference inventory → metadata catalog
  reference-study --channel C          title-format patterns (study only)
  import-sources PATH... --kind K --license L --proof P --batch B [...]
  top5-detect SOURCE                   re-run Top-5 boundary detection
  top5-set SOURCE --bounds a,b,c,d,e,f manual boundaries → five manual clips
  clips                                rebuild the visual clip browser
  build-fixtures                       ranking-style test videos with truth files
  eval-fixtures                        segmentation accuracy against truth files
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import RANKING_DIR

FIXTURES = RANKING_DIR / "fixtures"
COMMANDS = {"import-reference", "reference-study", "import-sources", "top5-detect",
            "top5-set", "clips", "build-fixtures", "eval-fixtures"}


def add_parsers(sub) -> None:
    s = sub.add_parser("import-reference"); s.add_argument("dir", type=Path)
    s.add_argument("--channel", required=True)
    s = sub.add_parser("reference-study"); s.add_argument("--channel", required=True)
    s = sub.add_parser("import-sources"); s.add_argument("paths", type=Path, nargs="+")
    s.add_argument("--kind", choices=["clip", "compilation"], required=True)
    s.add_argument("--license", required=True); s.add_argument("--proof", required=True)
    s.add_argument("--batch", required=True); s.add_argument("--attribution", default="")
    s.add_argument("--underlying-proof", default=""); s.add_argument("--category", default="")
    s.add_argument("--labels", default="", help="five moment descriptions, '|' separated")
    s.add_argument("--copy", action="store_true", help="copy instead of hard-link")
    s = sub.add_parser("top5-detect"); s.add_argument("source", type=int)
    s.add_argument("--order", choices=["countdown", "countup"], default="countdown")
    s = sub.add_parser("top5-set"); s.add_argument("source", type=int)
    s.add_argument("--bounds", required=True, help="start,b1,b2,b3,b4,end in seconds")
    s.add_argument("--order", choices=["countdown", "countup"], default="countdown")
    sub.add_parser("clips")
    s = sub.add_parser("build-fixtures"); s.add_argument("--raw", type=Path, default=FIXTURES / "raw")
    s.add_argument("--out", type=Path, default=FIXTURES / "compilations")
    s = sub.add_parser("eval-fixtures"); s.add_argument("--dir", type=Path,
                                                        default=FIXTURES / "compilations")


def _p(obj) -> None:
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


def handle(con, args) -> int:
    from . import clip_browser, compilation, importer, reference
    if args.cmd == "import-reference":
        _p(reference.import_inventory(con, args.dir, args.channel))
        print("reference rows are metadata only: never selectable, rendered or uploaded")
    elif args.cmd == "reference-study":
        _p(reference.study(con, args.channel))
    elif args.cmd == "import-sources":
        labels = [x.strip() for x in args.labels.split("|")] if args.labels else None
        _p(importer.import_sources(con, args.paths, kind=args.kind, license=args.license,
                                   proof=args.proof, batch=args.batch,
                                   attribution=args.attribution,
                                   underlying_proof=args.underlying_proof,
                                   category=args.category, moment_labels=labels,
                                   copy=args.copy))
        print("imported UNVERIFIED — review in `clips`, then verify-source")
    elif args.cmd == "top5-detect":
        _p(compilation.analyse_top5(con, args.source, args.order))
    elif args.cmd == "top5-set":
        bounds = [float(x) for x in args.bounds.split(",")]
        print(compilation.set_bounds(con, args.source, bounds, args.order))
    elif args.cmd == "clips":
        print(clip_browser.build(con))
    elif args.cmd == "build-fixtures":
        from . import fixtures
        for r in fixtures.build(args.raw, args.out):
            print(r)
    elif args.cmd == "eval-fixtures":
        return eval_fixtures(args.dir)
    return 0


def eval_fixtures(directory: Path) -> int:
    from . import fixtures, probe, segment_top5
    rows, inner_err = [], []
    for truth_file in sorted(directory.glob("*.truth.json")):
        truth = json.loads(truth_file.read_text())
        video = truth_file.with_name(truth_file.name.replace(".truth.json", ".mp4"))
        info = probe.probe(video)
        det = segment_top5.detect(video, info, info["has_audio"])
        ev = fixtures.evaluate(det, truth)
        if truth["moments"] == 5 and det.get("bounds"):
            inner_err += [abs(a - b) for a, b in zip(det["bounds"][1:5], truth["bounds"][1:5])]
        rows.append({"video": video.name, "truth_moments": truth["moments"],
                     "style": truth["style"], "status": det.get("status"), **ev})
    for r in rows:
        print(json.dumps(r, default=float))
    if inner_err:
        within = sum(e <= 0.5 for e in inner_err)
        print(f"\ninterior boundaries within 0.5 s: {within}/{len(inner_err)}; "
              f"mean error {sum(inner_err) / len(inner_err):.3f} s; max {max(inner_err):.2f} s")
    return 0
