# K70 Visual Engine V2 — License + Automation Audit

Real audit, done 2026-08-23, against each repository's actual LICENSE/COPYING
file and (for GitHub API "NOASSERTION"/"Other" cases) the raw license text --
not assumed from README claims. Commit SHAs below are the exact HEAD of each
repo's default branch at audit time, fetched via the unauthenticated GitHub
REST API (`api.github.com/repos/<owner>/<repo>` and `.../commits/<branch>`).

Legend: **OUTPUT** = does using the tool restrict what I can do with the
video/image it renders. **ATTRIB** = must K70/the final video credit the tool.
**BUNDLED** = do any bundled assets (brushes, fonts, sample files, textures)
carry a different license than the core code.

---

## 1. Blender (core renderer, already in production use)

- **Repo**: github.com/blender/blender @ `e6d1620ad53f` (2026-08-23). K70's
  actual production install is the vendored portable **Blender 4.2.4 LTS**
  (`tools/k70_scene_engine/.blender_portable/`), not this HEAD -- recorded
  here for license currency only.
- **License**: GPL. `COPYING` at repo root points to `doc/license/GPL-license.txt`;
  GitHub's detector returns "NOASSERTION" only because the license text isn't
  a bare SPDX file, not because the license is unclear.
- **Commercial YouTube use**: Safe. Blender Foundation's own FAQ states files
  you create with Blender belong to you -- this is the standard "GPL doesn't
  reach the *output* of the program" principle (same as gcc, ffmpeg, GIMP).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No (not for output; only if K70's own code redistributed
  Blender's source, which it doesn't).
- **BUNDLED assets different license?** Blender ships some CC0/CC-BY sample
  content unrelated to K70's pipeline (not used here).
- **Automation**: Confirmed extensively this session -- `--background --python
  script.py -- args.json` is K70's entire rendering backbone already.
- **Status**: **PRODUCTION, already in use.** No action needed.

## 2. Synfig (candidate: Style 2 Premium 2D Vector)

- **Repo**: github.com/synfig/synfig @ `288284581bce` (2026-08-22).
- **License**: GPL-3.0 (confirmed via GitHub license API).
- **Commercial YouTube use**: Safe, same "output not restricted" principle --
  Synfig Studio's own site states rendered animations are the user's own work.
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** Not checked yet (no render attempted this session --
  see Pending Work below).
- **Automation**: Ships a genuine standalone CLI renderer (`synfig`, separate
  binary from the `synfigstudio` GUI) explicitly designed for headless
  `.sif` -> video/image rendering. This is the single most automation-friendly
  candidate of the five 2D/paint tools evaluated for license purposes.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED.**

## 3. Glaxnimate (candidate: Style 2 vector, Lottie/rigging companion)

- **Repo**: github.com/KDE/glaxnimate @ `b96944aadc1b` (2026-08-12).
- **License**: GPL-3.0-or-later (`COPYING` points to `LICENSES/GPL-3.0-or-later.txt`,
  KDE's standard REUSE-compliant license layout -- GitHub shows "NOASSERTION"
  only because the license text lives in `LICENSES/`, not `COPYING` itself).
- **Commercial YouTube use**: Safe (output-not-restricted principle).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** Not checked yet.
- **Automation**: Has a documented CLI export mode; primary use case in K70
  would be pairing with Synfig for character rigging, not as the renderer.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED.**

## 4. Krita (candidate: Style 3 paper-cut, Style 5 2.5D, Style 7 sketch)

- **Repo**: github.com/KDE/krita @ `6b8cd6c59e34` (2026-08-22).
- **License**: GPL-3.0 (confirmed via GitHub license API; Krita is also
  REUSE-compliant per-file, core is GPL-3.0-or-later).
- **Commercial YouTube use**: Safe (output-not-restricted principle;
  Krita's own FAQ explicitly states artwork made in Krita is 100% the
  artist's, commercial use encouraged).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** Real caveat -- Krita ships default brush presets and
  bundled resource packs from multiple contributors; the vast majority are
  CC0/public-domain by KDE policy, but a small number of bundled brush
  packs have historically carried their own attribution terms. Must be
  checked per-brush-pack if/when a specific bundled resource (not just the
  paint engine) is redistributed -- not yet relevant since no render has
  been attempted.
- **Automation**: Krita is fundamentally a GUI paint application. It exposes
  a Python scripting API (`krita` module, run via Scripter or a startup
  script) and some `--export`-style batch flags, but it is NOT designed
  around a `--background`-style headless render loop the way Blender/Synfig
  are -- expect real friction here.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED. Automation risk flagged in advance.**

## 5. OpenToonz (candidate: Style 7 hand-drawn/sketch)

- **Repo**: github.com/opentoonz/opentoonz @ `4c0e5848ea61` (2026-08-22).
- **License**: **BSD-3-Clause** for OpenToonz's own code (confirmed by
  reading `LICENSE.txt` directly -- GitHub's detector shows "Other" because
  the file leads with a thirdparty-code disclaimer before the license text,
  not because the license itself is ambiguous). BSD-3-Clause is one of the
  most permissive licenses evaluated in this audit.
