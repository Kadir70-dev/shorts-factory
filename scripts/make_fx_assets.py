#!/usr/bin/env python3
"""
Procedural FX asset generator (Phase 3) — the loopable foreground textures the
layer compositor screen-blends on top of the hero stack.

CPU-only, no dependencies, idempotent: each asset is a SINGLE 1080x1920 PNG made
with one ffmpeg lavfi call, so it's cheap to (re)generate and the compositor just
loops it. Screen blend uses brightness, so monochrome textures are all we need.

    .venv/bin/python scripts/make_fx_assets.py            # generate any missing
    .venv/bin/python scripts/make_fx_assets.py --force    # regenerate all

Files land in data/assets/fx/ and match the names the Storyboard Agent's _FX
palette references (grain.png, scanlines.png, glow.png).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX_DIR = ROOT / "data" / "assets" / "fx"
W, H = 1080, 1920

# name → ffmpeg -vf filter producing one monochrome frame on a black canvas.
_ASSETS: dict[str, str] = {
    # fine film grain — subtle texture, reads as celluloid under screen blend.
    "grain.png": "geq=lum='random(1)*90':cb=128:cr=128",
    # faint horizontal scanlines (every 4px) — retro/anime/cyber HUD vibe.
    "scanlines.png": "geq=lum='if(lt(mod(Y\\,4)\\,1)\\,70\\,0)':cb=128:cr=128",
    # soft centered glow — gentle vignette lift on the hero, brightest at center.
    "glow.png": ("geq=lum='130*exp(-((X-540)*(X-540)+(Y-960)*(Y-960))/"
                 "900000)':cb=128:cr=128"),
}


def _make(name: str, vf: str, force: bool) -> str:
    out = FX_DIR / name
    if out.exists() and out.stat().st_size > 0 and not force:
        return f"· {name} (exists, {out.stat().st_size // 1024}KB)"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=black:s={W}x{H}",
           "-vf", vf, "-frames:v", "1", "-y", str(out)]
    r = subprocess.run(cmd, stderr=subprocess.PIPE)
    if r.returncode != 0:
        return f"✗ {name} FAILED: {r.stderr.decode()[:160]}"
    return f"✓ {name} ({out.stat().st_size // 1024}KB)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate even if present")
    args = ap.parse_args()
    FX_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fx] generating into {FX_DIR}")
    ok = True
    for name, vf in _ASSETS.items():
        line = _make(name, vf, args.force)
        print("   ", line)
        ok = ok and not line.startswith("✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
