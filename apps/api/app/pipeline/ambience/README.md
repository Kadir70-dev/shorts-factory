# Long-form ambience pipeline

Generates multi-hour 4K60 ambience videos (fireplace, and whatever comes next)
from a YAML preset. Sits alongside the short-form pipeline and reuses its
conventions — preset-driven config, ffmpeg for encoding, a QA gate before an
artefact is considered done — but shares none of its stages, because nothing
here needs an LLM, TTS, captions, b-roll or stock footage.

```
.venv/bin/python scripts/produce_ambience.py --preset ambience_fireplace
.venv/bin/python scripts/produce_ambience.py --preset ambience_fireplace --smoke
```

`--smoke` runs the identical code path at 1280x720 / 10 s loop / 60 s total in
about 7 minutes. Use it after any change; it exercises every stage including the
stream-copy and the QA gate.

## The one idea that makes this feasible

Two hours of 4K60 is **432,000 frames**. On the target box (4 cores, no working
CUDA, so libx264 only) a frame costs ~3.4 s, which is ~40 hours of rendering.

Instead we render **exactly one loop period** (5,400 frames = 90 s) and multiply
it out:

```
ffmpeg -stream_loop 79 -i loop.mp4 -stream_loop 79 -i loop.wav \
       -c:v copy -c:a aac ...
```

`-c:v copy` re-muxes packets without re-encoding, so the 2-hour master costs
minutes of I/O rather than hours of CPU, and every repetition is bit-identical
to the loop. Total cost drops from ~40 h to ~5.5 h.

This only works if the loop is **exactly periodic**, which is therefore the
invariant the whole package is built around.

## How seamlessness is guaranteed

Nothing crossfades. Periodicity is structural, and it is verifiable:

| Layer | Mechanism |
|---|---|
| flame / smoke turbulence | 3-D value-noise lattice that wraps on all axes; the z axis is traversed exactly once per loop (`noise.py`) |
| upward advection | y-scroll of an **integer** number of lattice periods per loop, so it wraps when z does |
| embers | every particle's state is a function of `(loop_phase + phase_j) mod 1`, with alpha zero at both ends of its own life |
| coal pulse | sum of sinusoids at **integer** frequencies in loop phase |
| audio bed | white noise shaped by multiplying its FFT — circular convolution is periodic to the sample |
| audio transients | written with `np.add.at` on indices mod N, so a crackle straddling the join wraps and completes |

Verified, not assumed:

```
grain OFF: max|f(0) - f(N)| = 0    mean = 0.000000    nonzero px = 0
audio seam_ratio = 0.0615          (1.0 == a normal sample-to-sample step)
```

Frame N is **bit-identical** to frame 0. The only thing that differs across the
join in the shipped render is the deliberate film grain, which should not repeat.

## Resolution strategy

The frame is split by how sharp each element genuinely is:

- **native 4K** — hearth plate (logs, bark, ash, brick) and ember particles.
  These are what the eye checks for sharpness.
- **1/3 resolution, upscaled** — flame, smoke, and the fire-light field. These
  are physically soft, so simulating them at 1280x720 is ~9x cheaper and
  visually indistinguishable after a smoothing pass.

The plate is rendered **once** per job, not per frame.

## Dynamic lighting

`respond` (baked cylindrical normals on the logs, upward bias on the ash) times
`light` (a heavily blurred copy of *this frame's own flame*) relights the plate
every frame. There is no LFO anywhere — the light **is** the fire, so the room
flickers in exact sympathy with the flames, and the lighting is periodic for
free because the flame is.

## Modules

| File | Role |
|---|---|
| `noise.py` | exactly-periodic 3-D value noise / fBm — the core invariant |
| `imaging.py` | blur, resample, colour ramp, tone-map, PNG writer |
| `hearth.py` | static 4K plate: firebox, ash bed, split logs |
| `flame.py` | flame + smoke + fire-light fields |
| `embers.py` | rising ember particles, drawn at native 4K |
| `compositor.py` | relight + layer stack + tone-map |
| `audio.py` | seamless stereo crackle synthesis |
| `encode.py` | pipe encoder + stream-copy master builder |
| `longform.py` | resumable orchestrator + QA gate |

Adding a second theme (rain, thunderstorm, forest) means a new scene module plus
a preset — `noise`, `imaging`, `encode` and `longform` are theme-agnostic.

## Originality

Every pixel and every sample is synthesised from a seeded RNG. There is no
sample library, no stock footage, no photographic texture and no generative
model anywhere in the chain, so the output is original by construction rather
than by review — which is what makes the copyright-safe / monetisation-safe
claim in the brief actually checkable.

## Performance notes (learned the hard way)

- `np.power` in the sRGB encode cost **1.2 s/frame** over 25M elements. Replaced
  with a 12-bit LUT.
- `upscale` must blur *before* expanding; blurring at 4K instead of at sim
  resolution wasted ~4 full-res passes per frame.
- `blur` pins its axes to 0/1. Using `-2/-1` silently blurred across the colour
  channels of RGB inputs — a real bug the smoke test could not catch, because
  `sim_divisor=1` returns from `upscale` early.
- x264 at 4K with default lookahead/refs reached **1.7 GB RSS** and would have
  OOM'd the box hours into the run. Capped via
  `rc-lookahead=12:ref=2:bframes=2:sync-lookahead=0`.