- **Commercial YouTube use**: Safe.
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** BSD-3-Clause requires the license/copyright notice be
  retained in *redistributions of the software itself*, not in rendered
  video output -- no on-video attribution needed.
- **BUNDLED assets — real, explicit warning found in the LICENSE file
  itself**: "Some of code in this repository is derived from thirdparty
  libraries... For files in the 'thirdparty' directory... 'stuff/library/
  mypaint brushes' directory: Please see the licenses in ... Licenses.txt."
  I.e. OpenToonz's own license file explicitly tells you NOT to assume
  BSD-3-Clause covers everything -- any bundled brush presets or thirdparty
  library content must be checked individually before reuse. Not yet
  checked (no bundled brush has been used).
- **Automation**: OpenToonz is GUI-first with no robust, documented CLI batch
  render path comparable to Blender/Synfig/Natron. Treat as HIGH automation
  risk going in.
- **Status**: **LICENSE CLEAR (core). BUNDLED-ASSET CAVEAT REAL, MUST RE-CHECK IF BRUSHES USED. NOT YET INSTALLED/TESTED.**

## 6. Pencil2D (candidate: Style 7 hand-drawn/sketch)

- **Repo**: github.com/pencil2d/pencil @ `195bfda7fead` (2026-08-05).
- **License**: GPL-2.0 (confirmed via GitHub license API).
- **Commercial YouTube use**: Safe (output-not-restricted principle).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** Not checked yet.
- **Automation**: GUI-only traditional frame-by-frame animation tool, no
  official CLI render/export automation. Expect the same friction class as
  OpenToonz/Krita, likely worse (Pencil2D has the smallest scripting surface
  of the three).
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED. Automation risk flagged in advance -- lowest automation-readiness of the candidates evaluated.**

## 7. Natron (candidate: Style 3/5 compositing, parallax assembly)

- **Repo**: github.com/NatronGitHub/Natron @ `3763d805d7d2` (RB-2.6 branch,
  2026-07-24). Note: this is the **community-maintained fork**
  (NatronGitHub org) of the original MrKepzie/Natron project, which has been
  inactive for several years -- worth recording since "Natron" alone is
  ambiguous between the two.
- **License**: GPL-2.0 (confirmed via GitHub license API).
- **Commercial YouTube use**: Safe (output-not-restricted principle; Natron
  is explicitly positioned as a free Nuke-alternative compositor for
  professional/commercial pipelines).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** Bundles third-party OpenFX (OFX) plugins from various
  vendors under their own terms -- not yet relevant since none has been
  invoked.
- **Automation**: Genuinely strong candidate -- ships `NatronRenderer`, a
  documented standalone CLI binary built specifically for headless/batch
  project rendering (`NatronRenderer -w Writer1 project.ntp`), the same
  design philosophy as Blender's `--background` mode.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED. Best automation prospect of the non-Blender tools evaluated (with Synfig).**

## 8. BuildingNodes (candidate: Style 6 isometric, Style 1 street dressing)

- **Repo**: github.com/Durman/BuildingNodes @ `30d54052261d` (2023-11-21 --
  no commits since, project appears dormant but the last release is stable
  and installable).
- **License**: **No LICENSE file exists in the repo root** (GitHub's own
  license API returns `null`) -- this alone would normally mean "all rights
  reserved, no reuse permission" by default. However, the addon's own
  `__init__.py` source header explicitly states: `"Building Nodes add-on
  for Blender for procedural building modeling / Copyright (C) 2021
  Soluyanov Sergey | sv@soluyanov.ru / License - GPLv3"` -- a real,
  in-source license grant. Treat as **GPL-3.0** on that basis, but flag the
  missing formal LICENSE file as a documentation gap worth a courtesy email
  to the author before heavy commercial reliance, not a hard blocker.
- **Commercial YouTube use**: Safe under the in-source GPLv3 grant
  (output-not-restricted principle, same as any other GPL Blender addon).
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** None -- it's a geometry-nodes addon, no bundled art.
- **Automation**: It's a Blender addon (Blender 3.0+), so the SAME
  `--background --python` automation K70 already uses applies directly --
  no separate application/process to script. Real documented limitation from
  its own README: **"Animation is not supported"** -- relevant if V2 wants
  camera-relative building animation, not just static procedural generation.
- **Status**: **LICENSE CLEAR (in-source grant, missing formal LICENSE file noted). NOT YET INSTALLED/TESTED. Lowest integration risk of the non-Blender-core candidates since it's just a Blender addon.**

