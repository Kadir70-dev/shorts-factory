"""Quality gates for K70 Scene Engine output (brief section 17).

Deliberately narrow: this checks the MECHANICAL failure modes a broken
render actually produces (empty file, uniform/black frame, degenerate
resolution) -- not aesthetic judgment, which still needs a human or the
existing `apps/api/app/pipeline/qa.py` frame-level pipeline QA for the
final composited video. `validate_still()` is meant to run right after
`bpy_bridge.render_still()` / `voxelizer.voxelize_and_render()`, before a
render is allowed into the timeline at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - PIL is already a project dependency
    Image = None


@dataclass
class QAResult:
    passed: bool
    checks: list[tuple[str, bool, str]]  # (name, passed, detail)

    def format(self) -> str:
        lines = [f"K70 Scene Engine QA: {'PASS' if self.passed else 'FAIL'}"]
        for name, ok, detail in self.checks:
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name} -- {detail}")
        return "\n".join(lines)


def validate_still(path: Path, *, min_width: int = 64, min_height: int = 64,
                   min_bytes: int = 1024, uniform_std_threshold: float = 1.5) -> QAResult:
    checks: list[tuple[str, bool, str]] = []

    exists = path.exists()
    checks.append(("file exists", exists, str(path)))
    if not exists:
        return QAResult(False, checks)

    size = path.stat().st_size
    ok = size >= min_bytes
    checks.append(("non-trivial file size", ok, f"{size} bytes (min {min_bytes})"))

    if Image is None:
        checks.append(("image readable", False, "PIL not available -- cannot inspect pixels"))
        return QAResult(all(c[1] for c in checks), checks)

    try:
        im = Image.open(path)
        im.load()
        w, h = im.size
        dims_ok = w >= min_width and h >= min_height
        checks.append(("resolution", dims_ok, f"{w}x{h} (min {min_width}x{min_height})"))

        gray = im.convert("L")
        hist = gray.histogram()
        total = sum(hist)
        mean = sum(i * c for i, c in enumerate(hist)) / total
        variance = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / total
        std = variance ** 0.5
        not_uniform = std > uniform_std_threshold
        checks.append(("not a blank/black/uniform frame", not_uniform,
                       f"pixel std-dev {std:.2f} (threshold {uniform_std_threshold}); "
                       f"mean brightness {mean:.1f}/255"))
    except Exception as e:  # noqa: BLE001
        checks.append(("image readable", False, f"{type(e).__name__}: {e}"))

    return QAResult(all(c[1] for c in checks), checks)
