from __future__ import annotations

from dataclasses import dataclass

from .catalog import Motion, get


@dataclass(frozen=True)
class ScheduledMotion:
    motion: Motion
    character: str
    mode: str
    start_frame: int
    end_frame: int


def get_motion(action: str, character: str = "john", mode: str = "voxel") -> Motion:
    motion = get(action)
    if mode not in {"voxel", "humanoid", "clay", "isometric"}:
        raise ValueError(f"unsupported character-animation mode {mode!r}")
    if mode not in motion.modes:
        raise LookupError(f"motion {action!r} is not visually verified for mode {mode!r}")
    return motion


def apply_motion(character, motion: Motion, start_frame: int, end_frame: int, *, mode="humanoid"):
    """Return a deterministic schedule; Blender-side adapters perform application."""
    if end_frame <= start_frame: raise ValueError("end_frame must exceed start_frame")
    name = character if isinstance(character, str) else getattr(character, "name", str(character))
    return ScheduledMotion(motion, name, mode, start_frame, end_frame)


def sequence_actions(actions: list[str], *, character="john", mode="voxel",
                     start_frame=1, frames_per_action=24) -> list[ScheduledMotion]:
    out = []
    for index, action in enumerate(actions):
        start = start_frame + index * frames_per_action
        out.append(apply_motion(character, get_motion(action, character, mode), start,
                                start + frames_per_action - 1, mode=mode))
    return out
