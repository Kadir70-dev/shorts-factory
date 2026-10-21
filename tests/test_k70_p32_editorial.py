"""K70 P3.2 editorial repair: offline, synthetic graph, no network or render."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine import editorial_plates as plates
from tools.k70_scene_engine.p32_editorial import (
    apply_decisions, caption_words, polish_transitions, validate,
)


def _scene(sid, kind, dur, text, transition="crossfade"):
    return {"id": sid, "narration": text, "duration_sec": dur, "transition_in": transition,
            "overlays": [], "visual": {"type": kind, "asset_path": None, "layers": []}}


def _captions(scenes, spoken):
    caps, t = [], 0.0
    for s in scenes:
        words = spoken.get(s["id"], s["narration"]).split()
        step = s["duration_sec"] / len(words)
        caps.append({"start": t, "end": t + s["duration_sec"], "text": " ".join(words),
                     "words": [{"w": w, "s": t + i * step, "e": t + (i + 1) * step}
                               for i, w in enumerate(words)]})
        t += s["duration_sec"]
    return caps


@pytest.fixture
def graph():
    scenes = [_scene("s1", "threejs", 3, "Open.", "cut"),
              _scene("s2", "motion_gfx", 3, "One card."),
              _scene("s3", "motion_gfx", 3, "Two card."),
              _scene("s30", "image", 4, "A race sharply higher."),
              _scene("s35", "dataviz", 3, "Chart one."),
              _scene("s36", "dataviz", 3, "Chart two."),
              _scene("s7", "broll", 1.5, "Punch."),
              _scene("s8", "ai_video", 1.5, "Cinema.")]
    spoken = {"s30": "A race to the moon."}
    return {"meta": {"video_id": "x"}, "scenes": scenes, "audio": {"voiceover_path": "vo.wav"},
            "captions": _captions(scenes, spoken), "sfx": []}


def _plate(tmp_path: Path) -> str:
    path = tmp_path / "plate.jpg"
    Image.new("RGB", (1080, 1920), "gray").save(path)
    return str(path)


def test_narration_fix_only_when_recorded_captions_already_say_it(graph, tmp_path):
    good = {"narration_corrections": [{"scene_id": "s30", "from": "A race sharply higher.",
                                       "to": "A race to the moon."}], "scenes": []}
    before = copy.deepcopy(graph)
    out, changes = apply_decisions(graph, good, {})
    assert graph == before
    assert out["scenes"][3]["narration"] == "A race to the moon."
    assert out["captions"] == graph["captions"]
    assert caption_words(graph, "s30") == ["a", "race", "to", "the", "moon"]
    bad = {"narration_corrections": [{"scene_id": "s30", "from": "A race sharply higher.",
                                      "to": "A race to Mars."}], "scenes": []}
    with pytest.raises(ValueError, match="re-TTS"):
        apply_decisions(graph, bad, {})


def test_visual_repair_protects_cinematic_and_sourced_charts(graph, tmp_path):
    plate = _plate(tmp_path)
    ok = {"scenes": [{"scene_id": "s30", "action": "archival_plate", "label": "x",
                      "sources": [{"title": "File:A.jpg", "license": "Public domain"}]}]}
    out, _ = apply_decisions(graph, ok, {"s30": plate})
    v = out["scenes"][3]["visual"]
    assert v["type"] == "image" and v["asset_path"] == plate and v["budget_channel"] == "official"
    for sid in ("s1", "s35"):
        with pytest.raises(ValueError, match="protected"):
            apply_decisions(graph, {"scenes": [{"scene_id": sid, "action": "archival_plate"}]},
                            {sid: plate})


def test_transition_polish_is_selective(graph):
    scenes = copy.deepcopy(graph["scenes"])
    changes = {c["scene_id"]: c["reason"] for c in polish_transitions(scenes, keep=set())}
    assert changes == {"s3": "card_to_card", "s36": "card_to_card", "s7": "short_punch_beat"}
    assert scenes[7]["transition_in"] == "crossfade"   # into AI cinematic: kept
    assert scenes[4]["transition_in"] == "crossfade"   # protected chart s35 untouched


def test_validate_rejects_timing_and_caption_changes(graph):
    moved = copy.deepcopy(graph)
    moved["scenes"][2]["duration_sec"] = 3.5
    with pytest.raises(AssertionError, match="duration_sec"):
        validate(graph, moved, {})
    recap = copy.deepcopy(graph)
    recap["captions"][0]["text"] = "changed"
    with pytest.raises(AssertionError, match="captions"):
        validate(graph, recap, {})


def test_overlay_correction_must_match_expected_defect(graph):
    graph["scenes"][3]["overlays"] = [{"type": "stat", "text": "Z$1", "sub": "date"}]
    fix = {"scenes": [], "overlay_corrections": [{
        "scene_id": "s30", "index": 0, "from": {"type": "stat", "text": "Z$1", "sub": "date"},
        "to": {"type": "stat", "text": "date", "sub": "Z$1"}}]}
    out, changes = apply_decisions(graph, fix, {})
    assert out["scenes"][3]["overlays"][0]["sub"] == "Z$1"
    fix["overlay_corrections"][0]["from"] = {"type": "stat", "text": "other"}
    with pytest.raises(ValueError, match="overlay"):
        apply_decisions(graph, fix, {})


def test_plates_are_portrait_and_keep_whole_source(tmp_path):
    wide = tmp_path / "note.png"
    Image.new("RGB", (2000, 860), "blue").save(wide)
    out = plates.archival_plate(wide, tmp_path / "p.jpg", label="Z$ note", text=["LINE"])
    assert Image.open(out).size == (1080, 1920)
    trip = plates.triptych_plate([(wide, "a"), (wide, "b"), (wide, "c")], tmp_path / "t.jpg")
    assert Image.open(trip).size == (1080, 1920)
    typo = plates.typography_plate([("LIBERTY DOLLAR", 80, True)], tmp_path / "y.jpg",
                                   kicker="14 NOVEMBER 2007")
    assert Image.open(typo).size == (1080, 1920)
    with pytest.raises(ValueError):
        plates.archival_plate(wide, tmp_path / "bad.jpg", crop=(0.5, 0, 0.2, 1))
    plain = Image.open(plates.archival_plate(wide, tmp_path / "a.jpg", label="x"))
    credited = Image.open(plates.archival_plate(wide, tmp_path / "b.jpg", label="x",
                                                credit="Photo: A · CC BY-SA 3.0 · adapted"))
    assert plain.tobytes() != credited.tobytes()      # on-plate attribution drawn


def test_explainer_graphics_are_original_and_honest(tmp_path):
    import hashlib
    from tools.k70_scene_engine import explainer_graphics as gfx
    n, h = gfx.proof_of_work("t:", zero_hex=3)
    assert h == hashlib.sha1(f"t:{n}".encode()).hexdigest() and h.startswith("000")
    assert not any(hashlib.sha1(f"t:{i}".encode()).hexdigest().startswith("000") for i in range(n))
    geo = tmp_path / "geo.json"
    geo.write_text('{"features":[{"properties":{"ADMIN":"X"},"geometry":{"type":"Polygon",'
                   '"coordinates":[[[0,0],[10,0],[10,20],[0,20],[0,0]]]}}]}')
    outs = [gfx.map_plate(geo, "X", tmp_path / "m.jpg", marker=(5, 10), marker_label="City"),
            gfx.terminal_plate("t:", tmp_path / "t.jpg", zero_hex=3),
            gfx.shutter_plate(tmp_path / "s.jpg", notice=["CERRADO"]),
            gfx.ledger_plate(tmp_path / "l.jpg", rows=[("Decree", "1570/2001")], stamp="FROZEN")]
    assert all(Image.open(o).size == (1080, 1920) for o in outs)


def test_graphic_plate_is_marked_not_archival(graph, tmp_path):
    plate = _plate(tmp_path)
    out, _ = apply_decisions(graph, {"scenes": [{"scene_id": "s30", "action": "graphic_plate"}]},
                             {"s30": plate})
    v = out["scenes"][3]["visual"]
    assert v["strategy"] == "branded" and "not archival" in v["decision_reason"]