## 9. Storytools (candidate: Style 5 2.5D previz/parallax rigging)

- **Repo**: github.com/Pullusb/storytools @ `a159808ddcaa` (2026-08-07).
- **License**: GPL-3.0 (confirmed via GitHub license API).
- **Commercial YouTube use**: Safe.
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** None expected (storyboard/camera-rig tooling addon).
- **Automation**: Blender addon -- same `--background --python` path applies.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED.**

## 10. Stop-Motion-Blender-Addon (candidate: Style 4 clay/miniature)

- **Repo**: github.com/bkurdali/Stop-Motion-Blender-Addon @ `e8f1bf792c6f`
  (2024-08-28 -- dormant but installable).
- **License**: GPL-3.0 (confirmed via GitHub license API).
- **Commercial YouTube use**: Safe.
- **OUTPUT inherits restriction?** No.
- **ATTRIB required?** No, for rendered output.
- **BUNDLED assets?** None (a keyframing/mesh-cache workflow addon, no art assets).
- **Automation**: Blender addon -- same `--background --python` path applies
  in principle, though its actual value-add is an *interactive* stepped/
  on-twos workflow; per the brief ("evaluate only if it improves the result
  without destabilizing automation"), it will only be adopted if a plain
  scripted low-frame-rate/held-pose technique (no addon) proves insufficient.
- **Status**: **LICENSE CLEAR. NOT YET INSTALLED/TESTED.**

## 11. awesome-blender (reference list, not software)

- **Repo**: github.com/agmmnn/awesome-blender. This is a curated markdown
  links list, not a tool to integrate or render with -- used only as a
  research index if/when sourcing further addons. No license audit
  applicable to K70's output.

## 12. Thomas Rig Legacy (R&D-only, per explicit standing instruction)

- Already audited earlier this session: GPL-3.0-or-later, confirmed via its
  own `blender_manifest.toml`. **Status unchanged: R&D-only, NOT production,
  per your explicit instruction not to restart that debugging.** No further
  work done on it this pass.

---

## Cross-cutting findings

1. Every real candidate license (GPL-2.0/3.0, BSD-3-Clause) is safe for
   commercial YouTube output under the standard "GPL/BSD doesn't reach the
   *output* of the program" principle -- none of these tools' licenses put
   any restriction on the rendered video itself. This matches the same
   principle already relied on for Blender throughout this project.
2. The one real red flag is **bundled assets, not core licenses**:
   OpenToonz's own LICENSE.txt explicitly warns thirdparty/brush content
   needs separate checking, and Krita's default brush packs need the same
   scrutiny if a specific bundled brush (not just the paint engine) is ever
   redistributed. Neither has been triggered yet since no render has used
   bundled brush content.
3. **BuildingNodes has no formal LICENSE file** -- functionally fine (real
   in-source GPLv3 grant found), but it's the one repo here that doesn't
   meet the bar of "a proper LICENSE file at the root," worth remembering
   if the author is ever asked to confirm terms directly.
4. **Automation-readiness split, by design of each tool**:
   - Built for headless/CLI automation: Blender, Synfig, Natron (NatronRenderer),
     and all three Blender-addon candidates (BuildingNodes, Storytools,
     Stop-Motion-addon) since they inherit Blender's `--background` mode.
   - GUI-first with real automation friction expected: Krita (has a Python
     scripting API but no `--background`-equivalent render loop), OpenToonz
     and Pencil2D (no robust CLI automation surface at all).
   - This ranking, not license status, is what should drive which styles get
     attempted first under the 10-minute anti-bug-loop rule.

## Execution update (2026-08-24)

- **Synfig 1.5.5:** installed and genuinely executed; rendered the full
  144-frame premium-vector sequence from a `.sif` source. GPL-3.0.
- **Natron 2.5.0:** installed and genuinely executed; `NatronRenderer.exe`
  rendered the 144-frame 1920x1080 collage sequence through a real
  Read/Transform/Merge/WriteOIIO graph. GPL-2.0.
- **Krita 5.3.3:** installed and genuinely executed via `krita.com --export`;
  its exported RGBA artwork is consumed by the final Blender 2.5D render.
  GPL-3.0-or-later. No bundled brush resource was used.
- **Pencil2D 0.7.2:** installed and genuinely executed; its supported
  `project.pcl --export-sequence` CLI rendered four full-HD project frames,
  assembled into the specialized sketch proof MP4. GPL-2.0.
- **BuildingNodes:** downloaded and source-inspected only, not executed or
  adopted. Its lack of a bundled preset/example and manual setup steps make
  it an unjustified detour for the already-working isometric renderer.
- **Storytools, OpenToonz, Glaxnimate, Stop-Motion addon:** not executed.
