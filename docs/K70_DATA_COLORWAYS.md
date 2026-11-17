# K70 Data Visualization — colorways

The original `config/brand/k70.yaml` stays **untouched**. The chart Shorts can
select one of three coordinated palettes with a single CLI flag. Every colorway
reuses the existing type, watermark, safe areas, captions, FFmpeg renderer, music
and brand assets. It is **not** a new Shorts Factory or a new YouTube channel.

| Palette | Background | Highlight | Neutral series | Positive | Negative |
| --- | --- | --- | --- | --- | --- |
| Aurora (recommended) | `#081525` | `#A78BFA` violet | `#22D3EE` cyan | `#34D399` mint | `#FB7185` coral |
| Sunset | `#180F22` | `#FFB86B` amber | `#C084FC` purple | `#4ADE80` green | `#FB7185` rose |
| Ocean | `#081A25` | `#2DD4BF` teal | `#60A5FA` blue | `#4ADE80` green | `#F87171` red |

### Render with an opt-in palette

```bash
python make_gen.py "How NVIDIA grew over the last decade" --niche business --colorway aurora
python make_gen.py "How Dubai's population changed" --niche facts --colorway sunset
python make_gen.py "Why energy demand is growing" --niche economy --colorway ocean

# Existing default remains identical:
python make_gen.py "Why Americans are worried about inflation" --niche economy
```

The `--colorway` flag sets `SceneGraph.brand_id` **after Director generation**
and before the usual variety/asset/render steps. Every downstream module resolves
the selected brand from the graph, so the full Short stays visually consistent.
`classic` deliberately leaves Director-selected branding unchanged.

### Colored ranking bars

The new palettes also define `chart.category_colors` as six coordinated,
distinct colors. In **bar comparison** charts only, neutral categories rotate
through those colors, while a highlighted category uses the palette's primary
accent. Explicit `positive`/`negative` data emphasis overrides decorative
category coloring. The classic renderer keeps its original behavior.

This is a palette extension; not an animated bar-chart race renderer. Charts
still require authored values and source attribution, and the 570-video
production plan remains a separate step.

### Checks

```bash
cd apps/api
python -m pytest tests/test_k70_chart_colorways.py -q
```

No uploads, schedules, existing videos, 14-layer K70 long-form architecture,
or protected documentary assets are changed by this feature.
