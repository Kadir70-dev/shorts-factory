"""
GeoJSON border source for the `globe_flight` Three.js template.

Free and local by construction: the two public-domain border files are fetched
ONCE into the same content-addressed cache the visual providers use (sha1 of the
URL), then decoded to plain lon/lat polylines. Every later render — and every
offline render — reads the cache. No paid service, no map tile server, no API
key, and nothing is fetched while frames are being drawn.

Sources (both public domain / CC0):
  • Natural Earth 1:110m admin-0 countries  — world borders
  • PublicaMundi mirror of the US Census cartographic state boundaries

`borders()` returns rings already thinned for a 1080x1920 globe: at 110m the
full ring count is far more detail than a 6-second flight can resolve, and every
extra vertex is per-frame GPU work in the worker.
"""
from __future__ import annotations

import functools
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from ..config import settings

WORLD_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
             "master/geojson/ne_110m_admin_0_countries.geojson")
STATES_URL = ("https://raw.githubusercontent.com/PublicaMundi/MappingAPI/"
              "master/data/geojson/us-states.json")

# A ring below this many points is kept whole; larger rings are decimated to it.
# 96 points is ~4 degrees of arc on a country the size of the USA — under the
# pixel grid of a 1080-wide frame, so the saving is free visually.
_MAX_RING_POINTS = 96
_TIMEOUT_S = 60

Ring = list[tuple[float, float]]


def _cache_dir() -> Path:
    path = settings().data_dir / "cache" / "geo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(url: str) -> dict:
    """Content-addressed GeoJSON fetch. sha1(url) names the file, so the same
    source is downloaded at most once, ever."""
    target = _cache_dir() / f"{hashlib.sha1(url.encode()).hexdigest()}.geojson"
    if not target.is_file() or not target.stat().st_size:
        request = urllib.request.Request(url, headers={"User-Agent": "shorts-factory/1.0"})
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            payload = response.read()
        tmp = target.with_suffix(".part")
        tmp.write_bytes(payload)
        tmp.replace(target)                      # atomic publish, as elsewhere
    return json.loads(target.read_text())


def _thin(ring: list) -> Ring:
    step = max(1, len(ring) // _MAX_RING_POINTS)
    thinned = [(float(point[0]), float(point[1])) for point in ring[::step]]
    if thinned and thinned[0] != thinned[-1]:
        thinned.append(thinned[0])               # close the ring
    return thinned


def _rings(geometry: dict) -> list[Ring]:
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    if kind == "Polygon":
        return [_thin(ring) for ring in coords]
    if kind == "MultiPolygon":
        return [_thin(ring) for polygon in coords for ring in polygon]
    return []


def _name(properties: dict) -> str:
    for key in ("NAME", "name", "ADMIN", "NAME_LONG"):
        value = properties.get(key)
        if value:
            return str(value)
    return ""


def borders(url: str, *, only: str = "") -> tuple[list[Ring], list[Ring]]:
    """Return (all rings, rings of the named feature). `only` is matched case
    insensitively against the usual name properties, so the caller says "United
    States of America" or "Texas" rather than knowing the file's schema."""
    data = fetch(url)
    every: list[Ring] = []
    picked: list[Ring] = []
    wanted = only.strip().lower()
    for feature in data.get("features", []):
        rings = _rings(feature.get("geometry") or {})
        every.extend(rings)
        if wanted and _name(feature.get("properties") or {}).lower() == wanted:
            picked.extend(rings)
    return every, picked


@functools.lru_cache(maxsize=1)
def place_index() -> dict[str, str]:
    """`lowercase place name → source URL`, for template selection.

    Membership in the boundary file IS the test for "this beat is about a
    place": a name the cartographic source does not know cannot be flown to, so
    the selector declines instead of guessing. Built once per process.

    A cold cache needs one download. If that cannot happen — offline host, no
    prior render — the index is empty and every geography beat simply declines
    to the existing ladder, exactly as it did before this template existed.
    """
    index: dict[str, str] = {}
    for url in (WORLD_URL, STATES_URL):
        try:
            data = fetch(url)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        for feature in data.get("features", []):
            name = _name(feature.get("properties") or {})
            if name:
                index.setdefault(name.lower(), url)
    return index


# Spoken shorthands the boundary files do not carry as feature names.
_ALIASES = {
    "usa": "united states of america",
    "us": "united states of america",
    "u.s.": "united states of america",
    "america": "united states of america",
    "united states": "united states of america",
    "uk": "united kingdom",
    "britain": "united kingdom",
}


def resolve(text: str) -> tuple[str, str] | None:
    """First place named in `text`, as `(name, source url)`.

    Longest match wins so "New York" is not shadowed by "York", and states are
    preferred over countries when both match — the tighter zoom is the more
    specific editorial intent.
    """
    index = place_index()
    if not index:
        return None
    # Punctuation becomes whitespace BEFORE matching. Names are matched with
    # surrounding spaces so "York" cannot match inside "New York", but that also
    # meant a name followed by a comma — "crosses to Germany, and" — never
    # matched at all, and the beat silently lost its flight.
    lowered = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "
    best: tuple[str, str] | None = None
    for alias, canonical in _ALIASES.items():
        if f" {alias} " in lowered and canonical in index:
            best = (canonical, index[canonical])
    for name, url in index.items():
        if len(name) < 4 or f" {name} " not in lowered:
            continue
        if best is None or url == STATES_URL or len(name) > len(best[0]):
            if best is None or url == STATES_URL or best[1] != STATES_URL:
                best = (name, url)
    return best


def centroid(rings: list[Ring]) -> tuple[float, float]:
    """Vertex mean of the ring with the LARGEST AREA — good enough to aim a
    camera, and it ignores the outlying rings (Alaska, Hawaii, overseas
    territories) that drag a whole-feature mean into the ocean.

    Area, not vertex count: Alaska's coastline carries more points than the
    contiguous states, so ranking by length aimed the country leg of the flight
    at the Bering Sea.
    """
    if not rings:
        return (0.0, 0.0)

    def area(ring: Ring) -> float:
        return abs(sum(a[0] * b[1] - b[0] * a[1]
                       for a, b in zip(ring, ring[1:]))) / 2.0

    main = max(rings, key=area)
    lon = sum(point[0] for point in main) / len(main)
    lat = sum(point[1] for point in main) / len(main)
    return (round(lon, 4), round(lat, 4))
