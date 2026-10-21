#!/usr/bin/env python3
"""K70 P3 semantic documentary edit planning; never changes a source SceneGraph.

Examples:
  python3 scripts/k70_p3_editor.py --graph data/series/bitcoin_history/ep01/scene_graph.json --out-dir data/finance_p3/bitcoin_editor_review_v1
  python3 scripts/k70_p3_editor.py --graph NEW_UNRENDERED_GRAPH.json --out-dir data/finance_p3/new_episode_v1 --apply-transitions-to-copy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.k70_scene_engine.intelligent_editor import (
    plan_documentary, review_markdown, safe_transition_copy,
)


def _json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="K70 P3 whole-film editorial planning and safe QA")
    parser.add_argument("--graph", type=Path, required=True, help="existing SceneGraph JSON, read-only")
    parser.add_argument("--out-dir", type=Path, required=True, help="new directory for output reports")
    parser.add_argument("--apply-transitions-to-copy", action="store_true",
                        help="opt in on unrendered graph; creates NEW copy with safe cuts + sourced charts")
    args = parser.parse_args()
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        report = plan_documentary(graph)
        outputs = {
            "editorial_plan.json": _json(report),
            "editorial_review.md": review_markdown(report),
        }
        if args.apply_transitions_to_copy:
            safe_copy = safe_transition_copy(graph, report)
            outputs["scene_graph_editorial_copy.json"] = _json(safe_copy)
        directory = args.out_dir.expanduser().resolve()
        source = args.graph.expanduser().resolve()
        targets = [directory / name for name in outputs]
        if any(target == source for target in targets):
            raise ValueError("source SceneGraph may never be overwritten")
        if any(target.exists() for target in targets):
            raise FileExistsError("output exists; use a fresh --out-dir")
        directory.mkdir(parents=True, exist_ok=True)
        for name, contents in outputs.items():
            with (directory / name).open("x", encoding="utf-8") as handle:
                handle.write(contents)
        print(f"EDITOR REPORT: {directory}")
        print(f"SCENES: {report['scene_count']} · REVIEW ISSUES: {len(report['review_issues'])}")
        if args.apply_transitions_to_copy:
            print("COPY ONLY: safe transition/chart decisions; no video rendered or original data modified.")
        else:
            print("READ-ONLY: visual and transition proposals, no graph edits.")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
