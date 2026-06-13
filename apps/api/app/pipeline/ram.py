"""
CPU-only RAM budget guard + child-process peak monitor (Phase 3).

The layered FFmpeg compositor stacks several planes in one filter_complex, which
is the one place this CPU-first pipeline can spike memory on a 12GB box. These
helpers let the compositor (a) refuse to start when free RAM is already low and
(b) report the ffmpeg child's peak RSS for the QA readout — WITHOUT adding a
psutil dependency (we read /proc/meminfo and resource.getrusage only).

Everything degrades SAFELY: on a non-Linux host or an unreadable /proc, the
"available" reading is None, which callers treat as "unknown → do not block".
So these guards can only ADD safety on the target hardware; they never break a
render elsewhere.
"""
from __future__ import annotations

import resource
from pathlib import Path

_MEMINFO = Path("/proc/meminfo")


def _meminfo_mb(field: str) -> float | None:
    """Read one MB value from /proc/meminfo, or None if unavailable."""
    try:
        for line in _MEMINFO.read_text().splitlines():
            if line.startswith(field + ":"):
                return float(line.split()[1]) / 1024.0      # kB → MB
    except Exception:
        return None
    return None


def available_mb() -> float | None:
    """Currently-available RAM in MB (MemAvailable), or None if it can't be read.
    None == 'unknown' — callers must NOT block a render on an unknown reading."""
    return _meminfo_mb("MemAvailable")


def total_mb() -> float | None:
    """Total system RAM in MB, or None if it can't be read."""
    return _meminfo_mb("MemTotal")


def budget_ok(min_free_mb: float) -> bool:
    """True when at least `min_free_mb` is free right now — OR when the reading is
    unknown (so this guard only ever ADDS safety on Linux/12GB, never elsewhere)."""
    avail = available_mb()
    return avail is None or avail >= float(min_free_mb)


def child_peak_mb() -> float:
    """High-water peak RSS (MB) across all child processes reaped so far this run.
    On Linux `ru_maxrss` is in kB. Read it AFTER an ffmpeg run for a per-stage
    peak readout; it's cumulative-high-water, so compare against a pre-run sample
    if you want the delta."""
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ru.ru_maxrss / 1024.0                            # kB → MB (Linux)
