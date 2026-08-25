#!/usr/bin/env python3
"""Rebuilds the K70 asset catalog (catalog.sqlite3) and the license manifest
(license/manifest.json) from every source scanner.

    .venv-win/Scripts/python.exe -m tools.k70_scene_engine.catalog.build_catalog

Only scans local vendor/ content and the local quaternius seed file -- no
network calls, safe to run repeatedly.
"""
from __future__ import annotations

from . import index
from .sources import gobkit, cc0tree, cc0_asset_index, polyhaven
from ..license import manifest as license_manifest


def main() -> int:
    all_records = []
    all_licenses = []
    for scanner in (gobkit, cc0tree, cc0_asset_index, polyhaven):
        fn = scanner.scan if hasattr(scanner, "scan") else scanner.seed_pointers
        records, licenses = fn()
        print(f"[{scanner.__name__.split('.')[-1]}] {len(records)} assets")
        all_records.extend(records)
        all_licenses.extend(licenses)

    n = index.rebuild(all_records)
    print(f"catalog: {n} rows written to {index.DB_PATH}")

    m = license_manifest.build(all_licenses)
    license_manifest.save(m)
    print(f"license manifest: {m['eligible_count']} eligible, "
          f"{m['excluded_count']} excluded, {m['total_entries']} total "
          f"-> {license_manifest.MANIFEST_PATH}")

    print(index.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
