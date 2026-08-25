#!/usr/bin/env python3
"""validate.py — CI guardrail for cc0-asset-index.

Checks:
  1. Every record in data/assets.jsonl (or a given file) matches schema.json required fields + enums.
  2. license is exactly "CC0" and attribution_required is false — no exceptions, ever.
  3. id format is <provider>:<slug> and ids are unique.
  4. If grade is present, grade_reason is present (and vice versa).
  5. If provenance is present, original_id + enhanced_with are present.
  6. AI-generated records (generated_by present) are flagged for human review in CI output
     (they still must be CC0 — this is a review hint, not a rejection).

Exit 0 = pass, 1 = violations found. Stdlib only.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = json.load(open(os.path.join(ROOT, "schema.json")))
REQUIRED = SCHEMA["required"]
ALLOWED_LICENSE = {"CC0"}
KINDS = {"kit", "model", "hdri", "material", "scene"}
ENGINES = {"blender", "godot", "unreal"}
GRADES = {"gold", "silver", "bronze", "archive"}
ID_RE = re.compile(r"^[a-z0-9_]+:.+$")


def validate_record(r, lineno):
    errs = []
    for field in REQUIRED:
        if field not in r:
            errs.append(f"missing required field '{field}'")
    if errs:
        return errs  # don't cascade on broken records
    if r["license"] not in ALLOWED_LICENSE:
        errs.append(f"license must be CC0, got {r['license']!r}")
    if r["attribution_required"] is not False:
        errs.append("attribution_required must be false")
    if r["kind"] not in KINDS:
        errs.append(f"unknown kind {r['kind']!r}")
    if not ID_RE.match(r["id"]):
        errs.append(f"bad id format {r['id']!r}")
    bad_engines = set(r["engine_targets"]) - ENGINES
    if bad_engines:
        errs.append(f"unknown engine_targets {bad_engines}")
    if not isinstance(r["tags"], list) or not isinstance(r["formats"], list):
        errs.append("tags and formats must be arrays")
    if not r["description"].strip():
        errs.append("description must be non-empty")
    if "grade" in r:
        if r["grade"] not in GRADES:
            errs.append(f"unknown grade {r['grade']!r}")
        if not r.get("grade_reason"):
            errs.append("grade present but grade_reason missing")
    if "grade_reason" in r and "grade" not in r:
        errs.append("grade_reason present but grade missing")
    if "provenance" in r:
        p = r["provenance"]
        for f in ("original_id", "enhanced_with"):
            if f not in p:
                errs.append(f"provenance missing '{f}'")
    return errs


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "assets.jsonl")
    records = [json.loads(l) for l in open(path) if l.strip()]
    seen = {}
    violations = 0
    ai_flagged = 0
    for i, r in enumerate(records, 1):
        errs = validate_record(r, i)
        rid = r.get("id", f"line {i}")
        if rid in seen:
            errs.append(f"duplicate id (first seen line {seen[rid]})")
        seen[rid] = i
        if r.get("generated_by"):
            ai_flagged += 1
            print(f"REVIEW: {rid} is AI-generated ({r['generated_by']}) — confirm model dedicates outputs CC0", file=sys.stderr)
        for e in errs:
            violations += 1
            print(f"FAIL line {i} ({rid}): {e}", file=sys.stderr)
    print(f"validated {len(records)} records: {violations} violation(s), {ai_flagged} AI-generated flagged for review")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
