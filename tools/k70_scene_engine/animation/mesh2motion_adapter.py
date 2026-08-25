from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "vendor" / "mesh2motion-app"
HUMAN_BASE = APP / "static" / "animations" / "human-base-animations.glb"


def status() -> dict:
    commit = subprocess.run(["git", "-C", str(APP), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    return {"installed": APP.exists(), "offline_build": (APP / "dist/index.html").exists(),
            "commit": commit or "UNKNOWN", "human_base": str(HUMAN_BASE),
            "code_license": "MIT", "asset_license": "CC0",
            "normal_runtime_dependency": False}
