# P1 — CPU cartoon asset preparation (character images → layered rig)

This is an opt-in, deterministic asset preparation stage. No GPU, hosted video generation,
segmentation model or changed finance-documentary pipeline is required.

## What goes in

**Supported:** individually generated body-part PNGs, **or** one **well-spaced sprite
sheet** containing individual parts in fixed, separate grid cells. Transparent PNG
is preferred. A uniform solid white background also works via border-connected
color-key removal. The system preserves interior white eyes if enclosed by outlines.

**Not supported:** an ordinary full-body photo/cartoon flattened into one image.
The hidden arm/leg pixels, occluded shoulder geometry and separate pivot-ready sprites
are not recoverable reliably by this CPU-only process. Use an original segmented
character asset sheet instead (or manually draw/correct pieces).

### Layout for 4-column × 3-row sheet

| Row | Cell 0 | Cell 1 | Cell 2 | Cell 3 |
|---|---|---|---|---|
| 0 | head | body | arm_left | arm_right |
| 1 | leg_left | leg_right | eyes_open | eyes_closed |
| 2 | mouth_open | mouth_closed | blank | blank |

All parts **must have gap around edges and not overlap**. Avoid labels inside cells;
labels become cutout pixels. The body-part images must be your own or licensed for use.

Generate prompt suggestion (for your image generator):

> Create an original 2D cartoon character asset sheet for cutout animation.
> Exactly 4 columns and 3 rows, uniform flat WHITE background; no text, no
> shadows, no labels, no grid lines. Each cell contains ONLY the single isolated
> body part in this exact order: first row head, torso, left arm, right arm;
> second row left leg, right leg, eyes-open sprite, eyes-closed sprite;
> third row mouth-open sprite, mouth-closed sprite, two blank cells.
> One consistent original character, front-facing 2D cel-shaded art.
> No overlaps; generous white margins; keep limb parts completely visible.

Image generation may misplace items, so visually verify the grid and adjust cells
before running the script. For best control, generate the 10 parts separately.

## Run

Install dependencies in the **existing** Shorts Factory environment (Pillow + numpy)
and make sure ffmpeg is installed. Repo root:

~~~bash
# Smoke: creates a procedural demo sheet (not AI art), processes it, renders an MP4
python scripts/cartoon_p1_smoke.py --out-dir data/cartoon_p1_smoke
ffprobe -v error -show_entries format=duration -of json data/cartoon_p1_smoke/prepared/demo.mp4

# Real 4x3 sheet: put sheet_spec.json next to your character_parts_sheet.png
python scripts/cartoon_prepare_assets.py --spec /path/to/sheet_spec.json --out data/characters/hero_v1
python apps/api/app/pipeline/cartoon_motion_cpu.py \
  --manifest data/characters/hero_v1/cartoon.json \
  --out data/characters/hero_v1/test.mp4

# Regression tests
PYTHONPATH=apps/api pytest -q tests/test_cartoon_asset_prep.py tests/test_cartoon_motion_cpu.py
~~~

Example sheet_spec.json beside sheet:

~~~json
{
  "source": "sheet", "sheet": "character_parts_sheet.png",
  "grid": [3, 4], "width": 360, "height": 640,
  "fps": 12, "duration_sec": 5,
  "background_tolerance": 26, "cell_inset_px": 5,
  "motions": ["idle", "blink", "wave", "talk", "nod"]
}
~~~

For individual files: put body.png, head.png, arm_left.png, arm_right.png,
leg_left.png, leg_right.png in art/, optionally eyes_open.png,
eyes_closed.png, mouth_open.png, mouth_closed.png. Then:

~~~json
{ "source": "parts", "input_dir": "art", "fps": 12,
  "width": 360, "height": 640, "duration_sec": 5 }
~~~

parts can be a mapping of custom filenames, e.g. {"head":"head_v2.webp"}.
Custom sheet cell indexes can be provided with cells:{"head":[row,col], ...}.

## What comes out

- assets/*.png: transparent, tightly cropped, auto-sized parts
- cartoon.json: **editable heuristic** positions/pivots in existing CartoonMotion format
- preview.png: assembled rig check before spending time rendering video
- asset_qa.json: background removal method, bounds and part sizes

**Human visual approval is necessary.** Automatic positioning uses front-view
proportions, not learned skeletal pose detection. Change anchors/pivots, regenerate
preview, and inspect ears/eyes/mouth joints, skin edges, empty space and limb orientation.
The P1 output can be fed to the existing apply_cartoon_to_graph() bridge.

On the HP i5-4300U / 11 GiB RAM, begin with 360×640, 12 FPS and low-motion scenes.
Actual performance on the user's laptop is still unmeasured.

## Isolation

No schema migrations or edits to frozen K70 14-layer documentary pipeline.
main Shorts Factory rendering remains unchanged unless you explicitly call
this asset preparation script and animation adapter for a cartoon job.
