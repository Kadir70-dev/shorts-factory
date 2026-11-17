"""
Five-moment selection engine.

Not random: candidates are ranked by their measured interest score, then picked
greedily under hard constraints —

  * rights        only sources with a VERIFIED reusable license
  * topic         one category per countdown
  * diversity     >= `min_sources` distinct source FAMILIES (re-uploads of one
                  video are one family), <= 2 moments per family
  * no reuse      a moment used by any live concept is never picked again
  * near-dupes    perceptual-hash distance to every chosen AND every previously
                  used moment must exceed `dup_threshold`
  * no combo reuse  the sorted segment-id set is UNIQUE in the concepts table

A seeded jitter only breaks ties between similar scores so repeated runs explore
different, still-strong combinations. The countdown order is ascending interest:
the strongest moment is #1. Every concept starts `pending_approval`.
"""
from __future__ import annotations

import json
import random

from . import commentary, probe
from .db import CATEGORIES, eligible_source_sql, row_dict

INTRO_S = 1.2           # hook teaser
OUTRO_S = 1.6           # end card
MAX_PER_SOURCE = 2


class SelectionError(RuntimeError):
    pass


def _candidates(con, category: str) -> list[dict]:
    where, args = eligible_source_sql()
    rows = con.execute(
        f"""SELECT g.*, s.path, s.attribution, s.license, s.has_audio, s.kind,
                   s.content_crop, s.title AS src_title, s.origin_url,
                   COALESCE(NULLIF(g.category,''), s.category) AS cat
            FROM segments g JOIN sources s ON s.id = g.source_id
            WHERE {where} AND g.disabled = 0
              AND COALESCE(NULLIF(g.category,''), s.category) = ?
              AND g.id NOT IN (SELECT u.segment_id FROM segment_usage u
                               JOIN concepts c ON c.id = u.concept_id
                               WHERE c.status != 'rejected')""",
        (*args, category)).fetchall()
    return [dict(r) for r in rows]


RANK_PRIOR = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2}


def merit(c: dict) -> float:
    """Measured interest, blended with the source editor's own ranking when the
    clip came out of a Top-5 compilation (their #1 is a strong prior)."""
    if c.get("source_rank") in RANK_PRIOR:
        return round(0.6 * c["score"] + 0.4 * RANK_PRIOR[c["source_rank"]], 4)
    return c["score"]


FOOTAGE_THRESHOLD = 14


def same_footage(a: dict, b: dict) -> bool:
    """Two clips from DIFFERENT compilations that show the same original video:
    a recorded origin or moment annotation matches, or their picture signatures
    come within FOOTAGE_THRESHOLD (different footage measured >= 16)."""
    sa, sb = json.loads(a.get("signals") or "{}"), json.loads(b.get("signals") or "{}")
    if sa.get("origin") and sa.get("origin") == sb.get("origin"):
        return True
    la, lb = (a.get("label") or "").strip().lower(), (b.get("label") or "").strip().lower()
    if la and la == lb:
        return True
    if sa.get("fsig") and sb.get("fsig"):
        return probe.min_pair_distance(sa["fsig"], sb["fsig"]) <= FOOTAGE_THRESHOLD
    return False


def _cap(c: dict) -> int:
    """Clips cut from a ranking compilation: one per source video, so a new
    countdown never just re-orders one creator's list."""
    return 1 if c.get("kind") == "compilation" else MAX_PER_SOURCE


def _used_hashes(con) -> list[str]:
    rows = con.execute(
        """SELECT g.phash FROM segments g JOIN segment_usage u ON u.segment_id = g.id
           JOIN concepts c ON c.id = u.concept_id WHERE c.status != 'rejected'""")
    return [r[0] for r in rows if r[0]]


