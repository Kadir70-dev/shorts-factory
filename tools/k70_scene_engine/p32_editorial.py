"""K70 P3.2: apply REVIEWED editorial decisions to a NEW SceneGraph copy.

Pure functions, no network, no rendering. The input graph is never mutated.
Timing is frozen: no scene duration, caption, audio, SFX or metadata change.
Narration text may change ONLY where the decision file proves the recorded
speech and captions already say the corrected words (see `caption_words`).
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping

CINEMATIC = frozenset({"threejs", "ai_video"})
CARDS = frozenset({"motion_gfx", "dataviz"})
FOOTAGE = frozenset({"image", "broll"})
PROTECTED_CHARTS = frozenset({"s35", "s67"})
PROTECTED_TOP = ("audio", "captions", "sfx", "meta", "storyboard", "asset_provenance",
                 "threejs_provenance", "motion_graphics_provenance",
                 "ai_broll_provenance", "fps", "width", "height")
VISUAL_ACTIONS = frozenset({"archival_plate", "triptych", "typography_plate", "graphic_plate"})
NOTE_ACTIONS = frozenset({"keep", "manual_review"})
_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def scene_windows(graph: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    t, out = 0.0, {}
    for s in graph["scenes"]:
        out[s["id"]] = (t, t + float(s["duration_sec"]))
        t += float(s["duration_sec"])
    return out


def caption_words(graph: Mapping[str, Any], sid: str) -> list[str]:
    """Words whose caption timing falls inside the scene's window."""
    start, end = scene_windows(graph)[sid]
    words = []
    for cap in graph.get("captions", []):
        for w in cap.get("words", []):
            mid = (float(w["s"]) + float(w["e"])) / 2
            if start <= mid < end:
                words.extend(_words(w["w"]))
    return words


def polish_transitions(scenes: list[dict], keep: set[str] = frozenset()) -> list[dict]:
    """crossfade -> cut between cards, into a card from footage, and on short beats.

    Transitions are in-clip, duration-preserving effects in render_ffmpeg, so a
    cut never shifts the audio/caption timeline. Dissolves into or out of 3D and
    AI cinematic inserts are kept (the established cinematic style).
    """
    changes = []
    for prev, cur in zip(scenes, scenes[1:]):
        if (cur.get("transition_in") != "crossfade" or cur["id"] in keep
                or cur["id"] in PROTECTED_CHARTS):
            continue
        pt, ct = prev["visual"]["type"], cur["visual"]["type"]
        if pt in CINEMATIC or ct in CINEMATIC:
            continue
        reason = ("card_to_card" if pt in CARDS and ct in CARDS else
                  "card_entry" if ct in CARDS and pt in FOOTAGE else
                  "short_punch_beat" if float(cur["duration_sec"]) < 2.5 else "")
        if reason:
            cur["transition_in"] = "cut"
            changes.append({"scene_id": cur["id"], "from": "crossfade", "to": "cut",
                            "reason": reason})
    return changes


def _visual(scene: dict, plate: str, decision: Mapping[str, Any]) -> None:
    v = scene["visual"]
    sources = decision.get("sources") or []
    typo = decision["action"] in ("typography_plate", "graphic_plate")
    credit = "; ".join(f"{s['title'].removeprefix('File:')} ({s['license']})" for s in sources)
    v.update({"type": "image", "asset_path": plate, "motion": "ken_burns",
              "strategy": "branded" if typo else "real",
              "budget_channel": "branded" if typo else "official",
              "scene_visual_type": "abstract" if typo else "real_footage",
              "layers": [], "evidence_card_path": None,
              "decision_reason": (
                  "[P3.2] original K70 explanatory graphic; not archival"
                  if decision["action"] == "graphic_plate" else
                  "[P3.2] factual typography; no licensed imagery found" if typo else
                  f"[P3.2] reviewed Wikimedia Commons: {credit}")})


