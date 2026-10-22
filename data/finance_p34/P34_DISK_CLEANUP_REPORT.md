# P3.4 Disk Cleanup Report (read-only survey, nothing deleted)

- **Surveyed:** 2026-10-22.
- **Goal:** at least 12 GB free before the full master render.
- **Free space:** ≈6.6 GB before the P3.4 batches, **5.7 GB** after them (df -h, 2026-10-22 03:19). The P3.4 outputs themselves use only 41 MB; the other ~0.9 GB of the drop came from outside this project and was not investigated
- **Method:** "Referenced" means the absolute path appears anywhere in `scene_graph_p33.json` / `scene_graph_p34.json`.

**No file was deleted.** Every row below needs explicit user approval.

## Candidates

| # | Path | Size | Referenced by P3.3/P3.4 graph | What it is | Backup | Regenerable? | Risk if deleted |
|---|---|---|---|---|---|---|---|
| A1 | `data/finance_p0/k70_bitcoin_ep01_premium_v2/silent.mp4` | 990 MB | no | Video-only intermediate (scene clips concatenated) behind `final_p0_v2.mp4` | none | yes: `ffmpeg -f concat -c copy` of the 156 `scene_*.mp4` in the same folder (kept) | low; the Premium V2 master `final_p0_v2.mp4` (145 MB) is untouched |
| A2 | `data/jobs/k70_f4_bitcoin_ep01/silent.mp4` | 1068 MB | no | Video-only intermediate of the F4 job; its final was deleted earlier with user approval | none | yes, from the 156 job scene clips (kept) | low |
| A3 | `data/finance_f4/k70_f4_bitcoin_ep01_cinematic/silent.mp4` | 1042 MB | no | Video-only intermediate of the F4 cinematic render; its final was deleted earlier with user approval | none | yes, from its scene clips | low |
| B1 | `data/finance_f4/k70_f4_bitcoin_ep01_cinematic/scene_*.mp4` (156) | about 1.1 GB | no | Per-scene clips of the superseded F4 cinematic render | none | only by re-rendering F4 (CPU-hours) | medium: loses the ability to rebuild the F4 cut |
| C1 | `data/cache/*.mp4/*.webm` not referenced by the P3.3 graph (138 files) | about 1.89 GB | no (77 referenced cache files, 823 MB, are excluded) | Content-addressed stock downloads from other jobs and rejected candidates | none | yes, re-downloadable from Pexels/Pixabay: the URLs are in `data/cache/provider_search/` | low/medium: other jobs' graphs (`vid_*`, F3) may reference some; a per-graph check is needed before deleting |
| D1 | `data/benchmarks/` | 0.47 GB | no | Old engine benchmarks | none | yes (benchmark scripts) | low |
| D2 | `data/finance_f3/` | 0.37 GB | no | Superseded F3 experiment | none | partially | low/medium |
| E1 | `~/.cache/whisper/small.pt` | 462 MB | no | Whisper model used for the s30/s126 verification | none | yes (re-download) | low |
| — | `superseded_*` folders (P3.2: v1–v3; P3.3: v1–v2) | about 31 MB total | no | Previous P3.2/P3.3 graphs and plates | n/a | n/a | **Keep**; negligible gain |
| — | `~/.cache/puppeteer` (611 MB), `~/.cache/ms-playwright` (1.3 GB) | — | — | Puppeteer/Chromium is used by the Three.js worker; Playwright by browser tooling | — | — | **Do not delete** |

## Must keep (needed for the P3.4 render)

- `data/jobs/k70_f4_bitcoin_ep01/visuals/` and `vo/`: these contain 70 referenced files (motion_gfx/dataviz clips and the voiceover).
- `data/finance_p0/threejs_restore/clips/`: the 360×640 originals are preserved as a fallback.
- `data/finance_p34/threejs_final/`: the final 3D clips.
- `data/finance_p33/bitcoin_release_v1/assets/` and `data/finance_p32/bitcoin_editorial_v1/assets/`: plates and cinematic inserts.
- The 77 referenced `data/cache` files.
- `data/assets/` (music, SFX).

## Recommendation

Starting from 5.7 GB free:

| Option | Contents | Freed | Expected free space |
|---|---|---|---|
| 1 | A1 + A2 + A3 | 3.1 GB | about 8.8 GB |
| 2 | Option 1 + B1 | 4.2 GB | about 9.9 GB |
| 3 | Option 2 + C1 (after a per-graph reference check) | 6.1 GB | about 11.8 GB, just short of the target |
| 4 | Option 3 + D1 + D2 + E1 | 7.4 GB | about 13.1 GB, meets the ≥ 12 GB target |

**Recommended:** Option 4, but only with explicit approval for each row.
