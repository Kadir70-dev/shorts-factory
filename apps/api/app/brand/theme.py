"""
BrandTheme — config/brand/<id>.yaml parsed into something the renderer can use.

Two jobs beyond plain deserialisation:

  1. FONT RESOLUTION. The YAML names font FAMILIES in preference order. Machines
     differ, so we resolve each family to a real .ttf/.otf on disk (fontconfig
     first, then a scan of the usual font roots) and fall back to the faces that
     ship with every Debian/Ubuntu box. A missing designer font degrades the look,
     never the render.

  2. COLOUR PLUMBING. ffmpeg wants `0xRRGGBB`, ASS wants `&HBBGGRR`, our numpy
     rasteriser wants an (R,G,B) tuple. One palette, three accessors, so no module
     downstream has to hand-convert hex and get the byte order wrong.
"""
from __future__ import annotations

import functools
import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import CONFIG_DIR

# Faces guaranteed present on the target boxes — the end of every fallback chain.
_LAST_RESORT = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_MONO_LAST_RESORT = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
] + _LAST_RESORT

_FONT_ROOTS = [
    Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
    Path.home() / ".fonts", Path.home() / ".local/share/fonts",
]


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ff(hex_color: str) -> str:
    """ffmpeg colour literal (`0xRRGGBB`)."""
    return "0x" + hex_color.strip().lstrip("#").upper()


def ass(hex_color: str, alpha: int = 0) -> str:
    """ASS colour literal — &HAABBGGRR, i.e. BYTE-REVERSED vs hex, alpha first.
    alpha 0 = fully opaque, 255 = fully transparent (ASS convention)."""
    r, g, b = rgb(hex_color)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


# --------------------------------------------------------------------------- #
# Font resolution
# --------------------------------------------------------------------------- #
def _is_variable(path: str) -> bool:
    """Variable fonts (`Ubuntu[wdth,wght].ttf`) are a trap here: ffmpeg's drawtext
    and libass both render the DEFAULT instance, so asking for Bold silently gets
    Regular. We only accept one when there is no static alternative."""
    return "[" in Path(path).name


def _looks_bold(stem: str) -> bool:
    s = stem.lower()
    return (any(t in s for t in ("bold", "black", "heavy", "semibold"))
            or s.endswith(("-b", "-bd", "_b")))


@functools.lru_cache(maxsize=256)
def _fc_match(family: str, bold: bool) -> str:
    """Ask fontconfig for a family's file. Empty string when fc-match is absent
    or the match is a substitution for something we didn't ask for."""
    if not shutil.which("fc-match"):
        return ""
    query = f"{family}:style=Bold" if bold else family
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}|%{family}", query],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:                          # noqa: BLE001
        return ""
    path, _, matched = out.partition("|")
    if not path or not Path(path).exists():
        return ""
    # fc-match ALWAYS returns something — verify it actually matched the family
    # we asked for rather than silently substituting the default face.
    want = re.sub(r"[^a-z]", "", family.lower())
    got = re.sub(r"[^a-z]", "", matched.lower())
    if not want or want not in got:
        return ""
    # A variable file can't express the weight we asked for; let the filesystem
    # scan look for a static Bold before settling for it.
    if bold and _is_variable(path):
        return ""
    return path


@functools.lru_cache(maxsize=256)
def _scan_roots(family: str, bold: bool) -> str:
    """Filesystem fallback — also the path that finds static Bold faces that
    fontconfig would have answered with a variable file."""
    slug = re.sub(r"[^a-z0-9]", "", family.lower())
    if not slug:
        return ""
    fallback = ""
    for root in _FONT_ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() not in (".ttf", ".otf"):
                continue
            if slug not in re.sub(r"[^a-z0-9]", "", p.stem.lower()):
                continue
            if bold == _looks_bold(p.stem) and not _is_variable(str(p)):
                return str(p)
            fallback = fallback or str(p)
    return fallback


def resolve_font(families: list[str], bold: bool = True,
                 mono: bool = False) -> tuple[str, str]:
    """First installed face from the preference list → (file path, family name).

    Both halves are needed: ffmpeg's `drawtext` wants a FILE, while libass (our
    caption renderer) resolves by FAMILY NAME through fontconfig. Returning one
    and guessing the other is how caption typography silently drifts away from
    overlay typography.
    """
    for fam in families:
        hit = _fc_match(fam, bold) or _scan_roots(fam, bold)
        if hit:
            return hit, fam
    fallbacks = _MONO_LAST_RESORT if mono else _LAST_RESORT
    for p in fallbacks:
        if Path(p).exists():
            name = "DejaVu Sans Mono" if "Mono" in p else (
                "Ubuntu" if "ubuntu" in p else "DejaVu Sans")
            return p, name
    return "", "DejaVu Sans"                   # renderer falls back to ffmpeg default


# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FontFace:
    families: list[str]
    path: str                                  # for ffmpeg drawtext
    name: str = "DejaVu Sans"                  # for libass / ASS `Fontname`
    case: str = "none"                         # upper | lower | none

    def apply_case(self, text: str) -> str:
        if self.case == "upper":
            return text.upper()
        if self.case == "lower":
            return text.lower()
        return text


