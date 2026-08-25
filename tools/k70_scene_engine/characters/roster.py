"""K70's recurring explainer character roster.

Each character is mapped to a real, license-eligible base mesh (currently
one of gobkit's rigged "minion" models -- the only rigged humanoid-ish
characters actually vendored today) plus a `seed` used everywhere that
character needs a deterministic visual variation (material color, a small
prop). Same character, same seed, every scene => visual continuity across
a whole video, which is the actual requirement (section 5/11) -- not
photoreal likeness, just "the same John every time John appears."

`accent_color` is an RGB triple applied as a material tint in
blender/scene_builder.py so six characters built from a handful of shared
base meshes still read as visually distinct without needing six separate
sculpted models.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Character:
    character_id: str
    display_name: str
    role: str                       # "investor" | "worker" | "banker" | ...
    base_asset_id: str              # gobkit asset_id this character is built from
    seed: int
    accent_color: tuple[float, float, float]
    props: list[str] = field(default_factory=list)   # catalog tag hints for held/worn props


ROSTER: dict[str, Character] = {
    "john": Character(
        character_id="john", display_name="John", role="worker",
        base_asset_id="gobkit:minion/minion-a01", seed=1001,
        accent_color=(0.20, 0.45, 0.85), props=["computer"],
    ),
    "sarah": Character(
        character_id="sarah", display_name="Sarah", role="worker",
        base_asset_id="gobkit:minion/minion-a02", seed=1002,
        accent_color=(0.85, 0.30, 0.55), props=["phone"],
    ),
    "investor": Character(
        character_id="investor", display_name="The Investor", role="investor",
        base_asset_id="gobkit:minion/minion-b01", seed=1003,
        accent_color=(0.15, 0.60, 0.35), props=["computer", "money_prop"],
    ),
    "worker": Character(
        character_id="worker", display_name="The Worker", role="worker",
        base_asset_id="gobkit:minion/minion-b02", seed=1004,
        accent_color=(0.90, 0.60, 0.10), props=[],
    ),
    "business_owner": Character(
        character_id="business_owner", display_name="The Business Owner",
        role="business_owner", base_asset_id="gobkit:minion/minion-c01", seed=1005,
        accent_color=(0.35, 0.20, 0.55), props=["office"],
    ),
    "banker": Character(
        character_id="banker", display_name="The Banker", role="banker",
        base_asset_id="gobkit:minion/minion-c02", seed=1006,
        accent_color=(0.10, 0.10, 0.15), props=["bank", "vault"],
    ),
}


def get(character_id: str) -> Character:
    try:
        return ROSTER[character_id]
    except KeyError:
        raise KeyError(f"unknown K70 character '{character_id}'; known: {sorted(ROSTER)}")
