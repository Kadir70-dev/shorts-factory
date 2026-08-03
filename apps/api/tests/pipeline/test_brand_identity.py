from __future__ import annotations

from app.brand import brand_manager, load_theme, theme_for
from app.brand import overlays
from app.brand.manager import MANAGER_VERSION, validate
from app.config import settings
from app.pipeline import ai_broll, motiongfx, threejs_engine
import random
from app.schemas.scene import Caption, Overlay, StoryboardScene


def beat(**changes):
    base = dict(scene_id="s1.b1", source_scene_id="s1",
        narration="Revenue reached $4 billion in 2025.",
        duration_estimate=2.0, visual_objective="Show compound revenue growth",
        primary_entity="Revenue", secondary_entities=[], company="K70", location="USA",
        year=2025, financial_numbers=["4 billion"], emotion="confident",
        recommended_visual_type="dataviz",
        recommended_camera_movement="zoom_in", motion_graphics_needed=True,
        threejs_candidate=True, ai_broll_candidate=True,
        asset_priority=["local_graphics", "ai_recreation"],
        transition="cut", overlay_text=["$4B REVENUE"], visual_confidence_score=.95)
    base.update(changes)
    return StoryboardScene(**base)


def test_disabled_path_is_legacy_and_does_not_mutate(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", False)
    assert theme_for(graph, "threejs") is load_theme("k70")
    assert graph.brand_identity_provenance is None
    assert brand_manager.transition(graph, "whip") == "whip"


def test_complete_package_and_mobile_rules():
    result = validate(load_theme("k70"))
    assert result.valid
    assert all(result.checks.values())


def test_manager_receipt_unifies_modules(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    for module in ("motion_graphics", "threejs", "ai_broll", "captions"):
        theme_for(graph, module)
    receipt = graph.brand_identity_provenance
    assert receipt.manager_version == MANAGER_VERSION
    assert receipt.modules == ["ai_broll", "captions", "motion_graphics", "threejs"]
    assert receipt.palette == load_theme("k70").palette
    assert all(receipt.consistency_checks.values())


def test_typography_captions_lower_third_and_safe_area(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    theme = theme_for(graph, "captions")
    graph.captions = [Caption(start=0, end=1, text="Revenue grew 20 percent")]
    ass = overlays.caption_ass(graph, theme, animation="keyword_flash")
    assert theme.body.name in ass and theme.ass("primary") in ass
    plates, filters = overlays.lower_third_filters(
        theme, "K70 FINANCE", "MARKET BRIEF", 1080, 1920, 0, 2)
    assert not plates
    joined = " ".join(filters)
    assert theme.display.path in joined and theme.ff("primary") in joined
    assert float(theme.lower_third["y"]) < float(theme.captions["y"])


def test_chart_and_ai_prompt_share_palette(graph, monkeypatch, tmp_path):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    scene = graph.scenes[0]
    board = beat()
    payload = threejs_engine._payload(
        graph, scene, board, threejs_engine.map_template(board), "preview", 7, tmp_path)
    prompt = ai_broll.prompt_spec(graph, scene, board)
    theme = load_theme("k70")
    assert payload["palette"] == theme.palette
    assert prompt.color_palette == [theme.hex(k) for k in
                                    ("bg", "bg_soft", "primary", "secondary", "ink")]
    assert payload["fontFamily"] == theme.display.name


def test_brand_transition_policy(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    assert brand_manager.transition(graph, "fade") == "fade"
    assert brand_manager.transition(graph, "whip") == "cut"


def test_texture_chart_timeline_icon_and_cta_styles_are_central(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    theme = theme_for(graph, "component_styles")
    assert motiongfx.brand_treatment(theme, random.Random(9)) == "grid_drift"
    assert theme.chart["series_colors"][:2] == ["primary", "secondary"]
    assert theme.timeline["active_color"] == "primary"
    assert theme.icons["style"] == "outline"
    assert theme.cta["style"] == theme.outro["style"] == "endcard"


def test_overlay_colors_are_palette_bound(graph, monkeypatch):
    monkeypatch.setattr(settings(), "brand_identity_enabled", True)
    theme = theme_for(graph, "overlays")
    scene = graph.scenes[0]
    scene.overlays = [Overlay(type="headline", text="THE MARKET MOVED", y=.3),
                      Overlay(type="stat", text="GAIN", sub="20%", y=.45)]
    filters = " ".join(overlays.scene_overlay_filters(scene, theme, 1080, 1920))
    assert theme.ff("ink") in filters and theme.ff("bg") in filters
