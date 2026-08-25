"""Bridges the vendored cc0-asset-index tool into the K70 catalog.

Two things happen here, deliberately kept separate:

1. `seed_pointers()` — reads the already-local `quaternius_seed.json` and
   registers each pack as an `index_pointer` catalog entry: the catalog
   KNOWS the pack exists and what it's good for (tags/description), but
   `local_path` is empty and `integration_mode="index_pointer"` — nothing
   has been downloaded. A pointer is not `eligible()` for production until
   someone runs `fetch_pack()` and it gets re-registered as `vendored`.

2. `fetch_pack()` — actually invokes the vendored indexer (subprocess, so a
   crash in third-party code can't take down K70's own process) to pull one
   named pack down. NOT run automatically by `build_catalog.py` — pulling
   Quaternius/Kenney/PolyHaven packs is a live-network, potentially
   multi-hundred-MB operation per pack that a storyboard run should opt
   into explicitly, not trigger as a side effect of indexing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..index import AssetRecord
from ...license.schema import LicenseEntry, Clarity, CommercialUse

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "cc0-asset-index"
SEED_FILE = VENDOR_DIR / "indexers" / "quaternius_seed.json"


def seed_pointers() -> tuple[list[AssetRecord], list[LicenseEntry]]:
    records: list[AssetRecord] = []
    licenses: list[LicenseEntry] = []
    if not SEED_FILE.exists():
        return records, licenses

    packs = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    for pack in packs:
        asset_id = f"quaternius:{pack['slug']}"
        category = ("character" if "character" in pack["tags"] or "rigged" in pack["tags"]
                    else ("building" if any(t in pack["tags"] for t in
                                             ("buildings", "modular", "village", "ruins"))
                          else "nature"))
        records.append(AssetRecord(
            asset_id=asset_id, source="quaternius.com (via cc0-asset-index)",
            category=category, format="pack_pointer", local_path="",
            description=pack["description"], tags=pack["tags"], rigged=("rigged" in pack["tags"]),
            poly_style="low_poly", file_bytes=0,
        ))
        licenses.append(LicenseEntry(
            asset_id=asset_id, source="quaternius.com", source_url=pack["url"],
            creator="Quaternius", license_spdx="CC0-1.0",
            license_note=("Quaternius packs are independently, publicly documented as CC0. "
                          "Not yet downloaded -- integration_mode=index_pointer until "
                          "fetch_pack() pulls it and a human/CI re-verifies the specific "
                          "pack page still states CC0 at fetch time."),
            commercial_use=CommercialUse.YES, attribution_required=False,
            clarity=Clarity.CLAIMED, local_path="", category=category, tags=pack["tags"],
            integration_mode="index_pointer", checked_at="2026-08-22",
        ))
    return records, licenses


def refresh_metadata(out_path: Path) -> subprocess.CompletedProcess:
    """Run the vendored quaternius indexer to (re)emit its JSONL metadata
    index. VERIFIED interface (read indexers/quaternius.py directly): it
    takes one positional output-path arg and writes pack metadata sourced
    from quaternius_seed.json -- it does NOT download any 3D model files.

    There is currently no vendored downloader for the actual pack contents;
    quaternius.com packs are a JS-driven site with no documented bulk API in
    this repo, so pulling real geometry requires a separate, not-yet-built
    per-pack scraper. `seed_pointers()` above is therefore the accurate
    picture of what's usable today: pointers with real tags/descriptions,
    zero downloaded bytes.
    """
    script = VENDOR_DIR / "indexers" / "quaternius.py"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(script), str(out_path)],
        capture_output=True, text=True, timeout=120,
    )