@dataclass(frozen=True)
class GradeVariant:
    name: str
    contrast: float
    saturation: float
    brightness: float
    gamma: float
    vignette: float

    def ffmpeg(self) -> str:
        """eq + vignette chain — the shared documentary look."""
        return (f"eq=contrast={self.contrast}:saturation={self.saturation}:"
                f"brightness={self.brightness}:gamma={self.gamma},"
                f"vignette=PI/{self.vignette}")


@dataclass
class BrandTheme:
    id: str
    name: str
    tagline: str
    palette: dict[str, str]
    sizes: dict[str, int]
    display: FontFace
    body: FontFace
    mono: FontFace
    watermark: dict
    lower_third: dict
    intro: dict
    outro: dict
    captions: dict
    chart: dict
    safe: dict
    title_card: dict = field(default_factory=dict)
    background: dict = field(default_factory=dict)
    timeline: dict = field(default_factory=dict)
    icons: dict = field(default_factory=dict)
    transitions: dict = field(default_factory=dict)
    cta: dict = field(default_factory=dict)
    grades: dict[str, GradeVariant] = field(default_factory=dict)
    fingerprint: str = ""                      # hash of the source YAML

    # -- colour accessors --------------------------------------------------- #
    def hex(self, key: str, default: str = "#ffffff") -> str:
        """Palette lookup that also accepts a literal hex value, so config fields
        can say either `primary` or `#ff0000` interchangeably."""
        if key.startswith("#"):
            return key
        return self.palette.get(key, default)

    def rgb(self, key: str, default: str = "#ffffff") -> tuple[int, int, int]:
        return rgb(self.hex(key, default))

    def ff(self, key: str, default: str = "#ffffff") -> str:
        return ff(self.hex(key, default))

    def ass(self, key: str, alpha: int = 0, default: str = "#ffffff") -> str:
        return ass(self.hex(key, default), alpha)

    # -- layout ------------------------------------------------------------- #
    def size(self, key: str, height: int = 1920) -> int:
        """Type size scaled from the 1920-tall reference frame."""
        return max(8, round(self.sizes.get(key, 48) * height / 1920))

    def grade(self, variant: str = "") -> GradeVariant:
        if variant and variant in self.grades:
            return self.grades[variant]
        return next(iter(self.grades.values()))

    def grade_names(self) -> list[str]:
        return list(self.grades)


_DEFAULT_GRADE = GradeVariant("neutral_doc", 1.06, 1.04, -0.015, 1.0, 5.0)


@functools.lru_cache(maxsize=8)
def load_theme(brand_id: str = "k70") -> BrandTheme:
    """Load + resolve a brand. Cached: font resolution shells out to fc-match and
    we do NOT want that on every scene of every short."""
    path = CONFIG_DIR / "brand" / f"{brand_id}.yaml"
    raw = yaml.safe_load(path.read_text()) if path.exists() else {}
    fingerprint = hashlib.sha256(
        (path.read_text() if path.exists() else brand_id).encode()
    ).hexdigest()[:12]

    t = raw.get("type", {}) or {}

    def face(key: str, mono: bool = False) -> FontFace:
        spec = t.get(key, {}) or {}
        fams = spec.get("family") or []
        bold = str(spec.get("weight", "bold")).lower() in ("bold", "black", "heavy")
        path, name = resolve_font(list(fams), bold=bold, mono=mono)
        return FontFace(families=list(fams), path=path, name=name,
                        case=str(spec.get("case", "none")))

    grades = {
        name: GradeVariant(
            name=name,
            contrast=float(v.get("contrast", 1.06)),
            saturation=float(v.get("saturation", 1.04)),
            brightness=float(v.get("brightness", -0.015)),
            gamma=float(v.get("gamma", 1.0)),
            vignette=float(v.get("vignette", 5.0)),
        )
        for name, v in ((raw.get("grade", {}) or {}).get("variants", {}) or {}).items()
    } or {"neutral_doc": _DEFAULT_GRADE}

    return BrandTheme(
        id=raw.get("id", brand_id),
        name=raw.get("name", brand_id),
        tagline=raw.get("tagline", ""),
        palette=raw.get("palette", {}) or {},
        sizes=(t.get("sizes", {}) or {}),
        display=face("display"),
        body=face("body"),
        mono=face("mono", mono=True),
        watermark=raw.get("watermark", {}) or {},
        lower_third=raw.get("lower_third", {}) or {},
        intro=raw.get("intro", {}) or {},
        outro=raw.get("outro", {}) or {},
        captions=raw.get("captions", {}) or {},
        chart=raw.get("chart", {}) or {},
        safe=raw.get("safe", {}) or {},
        title_card=raw.get("title_card", {}) or {},
        background=raw.get("background", {}) or {},
        timeline=raw.get("timeline", {}) or {},
        icons=raw.get("icons", {}) or {},
        transitions=raw.get("transitions", {}) or {},
        cta=raw.get("cta", {}) or {},
        grades=grades,
        fingerprint=fingerprint,
    )
