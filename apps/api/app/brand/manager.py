"""Phase 7 central Brand Manager.

This extends the established YAML/theme path; it does not replace it. With the
feature gate off ``theme_for`` is exactly the legacy cached ``load_theme`` call
and never mutates the SceneGraph.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import settings
from ..schemas.scene import BrandIdentityProvenance, SceneGraph
from .theme import BrandTheme, load_theme

MANAGER_VERSION = "1.0.0"
REQUIRED_COLORS = {
    "bg", "bg_soft", "ink", "ink_dim", "primary", "secondary",
    "positive", "negative", "warn", "grid", "shadow",
}
REQUIRED_COMPONENTS = (
    "watermark", "lower_third", "intro", "outro", "captions", "chart",
    "safe", "title_card", "background", "timeline", "icons", "transitions", "cta",
)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class BrandValidation:
    valid: bool
    checks: dict[str, bool]


def validate(theme: BrandTheme) -> BrandValidation:
    components = all(bool(getattr(theme, name)) for name in REQUIRED_COMPONENTS)
    colors = REQUIRED_COLORS.issubset(theme.palette) and all(
        bool(_HEX.match(value)) for value in theme.palette.values())
    fonts = all(face.path and face.name for face in
                (theme.display, theme.body, theme.mono))
    safe = (0.03 <= float(theme.safe.get("side", 0)) <= 0.12
            and 0.05 <= float(theme.safe.get("top", 0)) <= 0.15
            and 0.12 <= float(theme.safe.get("bottom", 0)) <= 0.25)
    readable = (theme.size("caption") >= 54 and theme.size("source") >= 26
                and float(theme.captions.get("y", 1))
                < 1 - float(theme.safe.get("bottom", 0)))
    checks = {"complete_package": components, "palette_valid": colors,
              "fonts_resolved": fonts, "safe_margins": safe,
              "mobile_readable": readable}
    return BrandValidation(all(checks.values()), checks)


class BrandManager:
    """One entry point shared by renderers and generation engines."""

    def theme_for(self, graph: SceneGraph, module: str) -> BrandTheme:
        theme = load_theme(graph.brand_id or "k70")
        if not settings().brand_identity_enabled:
            return theme
        result = validate(theme)
        if not result.valid:
            failed = ", ".join(k for k, ok in result.checks.items() if not ok)
            raise ValueError(f"invalid brand package {theme.id}: {failed}")
        current = graph.brand_identity_provenance
        modules = sorted(set((current.modules if current else []) + [module]))
        graph.brand_identity_provenance = BrandIdentityProvenance(
            brand_id=theme.id, brand_fingerprint=theme.fingerprint,
            manager_version=MANAGER_VERSION, modules=modules,
            palette=dict(theme.palette),
            fonts={"display": theme.display.name, "body": theme.body.name,
                   "numbers": theme.mono.name},
            safe_margins={k: float(v) for k, v in theme.safe.items()},
            consistency_checks=result.checks)
        return theme

    def transition(self, graph: SceneGraph, requested: str) -> str:
        theme = self.theme_for(graph, "transitions")
        if not settings().brand_identity_enabled:
            return requested
        allowed = tuple(theme.transitions.get("allowed", ("cut", "fade")))
        return requested if requested in allowed else "cut"


brand_manager = BrandManager()


def theme_for(graph: SceneGraph, module: str) -> BrandTheme:
    return brand_manager.theme_for(graph, module)