def source_families(con, threshold: int = 10) -> dict[int, int]:
    """Map source id → family id. Two files are one family (a re-upload,
    re-encode or resize) when durations match within 1 s and most of their
    moments are perceptual near-duplicates — so diversity can't be faked by
    cataloguing the same video twice."""
    srcs = [dict(r) for r in con.execute("SELECT id, sha256, duration FROM sources ORDER BY id")]
    hashes = {s["id"]: [r[0] for r in con.execute(
        "SELECT phash FROM segments WHERE source_id=? AND phash != ''", (s["id"],))]
        for s in srcs}
    fam = {s["id"]: s["id"] for s in srcs}
    for i, a in enumerate(srcs):
        for b in srcs[:i]:
            if fam[b["id"]] != b["id"]:
                continue
            same = a["sha256"] == b["sha256"]
            if not same and abs((a["duration"] or 0) - (b["duration"] or 0)) <= 1.0:
                ha, hb = hashes[a["id"]], hashes[b["id"]]
                hits = sum(any(probe.hash_distance(x, y) <= threshold for y in hb) for x in ha)
                same = bool(ha) and hits / len(ha) >= 0.6
            if same:
                fam[a["id"]] = b["id"]
                break
    return fam


def category_stock(con) -> dict[str, int]:
    return {c: len(_candidates(con, c)) for c in CATEGORIES}


def _fit_durations(picks: list[dict], min_total: float, max_total: float) -> list[dict]:
    """Trim clips proportionally (from the START, keeping the payoff) to fit."""
    body_max = max_total - INTRO_S - OUTRO_S
    total = sum(p["end"] - p["start"] for p in picks)
    if total + INTRO_S + OUTRO_S < min_total:
        raise SelectionError(f"only {total:.1f}s of footage; need "
                             f"{min_total - INTRO_S - OUTRO_S:.1f}s")
    scale = min(1.0, body_max / total)
    out = []
    for p in picks:
        length = max(2.0, (p["end"] - p["start"]) * scale)
        out.append({**p, "in": round(p["end"] - length, 2), "out": p["end"]})
    return out


def select(con, channel: str, *, category: str | None = None, seed: int = 0,
           min_sources: int = 3, dup_threshold: int = 10,
           min_total: float = 20.0, max_total: float = 45.0,
           attempts: int = 25, writer: str = "template") -> dict:
    if category is None:
        stock = category_stock(con)
        category = max(stock, key=stock.get)
    if category not in CATEGORIES:
        raise SelectionError(f"unknown category {category!r}")
    cands = _candidates(con, category)
    for c in cands:
        c["merit"] = merit(c)
    if len(cands) < 5:
        raise SelectionError(f"{category}: {len(cands)} eligible rights-verified "
                             "moments, need 5")
    used = _used_hashes(con)
    used_rows = [dict(r) for r in con.execute(
        """SELECT g.label, g.signals FROM segments g JOIN segment_usage u ON u.segment_id = g.id
           JOIN concepts c ON c.id = u.concept_id WHERE c.status != 'rejected'""")]
    taken = {r[0] for r in con.execute("SELECT combo_key FROM concepts")}
    family = source_families(con, dup_threshold)
    rng = random.Random(seed)

    for _ in range(attempts):
        order = sorted(cands, key=lambda c: -(c["merit"] + rng.uniform(0, 0.15)))
        picks: list[dict] = []
        per_src: dict[int, int] = {}
        for c in order:
            fid = family.get(c["source_id"], c["source_id"])
            if per_src.get(fid, 0) >= _cap(c):
                continue
            if any(probe.hash_distance(c["phash"], h) <= dup_threshold
                   for h in used + [p["phash"] for p in picks]):
                continue
            if any(same_footage(c, p) for p in picks + used_rows):
                continue
            picks.append(c)
            per_src[fid] = per_src.get(fid, 0) + 1
            if len(picks) == 5:
                break
        if len(picks) < 5 or len(per_src) < min_sources:
            continue
        key = ",".join(str(i) for i in sorted(p["id"] for p in picks))
        if key in taken:
            continue
        return _create(con, channel, category, picks, key, seed, min_total, max_total,
                       writer)
    raise SelectionError(
        f"{category}: no new 5-moment combination from >= {min_sources} sources "
        "passes the duplicate/reuse rules — add more licensed footage")


