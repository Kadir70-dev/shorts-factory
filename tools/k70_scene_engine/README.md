# K70 Long-Form Visual Engine

Optional, additive extension of the K70 production pipeline. Nothing
under `apps/api/` imports from here; nothing here modifies anything under
`apps/api/`, `data/jobs/`, or `data/series/`.

See `FINAL_REPORT.md` for what's verified-working vs. wired-but-untested,
and `../../docs/K70_SCENE_ENGINE_LICENSE_AUDIT.md` for the full license
audit writeup behind `license/sources.py`.

## Module map

| Module | Purpose | Status |
|---|---|---|
| `license/` | Machine-readable license manifest + validator | Working, tested |
| `catalog/` | Local searchable SQLite asset catalog + semantic tag query | Working, tested |
| `characters/roster.py` | K70 recurring explainer characters (John, Sarah, ...) | Working |
| `templates/finance_scenes.py` | 12 finance-concept scene templates | Working |
| `environments/presets.py` | Reusable environment presets (section 7) | Working |
| `visual_mode/` | VisualMode enum + semantic beat classifier + sequence continuity | Working, tested |
| `cache/render_cache.py` | Content-addressed render cache | Working, tested |
| `checkpoint/pipeline_checkpoint.py` | Per-stage resume/checkpoint | Working, tested |
| `qa/validators.py` | Mechanical QA gate for rendered stills | Working |
| `blender/hardware.py` | Renderer/device/sample-count selection by detected GPU | Working, tested |
| `blender/bpy_bridge.py` | Headless Blender subprocess bridge, static-frame render | Working (needs Blender installed) |
| `blender/voxelizer.py` + `_voxelize_script.py` | VOXEL_STORY mode | Working (needs Blender installed) |
| `blender/procedural_city.py` | PROCEDURAL_CITY bridges | `generate_map()` wired to a verified real operator, unexercised; `generate_city()` (josauder) explicitly NOT wired -- raises `NotImplementedError` |
| `vendor/` | The six external repos/asset packs, license-audited | See license manifest |

## Quick start

```bash
# Rebuild the asset catalog + license manifest from local vendor/ content
.venv-win/Scripts/python.exe -m tools.k70_scene_engine.catalog.build_catalog

# Run the visual-mode selector's self-tests
.venv-win/Scripts/python.exe -m tools.k70_scene_engine.tests.test_selector

# Query the catalog
python -c "
from tools.k70_scene_engine.catalog import index
for a in index.query(['character']): print(a.asset_id, a.tags)
"
```

## Why this doesn't touch the existing pipeline

`visual_mode/modes.py`'s `VisualMode` enum maps six of its ten values
directly onto the existing `apps/api/app/pipeline/visual_budget.py`
channels (`REAL_STOCK`->`stock`, `MOTION_GRAPHIC`->`motion_gfx`, etc.) --
those beats need no new code at all, the existing renderer already
produces them. Only the four new modes (`3D_CHARACTER`,
`3D_ENVIRONMENT`, `PROCEDURAL_CITY`, `VOXEL_STORY`) route through this
package, and only when a caller opts in.
