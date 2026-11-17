# K70 advanced data visualisation engine

`apps/api/app/pipeline/dataviz_adv/` -- cinematic charts for Shorts, drawn with Pillow/NumPy into RGBA frames and
composited over real footage by FFmpeg.  It is **additive**: the classic `dataviz.py` engine, the K70 14-layer
long-form architecture and every already-published asset are untouched.

| Module | What it gives you |
| --- | --- |
| `core.py` | `ChartTheme` (from any K70 brand colourway), validated `Series`, `yoy_series` / `cumulative_series`, easing, `ViewTrack` (camera in data space), `Timeline`, text tiles, `Recorder` (for tests) |
| `line.py` | `LineChart` -- draw-on line, glow, gradient area, value pill riding the head, direction-coloured counter, callouts, **dynamic axes** that re-tick while the camera zooms |
| `race.py` | `BarRace` -- ranked bars with hysteresis (no stacked rows), smooth overtakes, animated values, period indicator, optional icons |
| `geo.py` | `GeoMap` -- choropleth on Natural Earth boundaries (`data/geo/`, public domain) with moving timeline, region labels + live values, camera (`MapTrack`) |
| `story.py` | `stat` (counting number), `before_after`, `percent_compare`, `split_screen`, kinetic `headline`, source line |
| `transitions.py` | `CameraTrack` + `apply_camera`, `MorphLineBars` (line -> bars), `focus_pulse` |
| `compose.py` | FFmpeg compositor: graded real footage with push-in, hard cuts inside a scene, `Bg` blur ramps for **footage -> chart -> footage** transitions |
| `qa.py` | Frame-level checks: text outside the safe area, text below 30 px, overlapping labels, frame-to-frame jumps, FPS/probe, caption<->voice sync |

## Using it in a Short

```python
from app.pipeline import dataviz_adv as A
th = A.ChartTheme.load("k70_chart_aurora")          # or k70_chart_sunset / k70_chart_ocean
yoy = A.yoy_series("U.S. inflation rate", cpi_index, "2021-01", "2023-06",
                   "U.S. BLS CPI-U CUUR0000SA0, NSA", "2026-11-17")      # source + units are mandatory
peak = yoy.periods.index("2022-06")
chart = A.LineChart(th, yoy, A.Timeline([(0.25, 0), (2.3, peak), (3.9, 29)]),
                    view=A.ViewTrack([(0, A.View(0, 29, 0, 10.6)), (1.6, A.View(7, 27, 3, 10.2))]),   # camera zooms to the peak
                    y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%",
                    big_fmt=lambda v: (f"{v:.1f}%", "year over year"),
                    callouts=[A.Callout(peak, "PEAK 9.1%", "JUNE 2022", th.negative, 1.5)])
A.compose.render_video(out_mp4, frames, [(footage_clip, 8.0, seconds)],
                       lambda t: draw(chart, t),                 # returns an RGBA layer
                       A.compose.Bg("ramp", blur_in=(0, 0.5), blur_out=(seconds - 0.9, 0.7)))    # footage->chart->footage
```

`scripts/k70_usa_inflation_short_v2.py` is the full worked example (12 scenes, voice, captions, music, SFX, render);
`scripts/k70_dataviz_demos.py` renders every chart type from real BLS data.

### Through the scene graph (schema 2.1)

`DataViz.kind` now also accepts `line_cinematic`, `bar_race`, `geo_map`, `morph_bars`, with sourced
`DataViz.series: [DataSeries]` and `DataViz.config` (timeline / views / callouts / map options).  `dataviz.render()`
delegates to the advanced engine for those kinds.  Schema 2.0 graphs still validate; `SCHEMA_VERSION` is `"2.1"`
(the Remotion zod mirror was already out of step before this change and does not model `DataViz`).

## Data rules (enforced, tested)

* a `Series` without `source` or `units`, with duplicate periods, non-finite values or fewer than 2 points raises `DataError`
* unpublished months stay `None`: lines draw them as a **dashed bridge**, bar races **drop** the period (and report it in `.dropped`), maps paint unmapped features grey
* inflation **rate** (`yoy_series`, 12-month change) and **price level** (`cumulative_series`, change since a base month) are different functions -- never label one as the other
* bar-race values must be non-negative; a headline that does not fit the frame raises instead of clipping
* red/green are reserved for direction (`ChartTheme.direction`): they are filtered out of the category palette (the Sunset colourway's rose is removed from the categories automatically)

## Colourways

`k70_chart_aurora` (default), `k70_chart_sunset`, `k70_chart_ocean` from PR #12; the original `k70` theme is not modified.
Eight distinct category colours are guaranteed; gold (`warn`) is the highlight.

## Footage mix

Charts sit on blurred, darkened **real** footage; counters/kinetic type sit on graded footage.  Never substitute a
missing licensed clip with an unrelated one -- `render_video` fails if a source file is missing.  Keep licence data in
a `footage_manifest.json` next to the clips (see `data/k70_usa_inflation_20261117/`).

## Quality gates

`apps/api/tests/test_dataviz_adv.py` (frame-level): CPI figures vs the saved BLS responses, year/value sync, interpolation,
dashed gaps, dynamic axes + units, source attribution, safe-area/min-size text, ranking smoothness + hysteresis,
map regions, morph continuity, camera smoothness, colourway semantics, schema compatibility, real FFmpeg render at 30 fps.
Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/test_dataviz_adv.py tests/test_k70_chart_colorways.py -q`.

## Performance (CPU-only HP EliteBook, 1080x1920 @ 30 fps, graphics on a navy plate)

| Demo clip (real BLS data) | length | render | per frame |
| --- | --- | --- | --- |
| `line_cinematic` (camera zoom to the 2022 peak) | 6.2 s | 20.9 s | 112 ms |
| `bar_race` (8 categories, 80 months) | 6.8 s | 13.5 s | 66 ms |
| `geo_map` (US regions, timeline, zoom) | 6.8 s | 33.3 s | 163 ms |
| `story_before_after` (counters + comparison bars) | 4.5 s | 6.2 s | 46 ms |
| `split_screen` (rate over level) | 5.6 s | 13.7 s | 81 ms |
| `morph_line_to_bars` | 4.2 s | 4.8 s | 38 ms |

The full USA Inflation V2 Short (12 scenes, 1,243 frames: footage, blur ramps, graphics, grain) renders in about 5.5 minutes on
top of TTS/music/SFX.  Charts are streamed to FFmpeg as raw RGBA, so no frame files are written to disk.

## Chart samples (`scripts/k70_chart_samples.py`)

Two 5-second previews from verified BLS data: a bar-chart race through the open-source `bar_chart_race` library (K70 Aurora styling,
`pip install -r apps/api/requirements-charts.txt`; the script shims the library's removed `fillna(method=)` call and declutters
value labels of crossing bars) and an animated line chart through `LineChart` with a head-synchronised date readout
(counter, pill and date always show the same published month).  Output: `data/k70_chart_samples/`.

## Known limits

* geographic maps use 110 m Natural Earth boundaries (story scale, not legal boundaries); only the US-state composite and a world equirectangular map are included
* the bar race drops periods where any entity is unpublished; it does not interpolate across a gap
* during an overtake two rows briefly cross (by design); persistent near-ties are held apart by the hysteresis
* the stock Kokoro voice is used for narration until the cloned `k70_host_v1` voice is enrolled