def _create(con, channel, category, picks, key, seed, min_total, max_total,
            writer="template") -> dict:
    from . import topic
    ranked = sorted(picks, key=lambda p: p["merit"])          # weakest first = #5
    ranked = _fit_durations(ranked, min_total, max_total)
    for p in ranked:
        p["subject"] = topic.subject(p["label"] or "", p.get("src_title") or "",
                                     p.get("origin_url") or "")
    copy = commentary.concept_copy(channel, category, seed,
                                   subjects={r: p["subject"] for r, p in zip((5, 4, 3, 2, 1), ranked)},
                                   labels={r: p["label"] for r, p in zip((5, 4, 3, 2, 1), ranked)},
                                   writer=writer)
    ranks = []
    for rank, p in zip((5, 4, 3, 2, 1), ranked):
        signals = json.loads(p.get("signals") or "{}")
        ranks.append({"rank": rank, "segment_id": p["id"], "source_id": p["source_id"],
                      "path": p["path"], "in": p["in"], "out": p["out"],
                      "has_audio": bool(p["has_audio"]), "score": p["merit"],
                      "interest": p["score"], "source_rank": p.get("source_rank"),
                      "caption": copy["captions"][rank], "label": p["label"],
                      "subject": p["subject"], "kind": p.get("kind", "clip"),
                      "crop": p.get("content_crop") or "",
                      "overlay_box": signals.get("overlay_box"),
                      "license": p["license"], "attribution": p["attribution"]})
    body = sum(r["out"] - r["in"] for r in ranks)
    payload = {"copy": copy, "ranks": ranks, "intro_s": INTRO_S, "outro_s": OUTRO_S,
               "est_duration": round(body + INTRO_S + OUTRO_S, 2), "seed": seed,
               "treatment": commentary.treatment(channel, seed)}
    cur = con.execute(
        "INSERT INTO concepts (channel, title, category, combo_key, payload) VALUES (?,?,?,?,?)",
        (channel, copy["title"], category, key, json.dumps(payload)))
    cid = cur.lastrowid
    con.executemany("INSERT INTO segment_usage (segment_id, concept_id) VALUES (?,?)",
                    [(r["segment_id"], cid) for r in ranks])
    commentary.record_copy(channel, category, copy)
    return get(con, cid)


def get(con, concept_id: int) -> dict:
    c = row_dict(con.execute("SELECT * FROM concepts WHERE id=?", (concept_id,)).fetchone())
    if c is None:
        raise KeyError(f"concept {concept_id} not found")
    return c


def update_payload(con, concept_id: int, payload: dict) -> dict:
    """Human edit of captions/title/order. Editing an approved concept resets
    it to pending — approval covers exactly what was reviewed."""
    c = get(con, concept_id)
    if sorted(r["segment_id"] for r in payload["ranks"]) != \
            sorted(r["segment_id"] for r in c["payload"]["ranks"]):
        raise ValueError("segments can't be swapped by editing; reject and re-select")
    con.execute("UPDATE concepts SET payload=?, title=?, status='pending_approval', "
                "approved_by='' WHERE id=?",
                (json.dumps(payload), payload["copy"]["title"], concept_id))
    return get(con, concept_id)


def approve(con, concept_id: int, reviewer: str) -> dict:
    if not reviewer.strip():
        raise ValueError("approval needs a reviewer name")
    c = get(con, concept_id)
    if c["status"] == "rejected":
        raise ValueError("concept was rejected")
    where, args = eligible_source_sql()
    ids = [r["source_id"] for r in c["payload"]["ranks"]]
    ok = con.execute(f"SELECT COUNT(*) FROM sources s WHERE s.id IN "
                     f"({','.join('?' * len(ids))}) AND {where}", (*ids, *args)).fetchone()[0]
    if ok != len(set(ids)):
        raise ValueError("a source lost its verified license; cannot approve")
    con.execute("UPDATE concepts SET status='approved', approved_by=? WHERE id=?",
                (reviewer, concept_id))
    return get(con, concept_id)


def reject(con, concept_id: int) -> None:
    """Frees the moments for reuse; the combo key stays burned."""
    con.execute("UPDATE concepts SET status='rejected' WHERE id=?", (concept_id,))
