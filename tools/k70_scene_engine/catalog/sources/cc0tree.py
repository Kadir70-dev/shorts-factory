"""Scans the vendored CC0Tree .fbx props into AssetRecords + per-asset
LicenseEntry records. See gobkit.py for the same pattern; CC0Tree is a
single-author, single-LICENSE repo (CC0-1.0, verified), so per-asset
entries inherit rather than re-derive.
"""
from __future__ import annotations

from pathlib import Path

from ..index import AssetRecord
from ...license.schema import LicenseEntry, Clarity, CommercialUse

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "CC0Tree" / "Assets"

# Hand-mapped once (15 files, small enough that guessed auto-tagging from the
# filename alone would be less reliable than a short explicit table).
_TAGS = {
    "SM_AbstractZeusSculpture": ["prop", "decor", "office"],
    "SM_Airplane": ["prop", "vehicle"],
    "SM_BaseballBat": ["prop", "sport"],
    "SM_Bowling_Ball": ["prop", "sport"],
    "SM_Bowling_Pin": ["prop", "sport"],
    "SM_ComputerTower": ["prop", "computer", "office"],
    "SM_CrowBar": ["prop", "tool"],
    "SM_FireAxe": ["prop", "tool"],
    "SM_HammerClaw": ["prop", "tool"],
    "SM_Screwdriver": ["prop", "tool"],
    "SM_Sword_1_Shortsword": ["prop", "weapon"],
    "SM_Sword_2_Katana": ["prop", "weapon"],
    "SM_Tree_1": ["prop", "nature", "tree"],
    "SM_WateringCan": ["prop", "garden"],
    "SM_Wrench": ["prop", "tool"],
}


def scan() -> tuple[list[AssetRecord], list[LicenseEntry]]:
    records: list[AssetRecord] = []
    licenses: list[LicenseEntry] = []
    if not VENDOR_DIR.exists():
        return records, licenses

    for fbx in sorted(VENDOR_DIR.glob("*.fbx")):
        name = fbx.stem
        asset_id = f"cc0tree:{name}"
        tags = _TAGS.get(name, ["prop"])
        records.append(AssetRecord(
            asset_id=asset_id, source="SkywolfGameStudios/CC0Tree", category="prop",
            format="fbx", local_path=str(fbx.relative_to(VENDOR_DIR.parents[2])),
            description=f"CC0Tree prop: {name}", tags=tags, rigged=False,
            poly_style="low_poly", file_bytes=fbx.stat().st_size,
        ))
        licenses.append(LicenseEntry(
            asset_id=asset_id, source="SkywolfGameStudios/CC0Tree",
            source_url="https://github.com/SkywolfGameStudios/CC0Tree",
            license_spdx="CC0-1.0",
            license_note="Inherits repo-level verified CC0-1.0 (see source:cc0tree).",
            commercial_use=CommercialUse.YES, attribution_required=False,
            clarity=Clarity.VERIFIED, local_path=str(fbx.relative_to(VENDOR_DIR.parents[2])),
            category="prop", tags=tags, integration_mode="vendored", checked_at="2026-08-22",
        ))
    return records, licenses
