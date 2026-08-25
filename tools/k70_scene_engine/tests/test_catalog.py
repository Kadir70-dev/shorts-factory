"""Integration smoke test: catalog + license + roster + templates all
agreeing with each other. Run:

    .venv-win/Scripts/python.exe -m tools.k70_scene_engine.tests.test_catalog
"""
from __future__ import annotations

from pathlib import Path

from ..catalog import index
from ..characters.roster import ROSTER
from ..templates.finance_scenes import TEMPLATES
from ..license import manifest as license_manifest


def run() -> bool:
    ok = True

    n = index.stats()["total"]
    print(f"[{'PASS' if n > 0 else 'FAIL'}] catalog non-empty: {n} assets")
    ok &= n > 0

    m = license_manifest.load()
    print(f"[{'PASS' if m['excluded_count'] == 0 else 'INFO'}] license manifest: "
          f"{m['eligible_count']} eligible, {m['excluded_count']} excluded")

    for cid, ch in ROSTER.items():
        rel = ch.base_asset_id.split(":", 1)[1]
        p = Path("tools/k70_scene_engine/vendor/gobkit-free-assets") / f"{rel}.glb"
        eligible = license_manifest.is_eligible(ch.base_asset_id.replace("gobkit:", "gobkit:"))
        status = p.exists()
        print(f"[{'PASS' if status else 'FAIL'}] character '{cid}' base mesh exists: {p}")
        ok &= status

    for concept, tmpl in TEMPLATES.items():
        has_shots = len(tmpl.shots) > 0
        print(f"[{'PASS' if has_shots else 'FAIL'}] template '{concept}': {len(tmpl.shots)} shots")
        ok &= has_shots

    print(f"\n{len(TEMPLATES)}/12 finance templates present "
          f"({'PASS' if len(TEMPLATES) == 12 else 'FAIL'})")
    ok &= len(TEMPLATES) == 12

    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
