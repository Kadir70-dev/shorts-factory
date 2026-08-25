"""Builds and persists the machine-readable license manifest
(`manifest.json`) that `catalog/index.py` consults before letting any
asset into automatic K70 production.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import LicenseEntry
from .sources import SOURCE_ENTRIES
from .validator import filter_eligible

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"


def build(asset_entries: list[LicenseEntry] | None = None) -> dict:
    """Combine repo-level SOURCE_ENTRIES with per-asset entries (from the
    catalog indexer) into one manifest, running every entry through the
    validator so nothing ineligible silently reaches production."""
    all_entries = list(SOURCE_ENTRIES) + list(asset_entries or [])
    eligible, excluded = filter_eligible(all_entries)
    manifest = {
        "generated_by": "tools/k70_scene_engine/license/manifest.py",
        "total_entries": len(all_entries),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "eligible": [e.as_dict() for e in eligible],
        "excluded": [{"entry": e.as_dict(), "reason": reason} for e, reason in excluded],
    }
    return manifest


def save(manifest: dict, path: Path = MANIFEST_PATH) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_eligible(asset_id: str, path: Path = MANIFEST_PATH) -> bool:
    m = load(path)
    return any(e["asset_id"] == asset_id for e in m["eligible"])


if __name__ == "__main__":
    m = build()
    save(m)
    print(f"license manifest: {m['eligible_count']} eligible, "
          f"{m['excluded_count']} excluded, {m['total_entries']} total")
