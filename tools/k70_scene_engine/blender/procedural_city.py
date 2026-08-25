"""PROCEDURAL_CITY mode bridges (brief sections 1.4/1.5, 7).

Both vendored tools are invoked as external subprocesses per their
GPL-3.0/MPL-2.0 licensing (license/sources.py), never imported directly.

HONESTY NOTE (do not remove) -- verified against the actual vendored
source on 2026-08-22, not guessed from README claims:

- `bene-proggen-maps`: real, callable operator confirmed at
  `procgen_maps/ui/operators.py:235` -- `bpy.ops.procgen_maps.generate_city`.
  `generate_map()` below invokes that real operator. Still UNVERIFIED
  end-to-end (no successful render produced yet -- Blender itself was
  still downloading when this module was authored; see FINAL_REPORT.md),
  but the entry point itself is real, not assumed.

- `josauder/procedural_city_generation`: NOT WIRED. Its
  `visualization/blenderize.py` is a plain function library (`try: import
  bpy ... except: pass` at module level, no `--`-style CLI, no `if
  __name__ == "__main__"`) meant to be called from a notebook/driver
  script that the repo doesn't ship. An earlier draft of this file
  invoked a `building_generation/visualize.py` path that does not exist
  in the vendored repo -- that was a wrong guess and has been removed.
  Making this generator callable from `--background --python` needs a
  short driver script (import the city-graph builder, call
  `blenderize`'s functions in the right order) that has NOT been written.
  `generate_city()` below raises `NotImplementedError` rather than
  silently pretending to work.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .bpy_bridge import find_blender

CITY_GEN_MAIN = (Path(__file__).resolve().parents[1] / "vendor" /
                 "procedural_city_generation" / "procedural_city_generation")
MAPS_GEN_PKG = (Path(__file__).resolve().parents[1] / "vendor" /
                "bene-proggen-maps" / "procgen_maps")


def generate_city(*, seed: int, out_blend: Path, timeout: int = 600):
    """josauder/procedural_city_generation has no CLI entry point in the
    vendored repo (see module docstring) -- NOT wired yet."""
    raise NotImplementedError(
        "procedural_city_generation.visualization.blenderize is a function "
        "library, not a runnable script. A driver script that calls its "
        "roadmap/polygon/building generators in sequence and then "
        "blenderize's mesh-building functions needs to be written before "
        "this can invoke it headlessly. Not done in this session -- see "
        "FINAL_REPORT.md open items.")


def generate_map(*, seed: int, out_dir: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    """Invoke bene-proggen-maps' real `procgen_maps.generate_city` operator
    (verified at procgen_maps/ui/operators.py:235) as a Blender addon,
    headless. GPL-3.0: invoked as a separate Blender process, never
    vendored into this module's own import graph. End-to-end render not
    yet exercised -- see FINAL_REPORT.md."""
    blender_exe = find_blender()
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = MAPS_GEN_PKG / "__init__.py"
    if not entry.exists():
        raise FileNotFoundError(f"expected addon entry point at {entry}")
    addons_parent = str(MAPS_GEN_PKG.parent)
    # generate_city takes no operator args (verified operators.py:233-238) --
    # it reads context.scene.procgen_maps (a PropertyGroup, ui/__init__.py:31
    # confirms .seed exists there), so the seed must be set on the scene
    # settings before calling the parameterless operator.
    return subprocess.run(
        [str(blender_exe), "--background", "--python-expr",
         f"import sys; sys.path.insert(0, r'{addons_parent}')\n"
         "import bpy, procgen_maps\n"
         "procgen_maps.register()\n"
         f"bpy.context.scene.procgen_maps.seed = {seed}\n"
         "bpy.ops.procgen_maps.generate_city()\n"
         f"bpy.ops.wm.save_as_mainfile(filepath=r'{out_dir / 'city.blend'}')"],
        capture_output=True, text=True, timeout=timeout,
    )
