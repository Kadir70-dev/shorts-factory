#!/usr/bin/env python3
"""K70 P1 narration planning and read-only editorial audit (stdlib only).

Planning:
 python3 scripts/k70_p1_storytelling.py plan \
   --topic "The end of the gold standard" --minutes 11 \
   --sources data/research/finance_sources.json \
   --out-dir data/finance_p1/gold_standard_plan

Editorial audit, no rewriting:
 python3 scripts/k70_p1_storytelling.py audit \
   --graph data/series/bitcoin_history/ep01/scene_graph.json \
   --out-dir data/finance_p1/bitcoin_ep01_audit
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.storytelling import (
    audit_graph, build_plan, write_audit_brief, write_director_brief,
)
from tools.k70_scene_engine.story_draft import draft_prompt, local_claude, review_draft


def _json_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("--sources must contain a JSON array of source objects")
    return data


def _write_outputs(directory: Path, outputs: dict[str, str]) -> None:
    dest = directory.expanduser().resolve()
    # Never overwrite a previous editorial plan or review.
    for filename in outputs:
        if (dest / filename).exists():
            raise FileExistsError(f"output exists; choose a fresh --out-dir: {dest / filename}")
    dest.mkdir(parents=True, exist_ok=True)
    for filename, text in outputs.items():
        # exclusive creation: existing file cannot be replaced even in a race
        with (dest / filename).open("x", encoding="utf-8") as f:
            f.write(text)
    print(f"P1 output: {dest}")
    for name in outputs:
        print(f"  {dest / name}")


def run_plan(args: argparse.Namespace) -> None:
    sources = _json_list(args.sources) if args.sources else []
    plan = build_plan(args.topic, duration_sec=args.minutes * 60,
                      sources=sources, audience=args.audience)
    _write_outputs(args.out_dir, {
        "story_plan.json": json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        "director_story_brief.md": write_director_brief(plan),
    })
    if not sources:
        print("RESEARCH REQUIRED: no verified facts supplied; plan does not invent any.")


def run_audit(args: argparse.Namespace) -> None:
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if not isinstance(graph, dict):
        raise ValueError("SceneGraph file must contain a JSON object")
    report = audit_graph(graph)
    _write_outputs(args.out_dir, {
        "narrative_qa.json": json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        "narrative_editorial_review.md": write_audit_brief(report),
    })
    print(f"Questions={report['questions']}, analogies={report['analogy_signals']}, "
          f"roadmap={bool(report['roadmap_scene_ids'])}, "
          f"warnings={len(report['warnings'])}")



def _read_json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def run_draft(args: argparse.Namespace) -> None:
    """Default: write an offline source-scoped prompt. --generate invokes Claude."""
    plan = _read_json_object(args.plan)
    evidence = _read_json_object(args.evidence)
    prompt = draft_prompt(plan, evidence)
    outputs = {"chapter_draft_prompt.md": prompt}
    if args.generate:
        draft = local_claude(prompt, binary=args.claude_bin,
                             model=args.model, timeout=args.timeout_sec)
        review = review_draft(plan, evidence, draft)
        outputs["chapter_narration_draft.json"] = (
            json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
        outputs["chapter_narration_review.json"] = (
            json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        print("DRAFT GENERATED; NOT APPROVED FOR TTS. Review every source claim.")
    else:
        print("Prompt-only mode: no model or paid API called.")
    _write_outputs(args.out_dir, outputs)


def run_review(args: argparse.Namespace) -> None:
    plan = _read_json_object(args.plan)
    evidence = _read_json_object(args.evidence)
    draft = _read_json_object(args.draft)
    review = review_draft(plan, evidence, draft)
    _write_outputs(args.out_dir, {
        "chapter_narration_review.json": json.dumps(
            review, ensure_ascii=False, indent=2) + "\n",
    })
    print("Text/evidence heuristics only. Manual fact verification mandatory.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="K70 P1: preproduction finance storytelling; frozen 14 layers unchanged")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Generate original chapter plan + Claude writing brief")
    plan.add_argument("--topic", required=True)
    plan.add_argument("--minutes", type=float, default=11,
                      help="Editorial duration target; allowed 4..20 minutes")
    plan.add_argument("--audience", default="general US finance audience")
    plan.add_argument("--sources", type=Path,
                      help="Optional JSON array of {id,title,url,claim}; externally verify claims")
    plan.add_argument("--out-dir", type=Path, required=True)
    plan.set_defaults(fn=run_plan)
    audit = commands.add_parser("audit", help="Read-only narration review of existing SceneGraph")
    audit.add_argument("--graph", type=Path, required=True)
    audit.add_argument("--out-dir", type=Path, required=True)
    audit.set_defaults(fn=run_audit)
    draft = commands.add_parser(
        "draft", help="Create evidence-scoped narration prompt; local Claude opt-in")
    draft.add_argument("--plan", type=Path, required=True)
    draft.add_argument("--evidence", type=Path, required=True)
    draft.add_argument("--out-dir", type=Path, required=True)
    draft.add_argument("--generate", action="store_true",
                       help="Explicitly invoke local Claude CLI; never API fallback")
    draft.add_argument("--claude-bin", default="claude")
    draft.add_argument("--model", default="opus")
    draft.add_argument("--timeout-sec", type=int, default=360)
    draft.set_defaults(fn=run_draft)
    review = commands.add_parser("review", help="Validate a chapter script without model calls")
    review.add_argument("--plan", type=Path, required=True)
    review.add_argument("--evidence", type=Path, required=True)
    review.add_argument("--draft", type=Path, required=True)
    review.add_argument("--out-dir", type=Path, required=True)
    review.set_defaults(fn=run_review)
    args = parser.parse_args()
    try:
        args.fn(args)
    except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
