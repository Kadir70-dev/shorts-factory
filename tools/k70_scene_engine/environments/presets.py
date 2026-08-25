"""Reusable environment presets (brief section 7).

A lighter-weight alternative to full procedural city generation (which is
either unverified or unwired -- see blender/procedural_city.py): each
preset is a small, curated set of catalog tag queries plus a camera/
lighting recipe, assembled from whatever eligible assets the catalog
actually returns at render time. This is what `3D_ENVIRONMENT` beats in
templates/finance_scenes.py resolve through by default; PROCEDURAL_CITY
is an opt-in upgrade once its generators are verified end-to-end.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EnvironmentPreset:
    name: str
    tags: list[str]
    camera_distance_multiplier: float = 3.0
    lighting_energy: float = 3.0
    notes: str = ""


PRESETS: dict[str, EnvironmentPreset] = {
    "financial_district": EnvironmentPreset(
        "financial_district", ["building", "office", "bank", "city"],
        3.5, 3.0, "Establishing-shot framing; wide camera distance."),
    "downtown": EnvironmentPreset(
        "downtown", ["city", "street", "building"], 3.0, 3.0, ""),
    "bank_exterior": EnvironmentPreset(
        "bank_exterior", ["bank", "building", "government"], 2.5, 2.5, ""),
    "corporate_office": EnvironmentPreset(
        "corporate_office", ["office", "computer", "furniture"], 1.8, 2.0,
        "Interior-scale lighting, closer camera."),
    "residential_neighborhood": EnvironmentPreset(
        "residential_neighborhood", ["house", "nature", "street"], 2.8, 3.2, ""),
    "shopping_district": EnvironmentPreset(
        "shopping_district", ["store", "street", "city"], 2.6, 3.0, ""),
    "industrial_zone": EnvironmentPreset(
        "industrial_zone", ["factory", "industrial"], 3.2, 2.6,
        "Cooler/dimmer lighting than downtown."),
    "government_district": EnvironmentPreset(
        "government_district", ["government", "building"], 3.5, 3.2,
        "Avoid unnecessary trademarks/logos (brief section 7) -- catalog "
        "assets used here must be generic government-style buildings, "
        "never a real depicted agency's actual branded architecture."),
    "skyline": EnvironmentPreset(
        "skyline", ["city", "building"], 5.0, 3.5, "Wide establishing shot only."),
    "suburban": EnvironmentPreset(
        "suburban", ["house", "nature"], 2.8, 3.4, ""),
}


def get(name: str) -> EnvironmentPreset:
    try:
        return PRESETS[name]
    except KeyError:
        raise KeyError(f"unknown environment preset '{name}'; known: {sorted(PRESETS)}")
