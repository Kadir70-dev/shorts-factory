"""Real downloader for a curated Poly Haven CC0 asset set.

Unlike quaternius_seed.json (metadata only, see cc0_asset_index.py),
Poly Haven has a genuine, documented, no-auth REST API
(https://api.polyhaven.com) that resolves straight to downloadable glTF +
texture files with MD5 checksums. `fetch_curated_set()` actually pulls
bytes to disk and verifies them -- this is the difference between a
"catalog pointer" and a real local asset (see FINAL_REPORT.md's audit
of that distinction).

Curated by hand against a live query of the real Poly Haven model list
(521 models, queried 2026-08-22) for finance-storytelling relevance:
office/desk/furniture props plus the one building-adjacent piece Poly
Haven actually has (an apartment facade -- Poly Haven does not carry
full house/bank building exteriors; verified by keyword search across
every one of the 521 real model records, not assumed).
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from ..index import AssetRecord
from ...license.schema import LicenseEntry, Clarity, CommercialUse

API = "https://api.polyhaven.com"
VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "polyhaven"

# slug -> (category, tags)
CURATED: dict[str, tuple[str, list[str]]] = {
    "metal_office_desk": ("office", ["desk", "office", "furniture"]),
    "classic_laptop": ("office", ["computer", "laptop", "office"]),
    "CashRegister_01": ("money_prop", ["money_prop", "store", "bank"]),
    "wall_clock": ("office", ["office", "clock"]),
    "Shelf_01": ("office", ["office", "store", "furniture"]),
    "drawer_cabinet": ("office", ["office", "furniture", "storage"]),
    "Sofa_01": ("office", ["office", "furniture", "waiting_area"]),
    "SchoolChair_01": ("office", ["office", "furniture", "chair"]),
    "desk_lamp_arm_01": ("office", ["office", "furniture", "lamp"]),
    "modular_urban_apartments_facade": ("building", ["building", "city", "facade"]),
}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "k70-scene-engine/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _download(url: str, dest: Path, expected_md5: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "k70-scene-engine/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if expected_md5:
        got = hashlib.md5(data).hexdigest()
        if got != expected_md5:
            raise ValueError(f"MD5 mismatch for {url}: expected {expected_md5}, got {got}")
    dest.write_bytes(data)


def fetch_curated_set(resolution: str = "1k", force: bool = False) -> list[Path]:
    """Actually download the curated set. Verified MD5 per file. Returns
    the list of local .gltf entry-point paths (one per asset)."""
    fetched: list[Path] = []
    for slug, (category, tags) in CURATED.items():
        asset_dir = VENDOR_DIR / slug
        info = _get_json(f"{API}/files/{slug}")
        gltf_entry = info["gltf"][resolution]["gltf"]
        gltf_path = asset_dir / f"{slug}.gltf"
        if not gltf_path.exists() or force:
            _download(gltf_entry["url"], gltf_path, gltf_entry.get("md5"))
        for rel_name, file_info in gltf_entry.get("include", {}).items():
            local = asset_dir / rel_name
            if not local.exists() or force:
                _download(file_info["url"], local, file_info.get("md5"))
        fetched.append(gltf_path)
        print(f"  fetched {slug} -> {gltf_path}")
    return fetched


def scan() -> tuple[list[AssetRecord], list[LicenseEntry]]:
    """Catalog scanner -- only registers assets actually present on disk
    (mirrors gobkit.py/cc0tree.py's pattern). Run fetch_curated_set()
    first; scan() alone never downloads anything."""
    records: list[AssetRecord] = []
    licenses: list[LicenseEntry] = []
    if not VENDOR_DIR.exists():
        return records, licenses

    for slug, (category, tags) in CURATED.items():
        gltf_path = VENDOR_DIR / slug / f"{slug}.gltf"
        if not gltf_path.exists():
            continue
        asset_id = f"polyhaven:{slug}"
        size = sum(f.stat().st_size for f in (VENDOR_DIR / slug).rglob("*") if f.is_file())
        records.append(AssetRecord(
            asset_id=asset_id, source="Poly Haven", category=category,
            format="gltf", local_path=str(gltf_path.relative_to(VENDOR_DIR.parents[1])),
            description=f"Poly Haven model: {slug}", tags=tags, rigged=False,
            poly_style="photoreal", file_bytes=size,
        ))
        licenses.append(LicenseEntry(
            asset_id=asset_id, source="Poly Haven", source_url=f"https://polyhaven.com/a/{slug}",
            creator="Poly Haven contributors", license_spdx="CC0-1.0",
            license_note=("Poly Haven publishes 100% CC0 assets (site-wide policy, "
                          "https://polyhaven.com/license). Downloaded and MD5-verified "
                          "directly from the documented api.polyhaven.com REST API, "
                          "not assumed from a catalog pointer."),
            commercial_use=CommercialUse.YES, attribution_required=False,
            clarity=Clarity.VERIFIED, local_path=str(gltf_path.relative_to(VENDOR_DIR.parents[1])),
            category=category, tags=tags, integration_mode="vendored", checked_at="2026-08-22",
        ))
    return records, licenses


if __name__ == "__main__":
    fetch_curated_set()
