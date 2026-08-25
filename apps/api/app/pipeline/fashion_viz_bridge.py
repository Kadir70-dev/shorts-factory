"""
Bridge to the Fashion Visualization Engine.

The engine is FROZEN and channel-agnostic; the fashion modules are vertical
specific and live in the fashion project (PROJECT_ROOT/apps/api/app/pipeline/
fashion_viz). Rather than fork them into this repo, this bridge imports that ONE
copy at run time and exposes a single `resolve` pass.

Scenes opt in explicitly. A beat authored with

    visual.query = "fashionviz:pattern_cutting"

is rendered by that module; every other scene is untouched and falls down the
existing ladder. When the fashion project is not on disk — any non-fashion
channel — `available()` is False and the pass is a no-op, so this file cannot
affect an existing render.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

from ..config import settings
from ..schemas.scene import Scene, SceneGraph

PREFIX = "fashionviz:"


@lru_cache(maxsize=1)
def _module():
    """Import the fashion_viz package standalone, or return None.

    It is imported as a TOP-LEVEL package: its own `from ...config import
    settings` then fails harmlessly inside the try/except it already carries and
    falls back to resolving the data dir from the project root — which is the
    correct answer here anyway.
    """
    root = Path(settings().data_dir).parent / "apps" / "api" / "app" / "pipeline"
    if not (root / "fashion_viz" / "__init__.py").is_file():
        return None
    if str(root) not in sys.path:
        sys.path.append(str(root))          # appended: never shadows the engine
    try:
        import fashion_viz
        return fashion_viz
    except Exception as exc:                # a broken vertical must not break a render
        print(f"[fashion-viz] engine unavailable ({type(exc).__name__}: "
              f"{str(exc)[:120]}) → scenes fall through", flush=True)
        return None


def available() -> bool:
    return _module() is not None


def requested(scene: Scene) -> tuple[str, dict] | None:
    """The (module, params) a scene asked for, or None.

    Accepts `fashionviz:<module>` optionally followed by a JSON parameter blob:
    `fashionviz:weave {"structure": "denim"}`.
    """
    query = (scene.visual.query or "").strip()
    if not query.startswith(PREFIX):
        return None
    body = query[len(PREFIX):].strip()
    name, _, blob = body.partition(" ")
    params: dict = {}
    if blob.strip():
        try:
            params = json.loads(blob)
        except json.JSONDecodeError as exc:
            print(f"[fashion-viz] {scene.id}: bad params ({exc}) → defaults",
                  flush=True)
    return name.strip(), params


async def resolve(graph: SceneGraph, quality: str = "preview") -> dict[str, dict]:
    """Render every fashion-viz beat. Returns {scene_id: provenance dict}.

    Runs before the lookup engines: these beats are explicitly authored, so a
    stock clip must never satisfy one. A module failure leaves the scene
    UNCLAIMED and the caller's ladder takes over — the same contract the
    Three.js and motion-graphics passes use.
    """
    engine = _module()
    if engine is None:
        return {}
    handled: dict[str, dict] = {}
    for scene in graph.scenes:
        ask = requested(scene)
        if ask is None:
            continue
        name, params = ask
        if name not in engine.MODULES:
            print(f"[fashion-viz] {scene.id}: unknown module {name!r} → "
                  f"falls through", flush=True)
            continue
        try:
            prov = await engine.render(name, params,
                                       duration_sec=scene.duration_sec,
                                       quality=quality)
        except Exception as exc:            # never terminal; the ladder continues
            print(f"[fashion-viz] {scene.id}: {name} failed "
                  f"({type(exc).__name__}: {str(exc)[:120]})", flush=True)
            continue
        if not prov.render_path or not Path(prov.render_path).is_file():
            print(f"[fashion-viz] {scene.id}: {name} produced nothing "
                  f"({prov.status}) → falls through", flush=True)
            continue
        scene.visual.asset_path = prov.render_path
        scene.visual.type = "motion_gfx"     # a locally rendered motion graphic
        scene.visual.motion = "none"
        handled[scene.id] = prov.as_dict()
        print(f"[fashion-viz] {scene.id}: {name} {prov.status} "
              f"({prov.frames}f, {prov.render_ms:.0f}ms)", flush=True)
    return handled
