"""Scans the vendored gobkit-free-assets .glb files into AssetRecords +
per-asset LicenseEntry records.

Every file inherits the source repo's already-VERIFIED CC0-1.0 finding
(license/sources.py:source:gobkit-free-assets) — there is no per-pack
license variance within this repo (single author, single LICENSE file), so
per-asset entries just reference that verification rather than re-deriving
it.
"""
from __future__ import annotations

from pathlib import Path

from ..index import AssetRecord
from ...license.schema import LicenseEntry, Clarity, CommercialUse

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "gobkit-free-assets"

_CATEGORY_TAGS = {
    "animal": ["nature", "animal"],
    "minion": ["character", "rigged"],
    "nature": ["nature", "prop"],
}


def scan() -> tuple[list[AssetRecord], list[LicenseEntry]]:
    records: list[AssetRecord] = []
    licenses: list[LicenseEntry] = []
    if not VENDOR_DIR.exists():
        return records, licenses

    for glb in sorted(VENDOR_DIR.rglob("*.glb")):
        rel = glb.relative_to(VENDOR_DIR)
        folder = rel.parts[0]
        name = glb.stem
        asset_id = f"gobkit:{folder}/{name}"
        tags = list(_CATEGORY_TAGS.get(folder, [folder]))
        tags.append(name.lower())
        category = "character" if folder == "minion" else ("nature" if folder in ("animal", "nature") else folder)
        records.append(AssetRecord(
            asset_id=asset_id, source="Ariescar/gobkit-free-assets", category=category,
            format="glb", local_path=str(glb.relative_to(VENDOR_DIR.parents[1])),
            description=f"Gobkit {folder} asset: {name}",
            tags=tags, rigged=(folder in ("animal", "minion")), poly_style="low_poly",
            file_bytes=glb.stat().st_size,
        ))
        licenses.append(LicenseEntry(
            asset_id=asset_id, source="Ariescar/gobkit-free-assets",
            source_url="https://github.com/Ariescar/gobkit-free-assets",
            creator="Gobkit / Alsomind Tech Co., Ltd.", license_spdx="CC0-1.0",
            license_note="Inherits repo-level verified CC0-1.0 (see source:gobkit-free-assets).",
            commercial_use=CommercialUse.YES, attribution_required=False,
            clarity=Clarity.VERIFIED, local_path=str(glb.relative_to(VENDOR_DIR.parents[1])),
            category=category, tags=tags, integration_mode="vendored", checked_at="2026-08-22",
        ))
    return records, licenses
