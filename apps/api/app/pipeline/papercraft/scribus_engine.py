"""
Paper Craft — the Scribus adapter.

`render()` is the one entry point: `DocumentSpec` in, a rendered+aged PNG (plus
the editable .sla, a font-embedded PDF, and provenance JSON) out. Scribus does
the real document-layout work — grid, frames, styles, PDF export with font
embedding — through its own Python scripting API, invoked headless
(`scribus -g -cl -py _runner.py plan.json result.json`). This module never
builds Scribus API calls itself; it only compiles a `PageLayout` (from
`templates.py`) into the JSON plan `_runner.py` consumes, exactly the same
"Python orchestrator → subprocess worker → structured JSON back" shape
`threejs_engine.py` already uses for Puppeteer.

Status as of the code being written: the binary locator, the plan/result JSON
contract and the subprocess invocation had NOT been exercised against a real
Scribus process — no cache entry, no output file, no log existed to back the
round-trip. Treat any timing/behavior claim here as unverified until a real
render under `data/previews/papercraft/` proves it.

Content-addressed caching follows `dataviz.py`/`motiongfx.py` exactly: same
spec + same theme + same code version -> the identical cached PNG, forever,
via `pipeline/util.py`'s shared cache helpers.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path

from ...config import settings
from ..util import visual_cache_path, visual_cache_store
from .layout import Frame, PageLayout
from .spec import DocumentSpec
from . import templates as tpl
from . import finishing
from . import provenance as prov
from .binary import find_scribus_binary

_CACHE_VERSION = 10  # bumped: build_spec() now reads `stat` overlays; vintage_newspaper displays spec.statistics
_RUNNER = Path(__file__).parent / "_runner.py"

TEMPLATE_BUILDERS = {
    "modern_newspaper": tpl.modern_newspaper,
    "vintage_newspaper": tpl.vintage_newspaper,
    "research_paper": tpl.research_paper,
    "archive_dossier": tpl.archive_dossier,
    "financial_report": tpl.financial_report,
    "magazine_feature": tpl.magazine_feature,
    "breaking_news": tpl.breaking_news,
    "evidence_board": tpl.evidence_board,
    "company_memo": tpl.company_memo,
    "historical_document": tpl.historical_document,
    "news_clipping": tpl.news_clipping,
}


class ScribusUnavailable(RuntimeError):
    """No Scribus binary found. Caller should fall back to another visual tier."""


class ScribusRenderError(RuntimeError):
    pass


def cache_key(spec: DocumentSpec) -> str:
    body = json.dumps({
        "version": _CACHE_VERSION, **spec.model_dump(),
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _cached(key: str, out: Path) -> Path | None:
    hit = _cache_path(key)
    if hit.is_file() and hit.stat().st_size > 1024:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hit, out)
        return out
    return None


def _cache_path(key: str) -> Path:
    return visual_cache_path("papercraft", key, ".png")


async def render(spec: DocumentSpec, out_png: Path,
                  *, keep_intermediates: bool = True) -> "RenderResult":
    """Render `spec` to `out_png` (aged, finished). Returns paths + timing +
    the provenance record. Raises `ScribusUnavailable` if Scribus isn't
    installed — callers must treat that as a normal fallback trigger, not a
    hard failure, same as every other engine in this pipeline degrading to
    the branded plate when its tool of choice is missing."""
    binary = settings().papercraft_binary or find_scribus_binary()
    if not binary:
        raise ScribusUnavailable(
            "Scribus not found (set PAPERCRAFT_BINARY or install via winget: "
            "Scribus.Scribus)")

    key = cache_key(spec)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    hit = _cached(key, out_png)
    if hit is not None:
        return RenderResult(png=hit, sla=None, pdf=None, cache_hit=True,
                            render_ms=0.0, provenance=prov.build(spec, key, cache_hit=True))

    t0 = time.perf_counter()
    layout: PageLayout = TEMPLATE_BUILDERS[spec.document_type](spec)

    work = out_png.parent / f".papercraft_{key[:12]}"
    work.mkdir(parents=True, exist_ok=True)
    plan_path = work / "plan.json"
    result_path = work / "result.json"
    raw_png = work / "raw.png"
    sla_path = work / "document.sla"
    pdf_path = work / "document.pdf"

    plan = {
        "page": {"width": layout.width, "height": layout.height,
                 "margins": list(layout.margins)},
        "background": layout.background,
        "frames": [asdict(f) for f in layout.frames],
        "outputs": {
            "sla": str(sla_path), "pdf": str(pdf_path), "png": str(raw_png),
            "png_scale_pct": 300,
        },
    }
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    proc = await asyncio.create_subprocess_exec(
        binary, "-g", "-cl", "-py", str(_RUNNER), str(plan_path), str(result_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=settings().papercraft_timeout_s)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ScribusRenderError(
            f"Scribus render timed out after {settings().papercraft_timeout_s}s "
            f"({spec.document_type})") from exc

    if not result_path.is_file():
        raise ScribusRenderError(
            f"Scribus exited without writing a result ({spec.document_type}); "
            f"returncode={proc.returncode}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("ok"):
        raise ScribusRenderError(
            f"Scribus layout failed ({spec.document_type}): {result.get('error')}\n"
            f"{result.get('traceback', '')}")

    finishing.age(raw_png, out_png, paper_age=spec.paper_age,
                 seed=int(key[:8], 16))

    visual_cache_store(_cache_path(key), out_png)

    render_ms = (time.perf_counter() - t0) * 1000.0
    record = prov.build(spec, key, cache_hit=False, frames=result.get("frames", 0))

    final_sla = out_png.with_suffix(".sla")
    final_pdf = out_png.with_suffix(".pdf")
    if keep_intermediates:
        shutil.copyfile(sla_path, final_sla)
        shutil.copyfile(pdf_path, final_pdf)
    else:
        final_sla = final_pdf = None

    shutil.rmtree(work, ignore_errors=True)

    return RenderResult(png=out_png, sla=final_sla, pdf=final_pdf,
                        cache_hit=False, render_ms=render_ms, provenance=record)


class RenderResult:
    def __init__(self, *, png: Path, sla: Path | None, pdf: Path | None,
                cache_hit: bool, render_ms: float, provenance: dict):
        self.png = png
        self.sla = sla
        self.pdf = pdf
        self.cache_hit = cache_hit
        self.render_ms = render_ms
        self.provenance = provenance
