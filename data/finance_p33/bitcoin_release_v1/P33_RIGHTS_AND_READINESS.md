# P3.3 Rights & Production Readiness: K70 Bitcoin Ep. 1

- **Branch:** `feature/k70-p32-editorial` (PR #9).
- **Graph:** `scene_graph_p33.json`, built from the P3.1 graph plus `p33_decisions.json`. It has 156 scenes and a 656.942 s timeline; narration, captions and audio are identical to P3.1.
- **Untouched:** the P3.1 graph, P3.2 graph, masters, voiceover, 20 Three.js clips and the 8 original AI clips are all unchanged on disk.

## Task 1: AI rights (8 Pollinations cinematic inserts)

### Evidence gathered

1. **Exact provenance.** Each final still is pixel-identical to a content-addressed cache file `ai_img_<sha1(key)>.jpg`. For all 8, the key reconstructs exactly as `pollinations:flux:<seed>:<prompt>` (`apps/api/app/pipeline/providers.py::_pollinations_image`). Provider = Pollinations and request parameter `model=flux` are therefore **proven**. The requests went to the legacy host `https://image.pollinations.ai/prompt/…` with `private=true` and `nologo=true`.
2. **What `flux` meant.** In Pollinations' public registry at the last commit before generation (`shared/registry/image.ts` @ `9435fff4`, 2026-10-18), `"black-forest-labs/flux.1-schnell": { aliases: ["flux"] }`. That registry belongs to `gen.pollinations.ai`; we found no evidence that the **legacy `image.pollinations.ai` host** routed through it.
3. **The response did not match the request.** We requested 768×1344 but received **580×1015** images. No response headers or model ID were logged, so the model that actually served each request cannot be proven. Today `https://image.pollinations.ai/models` returns only `["sana"]`.
4. **Provider terms in force at generation** (`pollinations.ai/public/legal/TERMS_OF_SERVICE.md` @ `4ead1048`, 2026-10-10): "We and our licensors own the Service, models, and documentation… **Model licences vary; verify before commercial use.**" The terms contain no grant or assignment of output rights.
5. **Generation runs.** s1, s33 and s46 were generated during the F4 job on 2026-10-20 and later "recovered" by P0. The other five were generated on 2026-10-21. During the same session the free tier returned HTTP 402 errors.

### Per-asset verdicts

Verdict rule: VERIFIED requires proof that FLUX.1 schnell served the request **and** provider terms that permit commercial use of the output. Neither is proven, so every asset is UNRESOLVED.

| Scene | Cache file | Generated | Seed | Provenance key | P0 status | Rights | P3.3 replacement | Original clip (preserved) |
|---|---|---|---|---|---|---|---|---|
| s1 | `ai_img_36f2efc0e69d…` | 2026-10-20 13:20 | 734171 | `pollinations:flux:734171:<prompt>` (exact sha1 match) | recovered | **UNRESOLVED** | INTERIOR, FIRST FLOOR, MAIN CORRIDOR, LOOKING NORTH - U | `finance_cinematic_e8bc163c82ee.mp4` |
| s33 | `ai_img_c2ad9a640b7a…` | 2026-10-20 13:20 | 874297 | `pollinations:flux:874297:<prompt>` (exact sha1 match) | recovered | **UNRESOLVED** | Photograph of a vault with gold bars - NARA - 296609.jp | `finance_cinematic_c7c8cc34db8a.mp4` |
| s46 | `ai_img_f3094be39bdd…` | 2026-10-20 13:26 | 57740 | `pollinations:flux:57740:<prompt>` (exact sha1 match) | recovered | **UNRESOLVED** | original K70 `broken_link` illustration | `finance_cinematic_964fc2760333.mp4` |
| s71 | `ai_img_ec1289818463…` | 2026-10-21 19:22 | 241541 | `pollinations:flux:241541:<prompt>` (exact sha1 match) | generated | **UNRESOLVED** | NTT DIPS in NTT History Center of Technologies.jpg | `finance_cinematic_f94655178542.mp4` |
| s79 | `ai_img_c5ff1caf5ebb…` | 2026-10-21 19:14 | 589476 | `pollinations:flux:589476:<prompt>` (exact sha1 match) | generated | **UNRESOLVED** | Apple Museum (Prague) Macintosh IIsi (1990).jpg | `finance_cinematic_dd439ddec7e4.mp4` |
| s101 | `ai_img_6b12e837c695…` | 2026-10-21 19:15 | 600656 | `pollinations:flux:600656:<prompt>` (exact sha1 match) | generated | **UNRESOLVED** | original K70 `wall` illustration | `finance_cinematic_ed05e6822fd9.mp4` |
| s123 | `ai_img_86d6d905fc45…` | 2026-10-21 19:16 | 913363 | `pollinations:flux:913363:<prompt>` (exact sha1 match) | generated | **UNRESOLVED** | original K70 `empty_room` illustration | `finance_cinematic_a9dcdc7159d1.mp4` |
| s145 | `ai_img_cef9eef9c897…` | 2026-10-21 19:23 | 574133 | `pollinations:flux:574133:<prompt>` (exact sha1 match) | generated | **UNRESOLVED** | original K70 `house_sign` illustration | `finance_cinematic_c742abc6f501.mp4` |

Each replacement is rendered by the same local 2.5D engine (`tools/finance_cinematic_cpu/engine.py`), reusing that scene's camera, strength, seed and effects. It is 720×1280 at 30 fps with the same duration, and it keeps the original transition, so the cinematic rhythm is preserved. The original AI clips stay in `data/finance_p0/cinematic_balanced/clips/` and are recorded in `p33_decisions.json → scenes[].motion.original_clip`.

## Task 2: Three.js quality

- **Current resolution:** all 20 clips in `data/finance_p0/threejs_restore/clips/` are **360×640** (confirmed with ffprobe; 3.1 MB total, template `globe_flight`).
- **Benchmark:** s72 (3.43 s) rendered at **1080×1920** (`--quality final`) into `data/finance_p33/threejs_final_bench/`.
  - Worker time: 47.6 s; whole process wall clock: 52.0 s.
  - Peak memory: 1640 MB in the browser worker; Python process max RSS 371 MB.
  - CPU: one core at 99% on a 4-core / 11 GB machine.
  - Output: 457 KB, 103 frames, 3.433 s, so the duration matches the scene.
- **Quality:** coastlines, borders and the label are visibly sharper than the upscaled preview, and nothing regressed.
- **Disk:** free space was 7.4 GB before and after; temporary frames were cleaned up.
- **Staged plan (not executed).** The 20 scenes total 95.9 s. At the benchmark rate (about 14× real time) the whole set takes roughly **22 minutes** of CPU and about 10 MB of output.
  1. Run in batches of 4–5 scenes with `scripts/k70_p0_threejs_restore.py --quality final --only <ids> --out data/finance_p33/threejs_final/batch_N`. Each batch writes to a new folder; the preview clips are never overwritten.
  2. After each batch, check the report: status `rendered`, probe 1080×1920, duration within ±1 frame of the scene, and non-flat `yavg_range`. Spot-check frames before starting the next batch.
  3. Require at least 3 GB free disk and at least 3 GB free RAM before each batch.
  4. Repoint the asset paths only in a new graph copy, after all 20 pass.

## Task 3: Editorial

- **s92:** the hooded-"hacker" Pexels clip becomes an original mail graphic: `To: majordomo@toad.com · subscribe cypherpunks`, "CYPHERPUNKS · 1992". The list was hosted on Gilmore's toad.com, per Wikipedia's *Cypherpunk* article.
- **s139:** an unrelated stock clip becomes **Lehman Brothers HQ, New York, 15 September 2008** (Robert Scoble, CC BY 2.0, with an on-plate credit).
- **s98:** becomes a bit-gold document plate (Design: Bit gold · Author: Nick Szabo · Year: 1998), placed below the scene's own headline. This breaks the s97–s100 run; no motion_gfx run longer than 3 remains.
- **Weak stock** (s13, s21, s40, s70, s133, s148) was left as is: it is generic rather than false, and replacing it would add plates without clear editorial gain.
- **Transitions:** dissolves into and out of every former AI slot and every Three.js scene are kept. Crossfades: 80/156; cuts: 55.

## Task 4: Production safety

- **Disk:** 7.3 GB free (97% used). That is enough for previews and the staged Three.js batches, but tight for a full 10m57s master. Free about 5 GB more before the full render; candidates include the 1 GB `silent.mp4` in the premium_v2 folder and the superseded_* folders, which need user approval.
- **Invariants checked on `scene_graph_p33.json`:**
  - 156 scenes; every duration identical; total 656.942 s.
  - Captions and audio identical.
  - 20 Three.js visuals and transitions identical; s35/s67 identical.
  - Every media path exists.
- **Previews:** single-scene clips were rendered with the real renderer and inspected for s1, s46, s92, s98, s139, s145, s25, s117 and s147. Two layout bugs were found and fixed: the s46 link spacing and the s98 headline overlap.
- **Tests:** `tests/test_k70_p32_editorial.py` 11 passed; `tests/` 127 passed.

## Remaining blockers before the first full render

1. Run the staged final-quality Three.js batches (about 22 min of CPU) and repoint them in a new graph copy.
2. Free disk space for the full master (recommended: at least 12 GB free).
3. Optional editorial work: the weak stock scenes (s13, s21, s40, s70, s133, s148).
4. At upload: paste the credits from `FINAL_VIDEO_CREDITS.md` and decide on the synthetic-voice disclosure.
5. Human frame-by-frame QA of the full render.
