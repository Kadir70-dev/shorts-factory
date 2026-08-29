#!/usr/bin/env python3
"""K70-PRODUCTION-v1.0 architecture drift validator (repo-tracked mirror).

This is the version-controlled reference copy of the validator that lives
alongside the live freeze package at
data/jobs/k70_national_debt_ep01/architecture_freeze/check_architecture_drift.py
(that directory is under data/jobs/, which is .gitignore'd for this repo like
every other job's run artifacts, so it is not committed). Run the LOCAL copy
for real drift checks -- it is the one BASELINE_HASHES.json and the render
pipeline actually stay in sync with. This tracked copy exists so the freeze's
logic and intent are part of repo history and reviewable in a PR.

Lightweight by default: checks file existence + size/mtime for protected
masters (fast), and full SHA256 for critical scripts/manifests (small files,
fast). Pass --full to also SHA256 the protected masters (slower -- ~700MB of
video, only needed for a deep pre-release check).

Protects the ENGINE (layer count, dependency definitions, critical scripts,
the architecture lock itself, and the deprecated caption pipeline never
silently returning). Does NOT fail on episode-specific content changes
(new footage, new chart data, new narration, new Pika clips *within* an
existing layer) -- those are expected and out of scope for this check.

Exit code 0 = no drift. Exit code 1 = drift detected (see printed report).
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
JOB = REPO_ROOT / "data/jobs/k70_national_debt_ep01"
FREEZE = JOB / "architecture_freeze"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def base_for(section: str) -> Path:
    return {
        "critical_scripts": REPO_ROOT,
        "job_local_scripts": JOB,
        "critical_manifests": JOB,
        "protected_masters": JOB,
        "freeze_docs": FREEZE,
    }[section]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                     help="also SHA256 protected masters (slow, ~700MB read)")
    args = ap.parse_args()

    problems = []
    lock_path = FREEZE / "ARCHITECTURE_LOCK.json"
    layers_path = FREEZE / "WORKING_LAYERS.json"
    baseline_path = FREEZE / "BASELINE_HASHES.json"

    for req in (lock_path, layers_path, baseline_path):
        if not req.exists():
            problems.append(f"MISSING FREEZE FILE: {req.name} (expected under the local, "
                             f"gitignored data/jobs/k70_national_debt_ep01/architecture_freeze/)")
    if problems:
        print("\n".join(problems))
        print(f"\nDRIFT CHECK: FAIL ({len(problems)} problem(s))")
        sys.exit(1)

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    layers = json.loads(layers_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    n_now = len(layers.get("layers", []))
    n_locked = lock.get("discovered_working_layer_count")
    if n_now != n_locked:
        problems.append(f"LAYER COUNT CHANGED: locked={n_locked} current={n_now}")

    if lock.get("status") != "FROZEN":
        problems.append(f"ARCHITECTURE_LOCK status is not FROZEN (found: {lock.get('status')!r})")

    for section in ("critical_scripts", "job_local_scripts", "critical_manifests", "freeze_docs"):
        base = base_for(section)
        for rel, rec in baseline.get(section, {}).items():
            p = base / rel
            if not p.exists():
                problems.append(f"MISSING LOCKED FILE [{section}]: {rel}")
                continue
            actual = sha256(p)
            if actual != rec["sha256"]:
                problems.append(f"MODIFIED LOCKED FILE [{section}]: {rel} "
                                 f"(expected {rec['sha256'][:12]}..., got {actual[:12]}...)")

    for rel, rec in baseline.get("protected_masters", {}).items():
        p = JOB / rel
        if not p.exists():
            problems.append(f"MISSING PROTECTED MASTER: {rel}")
            continue
        size = p.stat().st_size
        if size != rec["size"]:
            problems.append(f"PROTECTED MASTER SIZE CHANGED (overwritten?): {rel} "
                             f"(expected {rec['size']}, got {size})")
        elif args.full:
            actual = sha256(p)
            if actual != rec["sha256"]:
                problems.append(f"PROTECTED MASTER HASH CHANGED: {rel}")

    dep = layers.get("deprecated_components", [])
    old_caps = next((d for d in dep if d["name"] == "OLD_SELECTIVE_CAPTIONS"), None)
    if old_caps is None:
        problems.append("OLD_SELECTIVE_CAPTIONS entry missing from deprecated_components")
    elif old_caps.get("status") != "DEPRECATED / FORBIDDEN":
        problems.append(f"OLD_SELECTIVE_CAPTIONS status changed: {old_caps.get('status')!r}")

    if problems:
        print("\n".join(problems))
        print(f"\nDRIFT CHECK: FAIL ({len(problems)} problem(s))")
        sys.exit(1)

    print(f"DRIFT CHECK: PASS -- {n_now} layers locked, all critical files match baseline"
          + (" (full master hash verified)" if args.full else " (masters: size-checked only, use --full for hash)"))
    sys.exit(0)


if __name__ == "__main__":
    main()
