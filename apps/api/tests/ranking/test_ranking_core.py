"""Ranking pipeline: selection rules, approval gates, scheduling, channel
isolation and upload preflight — all without ffmpeg, network or credentials."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from app.ranking import catalog, channels, commentary, schedule, selector, uploader
from app.ranking.db import connect


@pytest.fixture(autouse=True)
def _no_ledger(monkeypatch):
    """Keep tests out of the real data/state rotation ledger."""
    from app import state
    monkeypatch.setattr(state, "recent", lambda *a, **k: [])
    monkeypatch.setattr(state, "record_many", lambda *a, **k: None)


def _h(seed: int) -> str:
    """Three distinct 64-bit hashes per seed, far apart from other seeds."""
    import random
    r = random.Random(seed)
    return ",".join(f"{r.getrandbits(64):016x}" for _ in range(3))


def _src(con, sid, *, verified=True, lic="licensed", dur=30.0, sha=None, cat="animals"):
    con.execute("""INSERT INTO sources (id, path, sha256, duration, width, height, fps,
                   has_audio, license, license_verified, attribution, category)
                   VALUES (?,?,?,?,1920,1080,30,1,?,?,?,?)""",
                (sid, f"/x/{sid}.mp4", sha or f"sha{sid}", dur, lic, int(verified),
                 f"Credit {sid}", cat))


def _seg(con, gid, sid, start, score, ph=None, cat="animals"):
    con.execute("""INSERT INTO segments (id, source_id, start, end, score, category, phash)
                   VALUES (?,?,?,?,?,?,?)""", (gid, sid, start, start + 6, score, cat,
                                               ph or _h(gid)))


@pytest.fixture
def con(tmp_path):
    with connect(tmp_path / "r.db") as c:
        for sid in (1, 2, 3):
            _src(c, sid)
            for k in range(3):
                _seg(c, sid * 10 + k, sid, k * 8.0, 0.3 + 0.05 * k + 0.01 * sid)
        yield c


def test_select_respects_rules_and_orders_by_score(con):
    c = selector.select(con, "ranking_shorts", category="animals", seed=1)
    ranks = c["payload"]["ranks"]
    assert [r["rank"] for r in ranks] == [5, 4, 3, 2, 1]
    assert [r["score"] for r in ranks] == sorted(r["score"] for r in ranks)
    per = {}
    for r in ranks:
        per[r["source_id"]] = per.get(r["source_id"], 0) + 1
    assert len(per) >= 3 and max(per.values()) <= 2
    assert c["status"] == "pending_approval"
    assert 20 <= c["payload"]["est_duration"] <= 45


def test_unverified_and_unknown_licenses_never_selected(con):
    _src(con, 9, verified=False)
    _src(con, 8, lic="unknown")
    for sid in (8, 9):
        for k in range(3):
            _seg(con, sid * 10 + k, sid, k * 8.0, 0.99)       # tempting scores
    c = selector.select(con, "ranking_shorts", category="animals")
    assert not {r["source_id"] for r in c["payload"]["ranks"]} & {8, 9}


def test_near_duplicates_are_rejected(con):
    # every segment of source 3 is a near-copy of source 1's best moment
    best = con.execute("SELECT phash FROM segments WHERE id=12").fetchone()[0]
    con.execute("UPDATE segments SET phash=? WHERE source_id=3", (best,))
    with pytest.raises(selector.SelectionError):
        selector.select(con, "ranking_shorts", category="animals")   # only 2 families left


def test_reupload_counts_as_same_family(con):
    _src(con, 4, dur=30.4)
    for k in range(3):                       # same moments as source 1
        ph = con.execute("SELECT phash FROM segments WHERE id=?", (10 + k,)).fetchone()[0]
        _seg(con, 40 + k, 4, k * 8.0, 0.2, ph=ph)
    fam = selector.source_families(con)
    assert fam[4] == 1 and fam[2] == 2


def test_no_moment_or_combo_reuse_and_reject_frees_moments(con):
    a = selector.select(con, "ranking_shorts", category="animals", seed=1)
    used = {r["segment_id"] for r in a["payload"]["ranks"]}
    with pytest.raises(selector.SelectionError):              # only 9 moments total
        selector.select(con, "ranking_shorts", category="animals", seed=2)
    selector.reject(con, a["id"])
    b = selector.select(con, "ranking_shorts", category="animals", seed=1)
    assert b["combo_key"] != a["combo_key"]
    assert {r["segment_id"] for r in b["payload"]["ranks"]} & used   # freed for reuse


def test_approval_gate_and_edit_resets_approval(con):
    c = selector.select(con, "ranking_shorts", category="animals")
    with pytest.raises(ValueError):
        selector.approve(con, c["id"], " ")
    assert selector.approve(con, c["id"], "kadir")["status"] == "approved"
    pay = c["payload"]
    pay["copy"]["title"] = "Top 5 Animals Edited"
    assert selector.update_payload(con, c["id"], pay)["status"] == "pending_approval"
    pay["ranks"][0]["segment_id"] = 999
    with pytest.raises(ValueError):
        selector.update_payload(con, c["id"], pay)


def test_approve_fails_if_license_revoked(con):
    c = selector.select(con, "ranking_shorts", category="animals")
    con.execute("UPDATE sources SET license_verified=0 WHERE id=?",
                (c["payload"]["ranks"][0]["source_id"],))
    with pytest.raises(ValueError):
        selector.approve(con, c["id"], "kadir")


def test_render_refuses_unapproved():
    from app.ranking import render
    with pytest.raises(PermissionError):
        render.render({"id": 1, "status": "pending_approval", "payload": {}}, {}, {}, None)


def test_suggest_returns_fewer_when_footage_lacks_moments():
    curve = [0.0] * 80                                      # 8 s, one shot
    curve[50] = 1.0
    out = catalog.suggest(8.0, curve, [], want=5)
    assert len(out) == 1
    s = out[0]
    assert s["start"] <= 5.0 <= s["end"] and (5.0 - s["start"]) / (s["end"] - s["start"]) > 0.5


def test_metadata_has_credits_and_valid_title(con):
    c = selector.select(con, "ranking_shorts", category="animals")
    m = commentary.metadata(c, {"cta": "Follow!"})
    assert len(m["title"]) <= 100 and "#shorts" in m["title"]
    assert "Credits:" in m["description"] and "Credit 1" in m["description"]
    assert m["default_language"] == "en-US" and not m["made_for_kids"]


def test_dst_aware_slots():
    cfg = {"schedule": {"timezone": "America/New_York", "slots": ["16:00"]}}
    before = schedule.slots_for_day(date(2026, 10, 30), cfg)[0]   # EDT
    after = schedule.slots_for_day(date(2026, 11, 3), cfg)[0]     # EST
    assert schedule.to_rfc3339(before) == "2026-10-30T20:00:00Z"
    assert schedule.to_rfc3339(after) == "2026-11-03T21:00:00Z"
    now = datetime(2026, 11, 3, 20, 45, tzinfo=timezone.utc)        # 3:45 PM EST
    nxt = schedule.next_slots(cfg, {"2026-11-04T21:00:00Z"}, count=1, now=now)
    assert schedule.to_rfc3339(nxt[0]) == "2026-11-05T21:00:00Z"   # 3rd skipped (lead), 4th taken


def test_real_channel_configs_are_isolated():
    assert channels.isolation_errors() == []
    assert {"ranking_shorts", "k70_dive", "finance_shorts"} <= set(channels.all_channels())


def test_isolation_detects_shared_token(tmp_path, monkeypatch):
    d = tmp_path / "publishing"
    d.mkdir()
    for ch in ("a", "b"):
        (d / f"{ch}.yaml").write_text(json.dumps({
            "channel": ch, "display_name": ch, "output_dir": f"out/{ch}",
            "schedule": {"slots": ["10:00"]},
            "youtube": {"token": "config/secrets/a/token.json",
                        "client_secret": f"config/secrets/{ch}/cs.json"}}))
    monkeypatch.setattr(channels, "PUBLISHING_DIR", d)
    errs = channels.isolation_errors()
    assert any("share token" in e for e in errs)
    assert any("b: token must live under" in e for e in errs)


def _approved(con):
    c = selector.select(con, "ranking_shorts", category="animals")
    return selector.approve(con, c["id"], "kadir")


def test_upload_preflight_blocks(con):
    c = _approved(con)
    rnd = {"path": "/x/final.mp4", "sha256": "abc"}
    meta = commentary.metadata(c, {})
    with pytest.raises(uploader.UploadBlocked, match="allow-public"):
        uploader.upload(con, "ranking_shorts", rnd, c, meta, schedule_slot=True, dry_run=True)
    with pytest.raises(uploader.UploadBlocked, match="belongs to"):
        uploader.upload(con, "k70_dive", rnd, c, meta, dry_run=True)
    with pytest.raises(uploader.UploadBlocked, match="not approved"):
        uploader.upload(con, "ranking_shorts", rnd, {**c, "status": "pending_approval"},
                        meta, dry_run=True)
    res = uploader.upload(con, "ranking_shorts", rnd, c, meta, dry_run=True)
    assert res["body"]["status"]["privacyStatus"] == "private"
    assert res["blocking"]                       # no credentials in the test env
    with pytest.raises(uploader.UploadBlocked, match="uploads are disabled"):
        uploader.upload(con, "ranking_shorts", rnd, c, meta)  # kill switch is default
    con.execute("UPDATE uploads SET status='uploaded', video_id='vid1'")
    with pytest.raises(uploader.UploadBlocked, match="already uploaded"):
        uploader.upload(con, "ranking_shorts", rnd, c, meta, dry_run=True)


def test_scheduled_upload_body_and_quota(con):
    c = _approved(con)
    meta = commentary.metadata(c, {})
    res = uploader.upload(con, "ranking_shorts", {"path": "/x", "sha256": "s1"}, c, meta,
                          schedule_slot=True, allow_public=True, dry_run=True)
    st = res["body"]["status"]
    assert st["privacyStatus"] == "private" and st["publishAt"].endswith("Z")
    con.execute("INSERT INTO quota (channel, day, units) VALUES (?,?,?)",
                ("ranking_shorts", schedule.quota_day(), 9000))
    with pytest.raises(uploader.UploadBlocked, match="quota"):
        uploader.upload(con, "ranking_shorts", {"path": "/x", "sha256": "s2"}, c, meta,
                        dry_run=True)


def test_plates_stay_inside_shorts_safe_area(tmp_path):
    from app.ranking import plates, qa, render
    brand = {"primary": "#e11d2a", "accent": "#ffd400", "accent_ink": "#111111",
             "ink": "#ffffff", "bg": "#111111"}
    t = plates.title_plate("Top 5 Animals Who Chose Absolute Total Chaos Today", "@h",
                           brand, tmp_path / "t.png")
    c = plates.caption_plate("This caption is deliberately far too long to fit", brand,
                             tmp_path / "c.png")
    b = plates.rank_badge(1, brand, tmp_path / "b.png")
    h = plates.hook_plate("Wait for number one it is insane", brand, tmp_path / "h.png")
    for path, (x, y), z in ((t, (0, render.TITLE_Y), plates.SAFE_TOP),
                            (h, (0, render.HOOK_Y), plates.SAFE),
                            (c, render.CAPTION_POS, plates.SAFE),
                            (b, render.BADGE_POS, plates.SAFE)):
        x0, y0, x1, y1 = qa.plate_bbox(str(path), x, y)
        assert x0 >= z["left"] - 2 and x1 <= z["right"] + 2, path
        assert y0 >= z["top"] and y1 <= z["bottom"], path
    assert render.fg_size(1920, 1080) == (1080, 760)        # 16:9 side-cropped
    assert render.fg_size(1080, 1920) == (1080, 1920)       # vertical fills


def test_publishing_disabled_by_default_on_every_channel():
    for ch in channels.all_channels():
        assert channels.load(ch).get("uploads_enabled") is False, ch


def test_verify_source_requires_proof_and_persists(tmp_path):
    import yaml
    vid = tmp_path / "clip.mp4"
    vid.write_bytes(b"x")
    with connect(tmp_path / "v.db") as c:
        c.execute("""INSERT INTO sources (id, path, sha256, duration, license, license_proof)
                     VALUES (1, ?, 's', 10, 'licensed', 'Pexels License — https://x')""",
                  (str(vid),))
        c.execute("INSERT INTO sources (id, path, sha256, duration) VALUES (2, '/n.mp4', 't', 10)")
        with pytest.raises(ValueError):
            catalog.verify_source(c, 2, "kadir")              # no license/proof
        with pytest.raises(ValueError):
            catalog.verify_source(c, 1, "  ")
        assert catalog.verify_source(c, 1, "kadir")["license_verified"] == 1
    entry = yaml.safe_load((tmp_path / "licenses.yaml").read_text())["clip.mp4"]
    assert entry["verified"] is True and entry["verified_by"] == "kadir"


def test_gallery_lists_concepts_with_commands(con, tmp_path):
    from app.ranking import gallery
    c = selector.select(con, "ranking_shorts", category="animals")
    html = gallery.build(con, tmp_path / "g" / "index.html").read_text()
    assert f"#{c['id']}" in html and "Needs review" in html
    assert f"approve {c['id']} --by YOUR_NAME" in html
    assert "<script>" in html and "Not rendered yet" in html


def test_long_single_shot_offers_several_moments():
    curve = [0.0] * 200                                     # 20 s, no cuts
    curve[40], curve[150] = 1.0, 0.9
    out = catalog.suggest(20.0, curve, [], want=5)
    assert len(out) == 2 and out[0]["end"] <= out[1]["start"]


def test_long_hook_fits_plate_height(tmp_path):
    from PIL import Image
    from app.ranking import plates
    brand = {"primary": "#e11d2a", "accent": "#ffd400", "accent_ink": "#111111",
             "ink": "#ffffff", "bg": "#111111"}
    p = plates.hook_plate("#1 is a beach zoomie!", brand, tmp_path / "h.png")
    alpha = Image.open(p).getchannel("A")
    bottom_rows = [alpha.getpixel((x, alpha.height - 1)) for x in range(0, alpha.width, 4)]
    assert max(bottom_rows) == 0          # nothing cut off at the plate's bottom edge


def test_edge_graphic_is_cropped_and_inner_graphic_delogoed():
    from app.ranking.render import source_prefilter
    # number hugging the right edge of a 540x408 picture → crop it off (<=20 %)
    pre, w, h = source_prefilter({"overlay_box": [451, 266, 68, 113],
                                  "crop": "540:408:0:278"}, 540, 960)
    assert "delogo" not in pre and pre.startswith("crop=")
    assert w <= 540 - 68 and h == 408
    # number at the bottom centre, removing it would cost >20 % → delogo
    pre, w, h = source_prefilter({"overlay_box": [222, 571, 95, 131],
                                  "crop": "540:408:0:296"}, 540, 960)
    assert pre.startswith("delogo=x=222:y=571:w=95:h=131,") and (w, h) == (540, 408)
    # plain clip: nothing to do
    assert source_prefilter({}, 1920, 1080) == ("", 1920, 1080)


def test_foreground_never_rises_behind_title():
    from app.ranking import render
    for w, h in ((1920, 1080), (540, 408), (452, 408), (1440, 1080), (1000, 1000)):
        fw, fh = render.fg_size(w, h)
        assert fh == render.FG_MIN_H
        assert render.FG_CENTER_Y - fh // 2 >= render.TITLE_Y + 330   # below title text
    assert render.fg_size(1080, 1920) == (1080, 1920)
    assert render.fg_size(720, 1280) == (1080, 1920)
