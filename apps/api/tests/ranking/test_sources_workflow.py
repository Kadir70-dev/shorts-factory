"""Source workflow: reference catalog, provenance gates, compilation rights,
Top-5 boundary selection, clip mixing rules and copy validation. No network,
no ffmpeg (detection is exercised on synthetic arrays)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.ranking import catalog, compilation, copywriter, reference, segment_top5, selector, topic
from app.ranking.db import connect, eligible_source_sql


@pytest.fixture(autouse=True)
def _no_ledger(monkeypatch):
    from app import state
    monkeypatch.setattr(state, "recent", lambda *a, **k: [])
    monkeypatch.setattr(state, "record_many", lambda *a, **k: None)
    monkeypatch.setattr(state, "record", lambda *a, **k: None)


@pytest.fixture
def con(tmp_path):
    with connect(tmp_path / "s.db") as c:
        yield c


def test_reference_import_is_metadata_only(con, tmp_path):
    inv = tmp_path / "inv"
    inv.mkdir()
    (inv / "rankzilla_inventory.txt").write_text(
        "v6__FPIOWf4 | DON'T CHECK THE SOUND 😭😭\n7sKAk3sAAmc | Ranking Top 5 Dogs\n")
    (inv / "shorts_ids.txt").write_text("v6__FPIOWf4\n7sKAk3sAAmc\n0kidg8Xmubk\n")
    rep = reference.import_inventory(con, inv, "rankzilla23")
    assert rep["catalog_total"] == 3 and rep["with_local_media"] == 0
    rows = {r["video_id"]: dict(r) for r in con.execute("SELECT * FROM reference_videos")}
    assert rows["v6__FPIOWf4"]["title"].startswith("DON'T")     # bare-id list didn't wipe it
    assert all(r["downloaded"] == 0 for r in rows.values())
    st = reference.study(con, "rankzilla23")
    assert st["titles"] == 2 and "never reused" in st["note"]
    # reference rows never appear in the selectable sources
    assert con.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_provenance_match_by_filename_and_sidecar(con, tmp_path):
    con.execute("INSERT INTO reference_videos (video_id, channel) VALUES ('v6__FPIOWf4', 'rz')")
    a = tmp_path / "DONT CHECK [v6__FPIOWf4].mp4"
    b = tmp_path / "clip.mp4"
    (tmp_path / "clip.info.json").write_text(json.dumps(
        {"id": "x", "webpage_url": "https://www.youtube.com/shorts/v6__FPIOWf4"}))
    c = tmp_path / "unrelated_abcdefghijk_long_name.mp4"
    assert reference.match_ref(con, a) == "v6__FPIOWf4"
    assert reference.match_ref(con, b) == "v6__FPIOWf4"
    assert reference.match_ref(con, c) == ""


def _src(con, sid, **kw):
    row = {"path": f"/x/{sid}.mp4", "sha256": f"s{sid}", "duration": 25, "width": 540,
           "height": 960, "has_audio": 1, "license": "owned", "license_verified": 1,
           "license_proof": "p", "category": "animals", "kind": "clip",
           "underlying_rights_verified": 0, "provenance_ref": "", "permission_proof": "",
           "underlying_proof": ""}
    row.update(kw)
    cols = ",".join(row)
    con.execute(f"INSERT INTO sources (id,{cols}) VALUES (?,{','.join('?' * len(row))})",
                (sid, *row.values()))


def _eligible(con):
    w, a = eligible_source_sql()
    return {r[0] for r in con.execute(f"SELECT s.id FROM sources s WHERE {w}", a)}


def test_compilation_needs_underlying_rights_and_reference_needs_permission(con):
    _src(con, 1)                                                  # plain verified clip
    _src(con, 2, kind="compilation")                              # clips inside unverified
    _src(con, 3, kind="compilation", underlying_rights_verified=1)
    _src(con, 4, kind="compilation", underlying_rights_verified=1, provenance_ref="v6__FPIOWf4")
    _src(con, 5, kind="compilation", underlying_rights_verified=1, provenance_ref="v6__FPIOWf4",
         permission_proof="signed email 2026-11-01")
    assert _eligible(con) == {1, 3, 5}


def test_verify_source_gates(con, tmp_path):
    vid = tmp_path / "comp.mp4"
    vid.write_bytes(b"x")
    _src(con, 1, path=str(vid), kind="compilation", license_verified=0)
    with pytest.raises(ValueError, match="clips inside"):
        catalog.verify_source(con, 1, "kadir")
    out = catalog.verify_source(con, 1, "kadir", underlying_proof="Pexels URLs: …")
    assert out["license_verified"] == 1 and out["underlying_rights_verified"] == 1
    _src(con, 2, path=str(tmp_path / "ref.mp4"), license_verified=0, provenance_ref="v6__FPIOWf4")
    with pytest.raises(ValueError, match="written permission"):
        catalog.verify_source(con, 2, "kadir")


def test_set_bounds_validates_and_saves_five_manual_clips(con, tmp_path, monkeypatch):
    monkeypatch.setattr(compilation, "_interest", lambda p, a: [0.5] * 300)
    monkeypatch.setattr(compilation.probe, "segment_hash", lambda *a: "0" * 16)
    monkeypatch.setattr(compilation.probe, "footage_signature", lambda *a, **k: "0" * 16)
    _src(con, 1, path=str(tmp_path / "c.mp4"), kind="compilation")
    with pytest.raises(ValueError):
        compilation.set_bounds(con, 1, [0, 5, 4, 10, 15, 20])         # not increasing
    with pytest.raises(ValueError):
        compilation.set_bounds(con, 1, [0, 5, 10, 15, 20, 99])        # past the end
    ids = compilation.set_bounds(con, 1, [0, 5, 10, 15, 20, 25], labels=list("abcde"))
    rows = [dict(r) for r in con.execute("SELECT * FROM segments ORDER BY start")]
    assert len(ids) == 5 and [r["source_rank"] for r in rows] == [5, 4, 3, 2, 1]
    assert all(r["manual"] == 1 for r in rows) and rows[0]["label"] == "a"
    compilation.set_bounds(con, 1, [0, 5, 10, 15, 20, 25])            # re-run: upsert, no dupes
    assert con.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 5


def _sig(n, at):
    s = np.zeros(n, dtype=np.float32)
    for i in at:
        s[i] = 1.0
    return s


def test_choose_finds_five_moments_and_rejects_four():
    hz, n = segment_top5.HZ, 25 * segment_top5.HZ
    at = [5 * hz, 10 * hz, 15 * hz, 20 * hz]
    sig = {"cut": _sig(n, at), "overlay": _sig(n, at), "audio": _sig(n, at)}
    fused = 0.35 * sig["cut"] + 0.45 * sig["overlay"] + 0.2 * sig["audio"]
    res = segment_top5.choose(fused, sig, n)
    assert res["bounds"][1:5] == [5.0, 10.0, 15.0, 20.0] and res["confidence"] >= 0.6
    # four moments of 5 s in 20 s: no valid 5-way split with >=2.5 s moments
    # can use only real boundaries, so confidence collapses
    n4, at4 = 20 * hz, [5 * hz, 10 * hz, 15 * hz]
    sig4 = {k: _sig(n4, at4) for k in ("cut", "overlay", "audio")}
    res4 = segment_top5.choose(0.35 * sig4["cut"] + 0.45 * sig4["overlay"] + 0.2 * sig4["audio"],
                               sig4, n4)
    assert not res4["bounds"] or res4["confidence"] < segment_top5.CONF_SAVE


def test_overlay_change_ignores_motion_and_sees_graphic_swap():
    rng = np.random.default_rng(0)
    f = rng.uniform(0, 255, (60, 40, 40)).astype(np.float32)   # busy moving content
    f[:, 2:10, 2:10] = 30                                        # static graphic "5"…
    f[30:, 2:10, 2:10] = 230                                     # …turns into "4" at t=30
    sig = segment_top5.overlay_change(f)
    assert int(np.argmax(sig)) in range(28, 33) and sig[10] == 0


def test_mixing_caps_one_clip_per_compilation_and_blocks_same_footage():
    a = {"kind": "compilation", "label": "a horse in running in the farm",
         "signals": json.dumps({"fsig": "ffff000000000000"})}
    b = {"kind": "compilation", "label": "A horse in running in the farm ",
         "signals": json.dumps({})}
    c = {"kind": "compilation", "label": "ducks", "signals": json.dumps({"fsig": "ffff000000000001"})}
    d = {"kind": "compilation", "label": "geese", "signals": json.dumps({"fsig": "0000ffffffff0000"})}
    assert selector._cap(a) == 1 and selector._cap({"kind": "clip"}) == 2
    assert selector.same_footage(a, b)                # identical annotation
    assert selector.same_footage(a, c)                # signatures 1 bit apart
    assert not selector.same_footage(a, d)            # different footage
    assert selector.merit({"score": 0.5, "source_rank": 1}) > selector.merit({"score": 0.5, "source_rank": 5})


def test_topic_says_unknown_instead_of_guessing():
    assert topic.detect("DON'T CHECK THE SOUND 😭😭") == ("", 0.0, "unknown")
    assert topic.detect("film of chickens")[0] == "animals"
    assert topic.detect("anything", declared="sports") == ("sports", 1.0, "declared")
    assert topic.subject("charming geese and goslings") == "goose"


def test_copywriter_validation():
    ok = {"title": "Top 5 Animal Moments", "hook": "#1 IS A BEACH ZOOMIE!",
          "captions": {k: "Snack radar on" for k in "54321"}, "outro": "Who's your #1?"}
    assert copywriter._valid(ok)                                   # "#1" is not a hashtag
    assert not copywriter._valid({**ok, "outro": "Follow #shorts"})
    assert not copywriter._valid({**ok, "hook": "x" * 30})
    assert not copywriter._valid({**ok, "captions": {"5": "a"}})
