from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import (DEFAULT_ROOT, discover_openverse, discover_wikimedia, download_pending,
                       ensure_layout, preflight_metadata, score_and_tag, select_top, stats,
                       validate_and_dedup, write_pilot_report)
from .stock_adapter import (discover_stock, download_score_cinematography,
                            download_stock_survivors, prepare_cinematography_pool,
                            score_cinematography_thumbnails, select_cinematography_top100)


def main() -> None:
    p = argparse.ArgumentParser(description="K70 provenance-first reference dataset")
    p.add_argument("stage", choices=("init", "discover", "discover-openverse", "discover-wikimedia",
                                     "discover-stock", "preflight", "download", "download-stock",
                                     "validate", "score", "top100", "stats", "report",
                                     "cine-prepare", "cine-thumbnails", "cine-originals", "cine-top100"))
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--pages-per-query", type=int, default=2)
    p.add_argument("--page-size", type=int, default=20)
    p.add_argument("--contact-email", help="Genuine contact required by Wikimedia robot policy")
    args = p.parse_args(); ensure_layout(args.root)
    if args.stage == "init": result = {"root": str(args.root), "status": "initialized"}
    elif args.stage == "discover": result = {"openverse": discover_openverse(args.root), "wikimedia": discover_wikimedia(args.root, contact_email=args.contact_email)}
    elif args.stage == "discover-openverse": result = discover_openverse(
        args.root, pages_per_query=args.pages_per_query, page_size=args.page_size)
    elif args.stage == "discover-wikimedia": result = discover_wikimedia(args.root, contact_email=args.contact_email)
    elif args.stage == "discover-stock": result = __import__("asyncio").run(discover_stock(args.root))
    elif args.stage == "preflight": result = preflight_metadata(args.root)
    elif args.stage == "download": result = download_pending(
        args.root, limit=args.limit, contact_email=args.contact_email)
    elif args.stage == "download-stock": result = __import__("asyncio").run(download_stock_survivors(args.root, args.limit))
    elif args.stage == "cine-prepare": result = prepare_cinematography_pool(args.root, args.limit)
    elif args.stage == "cine-thumbnails": result = __import__("asyncio").run(score_cinematography_thumbnails(args.root, args.limit))
    elif args.stage == "cine-originals": result = __import__("asyncio").run(download_score_cinematography(args.root, args.limit))
    elif args.stage == "cine-top100": result = select_cinematography_top100(args.root)
    elif args.stage == "validate": result = validate_and_dedup(args.root, limit=args.limit)
    elif args.stage == "score": result = score_and_tag(args.root, limit=args.limit)
    elif args.stage == "top100": result = select_top(args.root, target=100)
    elif args.stage == "stats": result = stats(args.root)
    else: result = write_pilot_report(args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
