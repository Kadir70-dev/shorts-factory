"""Repo-level license findings for the six systems named in the K70 Long-Form
Visual Engine brief.

Every field below was verified directly against the live GitHub API and the
actual LICENSE file content of each repo on 2026-08-22 (see
`docs/LICENSE_AUDIT.md` for the narrative writeup and raw evidence). Nothing
here is guessed from a repo's README claims alone unless `clarity` says so.
"""
from __future__ import annotations

from .schema import LicenseEntry, Clarity, CommercialUse

SOURCE_ENTRIES: list[LicenseEntry] = [
    LicenseEntry(
        asset_id="source:cc0-asset-index",
        source="Jpalmer95/cc0-asset-index",
        source_url="https://github.com/Jpalmer95/cc0-asset-index",
        creator="Jonathan Korstad",
        license_spdx="MIT",
        license_note=(
            "MIT covers the INDEXER TOOL itself (Python code that queries "
            "Kenney.nl, PolyHaven.com and Quaternius.com). The tool does not "
            "bundle assets — each indexed pack's own license (Kenney/PolyHaven/"
            "Quaternius are all independently, publicly CC0) must still be "
            "confirmed per-pack at download time by indexers/*.py before that "
            "pack's assets get a `verified` catalog entry."
        ),
        commercial_use=CommercialUse.YES,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/cc0-asset-index",
        category="tool:index",
        tags=["index", "catalog", "kenney", "polyhaven", "quaternius"],
        integration_mode="vendored",
        checked_at="2026-08-22",
    ),
    LicenseEntry(
        asset_id="source:gobkit-free-assets",
        source="Ariescar/gobkit-free-assets",
        source_url="https://github.com/Ariescar/gobkit-free-assets",
        creator="Gobkit / Alsomind Tech Co., Ltd.",
        license_spdx="CC0-1.0",
        license_note=(
            "GitHub's API reports NOASSERTION at the repo level (no root "
            "LICENSE file recognised by its detector), but the vendored "
            "LICENSE file's actual text is the full CC0 1.0 Universal legal "
            "code, explicitly naming these assets: 'These 3D assets are "
            "provided by Gobkit / Alsomind Tech Co., Ltd. No rights reserved.' "
            "Public domain, no attribution required, commercial use explicit."
        ),
        commercial_use=CommercialUse.YES,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/gobkit-free-assets",
        category="characters+nature",
        tags=["character", "animal", "minion", "nature", "rigged", "glb"],
        integration_mode="vendored",
        checked_at="2026-08-22",
    ),
    LicenseEntry(
        asset_id="source:cc0tree",
        source="SkywolfGameStudios/CC0Tree",
        source_url="https://github.com/SkywolfGameStudios/CC0Tree",
        license_spdx="CC0-1.0",
        license_note=(
            "Confirmed CC0-1.0 via GitHub API license detection. Despite the "
            "repo name/description ('Free Low Poly Assets for Indie Game "
            "Devs'), actual content is a small (39-file) misc-props pack: "
            "tools, a computer tower, sports items, one tree — NOT a "
            "buildings/environment library as the brief's summary implied. "
            "Useful for prop dressing, not for building exteriors."
        ),
        commercial_use=CommercialUse.YES,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/CC0Tree",
        category="props",
        tags=["prop", "misc", "fbx", "computer", "tools"],
        integration_mode="vendored",
        checked_at="2026-08-22",
    ),
    LicenseEntry(
        asset_id="source:procedural_city_generation",
        source="josauder/procedural_city_generation",
        source_url="https://github.com/josauder/procedural_city_generation",
        license_spdx="MPL-2.0",
        license_note=(
            "MPL-2.0 is weak/file-level copyleft: using it as an external "
            "invoked tool (or even importing its modules) only obligates "
            "sharing modifications to MPL-covered files themselves, not "
            "K70's own codebase. Real risk is NOT licensing but staleness: "
            "last pushed 2023-01-12, targets an old Blender bpy API. Not "
            "independently re-tested against the Blender version installed "
            "in this session as of the last catalog build — treat any city "
            "generated with it as `needs_review` output until a render is "
            "actually produced and inspected."
        ),
        commercial_use=CommercialUse.YES,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/procedural_city_generation",
        category="tool:procedural",
        tags=["city", "procedural", "streets", "buildings"],
        integration_mode="subprocess_only",
        checked_at="2026-08-22",
    ),
    LicenseEntry(
        asset_id="source:bene-proggen-maps",
        source="Beneking102/bene-proggen-maps",
        source_url="https://github.com/Beneking102/bene-proggen-maps",
        creator="Beneking102",
        license_spdx="GPL-3.0-or-later",
        license_note=(
            "GitHub API reports NOASSERTION (false negative — its detector "
            "didn't match the license file's nonstandard preamble). The "
            "vendored LICENSE file's full text is GPL-3.0-or-later, and its "
            "preamble explicitly states: 'This program (procgen_maps) is a "
            "Blender addon that uses Blender's Python API (bpy) and is "
            "therefore licensed under GPLv3... consistent with Blender's own "
            "GPL licensing terms.' GPL restricts REDISTRIBUTING/MODIFYING "
            "the tool's own source, not the renders it produces (same "
            "principle as art made in GPL-licensed Blender/GIMP not being "
            "GPL). K70 must invoke it as an external subprocess/addon, "
            "never vendor its code directly into K70's own MIT-adjacent "
            "modules, to keep the two works from combining under GPL terms."
        ),
        commercial_use=CommercialUse.CONDITIONAL,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/bene-proggen-maps",
        category="tool:procedural",
        tags=["city", "terrain", "dungeon", "procedural", "buildings"],
        integration_mode="subprocess_only",
        checked_at="2026-08-22",
    ),
    LicenseEntry(
        asset_id="source:minecraft-voxel-loader",
        source="carl-vbn/minecraft-voxel-loader",
        source_url="https://github.com/carl-vbn/minecraft-voxel-loader",
        creator="Carl von Bonin",
        license_spdx="MIT",
        license_note=(
            "IMPORTANT ARCHITECTURE NOTE: this repo is a Minecraft Fabric mod "
            "(Java) PLUS a standalone Blender/Python voxelizer script — NOT a "
            "general-purpose voxel renderer as the brief's one-line summary "
            "implied. Only `Scripts/blender_voxelizer.py` (pure bpy+bmesh+"
            "numpy, zero Minecraft/Fabric/Mojang dependency) is vendored and "
            "used. The Fabric mod, gradle build, and everything that talks to "
            "an actual Minecraft client were deliberately NOT vendored and "
            "will never be installed or invoked — using them would require a "
            "licensed Minecraft copy and would run inside Mojang's own "
            "renderer, which conflicts with the brief's explicit ban on "
            "Minecraft/Mojang assets and branding. VOXEL_STORY mode instead "
            "voxelizes any eligible CC0 mesh with this script and renders "
            "the resulting block geometry with Blender's own "
            "Cycles/EEVEE renderer — an originally-styled block world, never "
            "touching Minecraft."
        ),
        commercial_use=CommercialUse.YES,
        attribution_required=False,
        clarity=Clarity.VERIFIED,
        local_path="tools/k70_scene_engine/vendor/minecraft-voxel-loader-scripts",
        category="tool:voxelizer",
        tags=["voxel", "blockify", "bpy"],
        integration_mode="vendored",
        checked_at="2026-08-22",
    ),
]
