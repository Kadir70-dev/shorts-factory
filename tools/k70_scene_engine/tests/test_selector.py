"""Validates visual_mode.selector against the brief's OWN worked examples
(section 10) and the John/Sarah storytelling examples (section 6). Run:

    .venv-win/Scripts/python.exe -m tools.k70_scene_engine.tests.test_selector
"""
from __future__ import annotations

from ..visual_mode.modes import VisualMode
from ..visual_mode.selector import classify, SequencePlanner

CASES = [
    ("Millions of Americans use credit cards every day.", VisualMode.REAL_STOCK),
    ("John owes $5,000 at 24% APR.", VisualMode.THREE_D_CHARACTER),
    ("The Federal Reserve raises rates.", VisualMode.MOTION_GRAPHIC),
    ("EUR/USD drops.", VisualMode.DATA_CHART),
]


def run() -> bool:
    ok = True
    for text, expected in CASES:
        got = classify(text).mode
        status = "PASS" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"[{status}] {text!r} -> {got.value} (expected {expected.value})")

    print("\n--- section 6 sequence-continuity example ---")
    planner = SequencePlanner()
    story = [
        "John has $10,000.",
        "He walks into a bank.",
        "He deposits the money.",
        "Ten years later, his investment has grown.",
        "Meanwhile, EUR/USD drops sharply.",
    ]
    for line in story:
        d = planner.decide(line)
        print(f"  {line!r} -> {d.mode.value}  ({d.reason})")

    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
