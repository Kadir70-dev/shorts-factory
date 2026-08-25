from tools.k70_scene_engine.animation.catalog import get, load_catalog
from tools.k70_scene_engine.animation.director import sequence_actions
from tools.k70_scene_engine.animation.retarget import build_plan, semantic_map


def test_catalog_has_reusable_core_actions():
    assert len(load_catalog()) >= 15
    assert get("walk_confident").license == "CC0"


def test_semantic_alias_mapping():
    mapping = semantic_map(["pelvis", "upperarm_l", "calf_r"],
                           ["hips", "upper_arm_l", "shin_r"])
    assert mapping == {"pelvis": "hips", "upperarm_l": "upper_arm_l", "calf_r": "shin_r"}


def test_plan_cache_and_timing(tmp_path):
    args = (["root", "pelvis", "foot_l"], ["root", "hips", "foot_l"])
    first, _ = build_plan(*args, cache_dir=tmp_path)
    second, elapsed = build_plan(*args, cache_dir=tmp_path)
    assert first.mapping == second.mapping
    assert second.cache_hit and elapsed >= 0


def test_deterministic_sequence():
    rows = sequence_actions(["walk_confident", "turn_left", "explain_hands"],
                            character="sarah", mode="humanoid", frames_per_action=20)
    assert [(r.start_frame, r.end_frame) for r in rows] == [(1, 20), (21, 40), (41, 60)]


def test_unverified_humanoid_point_is_not_faked():
    import pytest
    from tools.k70_scene_engine.animation.director import get_motion
    with pytest.raises(LookupError):
        get_motion("point_screen", character="sarah", mode="humanoid")