def apply_decisions(source: Mapping[str, Any], decisions: Mapping[str, Any],
                    plates: Mapping[str, str]) -> tuple[dict, dict]:
    graph = copy.deepcopy(source)
    lookup = {s["id"]: s for s in graph["scenes"]}
    changes: dict[str, Any] = {"narration": [], "visuals": [], "notes": []}
    for fix in decisions.get("narration_corrections", []):
        sid = fix["scene_id"]
        scene = lookup[sid]
        if scene["narration"] != fix["from"]:
            raise ValueError(f"{sid}: narration does not match expected defect")
        if _words(fix["to"]) != caption_words(source, sid):
            raise ValueError(f"{sid}: corrected text differs from timed captions; needs re-TTS")
        scene["narration"] = fix["to"]
        changes["narration"].append({"scene_id": sid, "from": fix["from"], "to": fix["to"]})
    changes["overlays"] = []
    for fix in decisions.get("overlay_corrections", []):
        sid, idx = fix["scene_id"], int(fix["index"])
        overlays = lookup[sid]["overlays"]
        if overlays[idx] != fix["from"]:
            raise ValueError(f"{sid}: overlay does not match expected defect")
        overlays[idx] = dict(fix["to"])
        changes["overlays"].append({"scene_id": sid, "from": fix["from"], "to": fix["to"]})
    run_breaks = set()
    for d in decisions.get("scenes", []):
        sid, action = d["scene_id"], d["action"]
        if sid not in lookup:
            raise ValueError(f"unknown scene {sid}")
        if action in NOTE_ACTIONS:
            changes["notes"].append({"scene_id": sid, "action": action, "why": d.get("why", "")})
            continue
        if action not in VISUAL_ACTIONS:
            raise ValueError(f"{sid}: unknown action {action}")
        if sid in PROTECTED_CHARTS or lookup[sid]["visual"]["type"] in CINEMATIC:
            raise ValueError(f"{sid}: protected chart/3D/cinematic scene")
        if sid not in plates:
            raise ValueError(f"{sid}: plate missing")
        before = lookup[sid]["visual"]["type"]
        _visual(lookup[sid], plates[sid], d)
        if d.get("run_break"):
            run_breaks.add(sid)
        changes["visuals"].append({"scene_id": sid, "action": action, "from_type": before,
                                   "plate": plates[sid], "why": d.get("why", "")})
    changes["transitions"] = polish_transitions(graph["scenes"], keep=run_breaks)
    validate(source, graph, decisions)
    return graph, changes


def validate(source: Mapping[str, Any], graph: Mapping[str, Any],
             decisions: Mapping[str, Any]) -> None:
    old, new = source["scenes"], graph["scenes"]
    if [s["id"] for s in old] != [s["id"] for s in new]:
        raise AssertionError("scene order/IDs changed")
    fixed = {f["scene_id"] for f in decisions.get("narration_corrections", [])}
    relabelled = {f["scene_id"] for f in decisions.get("overlay_corrections", [])}
    for a, b in zip(old, new):
        for key in set(a) | set(b):
            if (key in ("visual", "transition_in")
                    or (key == "narration" and a["id"] in fixed)
                    or (key == "overlays" and a["id"] in relabelled)):
                continue
            if a.get(key) != b.get(key):
                raise AssertionError(f"{a['id']}: protected field {key} changed")
        if a["visual"]["type"] in CINEMATIC or a["id"] in PROTECTED_CHARTS:
            if a["visual"] != b["visual"] or a["transition_in"] != b["transition_in"]:
                raise AssertionError(f"{a['id']}: protected 3D/cinematic/chart changed")
        path = b["visual"].get("asset_path")
        if a["visual"] != b["visual"] and not (path and Path(path).is_file()):
            raise AssertionError(f"{a['id']}: new asset missing on disk")
    for key in PROTECTED_TOP:
        if source.get(key) != graph.get(key):
            raise AssertionError(f"protected top-level field {key} changed")
