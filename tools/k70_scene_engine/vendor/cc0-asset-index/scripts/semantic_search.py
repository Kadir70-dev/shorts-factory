#!/usr/bin/env python3
"""semantic_search.py — vibe/similarity search over asset descriptions.

Two modes (same embeddings on disk):
  embed  : build data/embeddings.npz from data/assets.jsonl   (run once, re-run after reindex)
  search : find nearest assets to a free-text query           (fast, no re-embedding)

Optional-dependency layer: requires numpy + onnxruntime + a local MiniLM ONNX model.
The core CLI (cc0a) stays stdlib-only; this script fails with a clear setup message
if deps are missing.

Setup (one time):
  pip install numpy onnxruntime huggingface_hub
  huggingface-cli download Xenova/all-MiniLM-L6-v2 onnx/model_quantized.onnx \\
      --local-dir ~/.cache/cc0-asset-index/minilm

Usage:
  python3 scripts/semantic_search.py embed
  python3 scripts/semantic_search.py search "cozy medieval tavern interior" [--limit 10] [--kind kit]
  python3 scripts/semantic_search.py search --image caption.txt     # BLIP/CLIP caption from any tool
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EMB_PATH = os.path.join(DATA, "embeddings.npz")
MODEL_DIR = os.path.expanduser("~/.cache/cc0-asset-index/minilm")
MODEL_FILE = os.path.join(MODEL_DIR, "onnx", "model_quantized.onnx")

SETUP_MSG = f"""semantic search needs one-time setup:
  pip install numpy onnxruntime huggingface_hub
  huggingface-cli download Xenova/all-MiniLM-L6-v2 onnx/model_quantized.onnx --local-dir {MODEL_DIR}
model file expected at: {MODEL_FILE}"""


def _deps():
    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError:
        sys.exit("missing deps.\n" + SETUP_MSG)
    if not os.path.exists(MODEL_FILE):
        sys.exit("model not found.\n" + SETUP_MSG)
    return np, ort


def _tokenize(texts):
    """Minimal WordPiece tokenizer for MiniLM (vocab from the model dir)."""
    import re as _re
    vocab = {}
    with open(os.path.join(MODEL_DIR, "vocab.txt")) as f:
        for i, line in enumerate(f):
            vocab[line.strip()] = i
    out_ids, out_mask = [], []
    for text in texts:
        tokens = ["[CLS]"]
        for word in _re.findall(r"[a-z0-9]+|[^\sa-z0-9]", text.lower()):
            if word in vocab:
                tokens.append(word)
            else:
                # greedy longest-match subword split
                start = 0
                while start < len(word):
                    end = len(word)
                    cur = None
                    while end > start:
                        sub = word[start:end] if start == 0 else "##" + word[start:end]
                        if sub in vocab:
                            cur = sub
                            break
                        end -= 1
                    if cur is None:
                        tokens.append("[UNK]")
                        break
                    tokens.append(cur)
                    start = end
        tokens.append("[SEP]")
        ids = [vocab.get(t, vocab["[UNK]"]) for t in tokens][:128]
        mask = [1] * len(ids)
        while len(ids) < 128:
            ids.append(0)
            mask.append(0)
        out_ids.append(ids)
        out_mask.append(mask)
    return out_ids, out_mask


def _embed(texts, batch=32):
    np, ort = _deps()
    sess = ort.InferenceSession(MODEL_FILE, providers=["CPUExecutionProvider"])
    vecs = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        ids, mask = _tokenize(chunk)
        inputs = {
            "input_ids": np.array(ids, dtype=np.int64),
            "attention_mask": np.array(mask, dtype=np.int64),
            "token_type_ids": np.zeros((len(chunk), 128), dtype=np.int64),
        }
        hidden = sess.run(None, inputs)[0]  # (B, T, H)
        m = np.array(mask, dtype=np.float32)[..., None]
        pooled = (hidden * m).sum(axis=1) / m.sum(axis=1).clip(min=1e-9)  # mean pool
        pooled = pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
        vecs.append(pooled)
    return np.vstack(vecs)


def _load_records():
    with open(os.path.join(DATA, "assets.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def cmd_embed(_args):
    np, _ = _deps()
    records = _load_records()
    texts = [f"{r['name']}. {' '.join(r['tags'])}. {r['description']}" for r in records]
    print(f"embedding {len(texts)} records...", file=sys.stderr)
    vecs = _embed(texts)
    np.savez_compressed(EMB_PATH, ids=[r["id"] for r in records], vecs=vecs)
    print(f"-> {EMB_PATH} ({os.path.getsize(EMB_PATH) / 1e6:.1f} MB)", file=sys.stderr)


def cmd_search(args):
    np, _ = _deps()
    if not os.path.exists(EMB_PATH):
        sys.exit("no embeddings. run: python3 scripts/semantic_search.py embed")
    z = np.load(EMB_PATH, allow_pickle=True)
    ids, vecs = z["ids"], z["vecs"]
    if args.image:
        query = open(args.image).read().strip()
        print(f"(image caption mode: '{query[:80]}...')" if len(query) > 80 else f"(image caption mode: '{query}')", file=sys.stderr)
    else:
        query = " ".join(args.query)
    q = _embed([query])[0]
    sims = vecs @ q
    records = {r["id"]: r for r in _load_records()}
    order = sims.argsort()[::-1]
    shown = 0
    for idx in order:
        rid = str(ids[idx])
        r = records.get(rid)
        if not r:
            continue
        if r.get("grade") == "archive" and not args.all:
            continue
        if args.kind and r["kind"] != args.kind:
            continue
        print(f"{sims[idx]:.3f}  {rid:45} [{r['kind']:8}] {r['name']}")
        shown += 1
        if shown >= args.limit:
            break


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("embed")
    p = sub.add_parser("search")
    p.add_argument("query", nargs="*")
    p.add_argument("--image", help="path to a text file containing an image caption (from BLIP/CLIP/any VLM)")
    p.add_argument("--kind", choices=["kit", "model", "hdri", "material", "scene"])
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.cmd == "search" and not args.image and not args.query:
        ap.error("search needs a query or --image caption file")
    {"embed": cmd_embed, "search": cmd_search}[args.cmd](args)


if __name__ == "__main__":
    main()
