from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MOTION_ROOT = ROOT / "data" / "assets" / "motions"
MANIFEST = MOTION_ROOT / "motion_manifest.json"


@dataclass(frozen=True)
class Motion:
    action: str
    category: str
    source: str
    source_action: str
    license: str
    fps: int = 30
    loop: bool = False
    modes: tuple[str, ...] = ("voxel", "humanoid", "clay", "isometric")


def load_catalog() -> dict[str, Motion]:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["motions"]
    return {r["action"]: Motion(**r) for r in rows}


def get(action: str) -> Motion:
    try:
        return load_catalog()[action]
    except KeyError as exc:
        raise KeyError(f"unknown K70 motion {action!r}") from exc
