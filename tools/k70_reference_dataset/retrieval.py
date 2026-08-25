"""Read-only reference retrieval for K70 Visual Director experiments."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from .pipeline import DEFAULT_ROOT, _load_clip, _normal


def _query_text(spec: dict) -> str:
    fields = [spec.get(k) for k in ("environment", "shot_type", "time_of_day", "hero_action", "mood")]
    return "premium cinematic block-world reference, " + ", ".join(str(v).replace("_", " ") for v in fields if v)


def retrieve_references(shot_spec: dict, top_k: int = 10, *, root: Path = DEFAULT_ROOT) -> list[dict]:
    """Return diverse, semantically relevant references without mutating K70."""
    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")
    db = sqlite3.connect(root / "dataset.sqlite"); db.row_factory = sqlite3.Row
    rows = db.execute("""SELECT c.id,c.local_path,c.title,c.creator,c.license,c.source_page_url,
      i.final_score,i.tags,e.vector,e.dim FROM candidates c JOIN images i ON i.candidate_id=c.id
      JOIN embeddings e ON e.candidate_id=c.id WHERE c.stage='SELECTED'""").fetchall()
    if not rows:
        db.close(); return []
    torch, model, processor, _ = _load_clip()
    with torch.no_grad():
        inp = processor(text=[_query_text(shot_spec)], return_tensors="pt", padding=True, truncation=True)
        query = _normal(model.get_text_features(**inp)).cpu().numpy()[0]
    ranked = []
    for row in rows:
        vec = np.frombuffer(row["vector"], dtype=np.float32, count=row["dim"])
        semantic = float(np.dot(query, vec))
        ranked.append((0.8 * semantic + 0.2 * (row["final_score"] or 0) / 100.0, row, vec))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected, selected_vecs = [], []
    for score, row, vec in ranked:
        if selected_vecs and max(float(np.dot(vec, old)) for old in selected_vecs) >= 0.95:
            continue
        selected.append({"id": row["id"], "local_path": str(root / row["local_path"]),
                         "title": row["title"], "creator": row["creator"], "license": row["license"],
                         "source_page_url": row["source_page_url"], "tags": json.loads(row["tags"] or "{}"),
                         "retrieval_score": round(score, 5)})
        selected_vecs.append(vec)
        if len(selected) == top_k:
            break
    db.close(); return selected
