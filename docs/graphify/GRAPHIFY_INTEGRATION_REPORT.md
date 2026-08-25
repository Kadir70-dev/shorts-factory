# Graphify Integration Report — Shorts Factory

Date: 2026-08-09
Scope: install, build, and evaluate Graphify as a repository-navigation layer for Claude Code. No production code was modified in this task — only tooling config, Graphify-generated artifacts, and this report.

## 1. Installation

- **Tool identified and verified:** `Graphify-Labs/graphify` (PyPI package name `graphifyy`), MIT-licensed, actively maintained, fully local, no cloud/paid API required for its core AST-graph feature set. Verified before installing anything, per the prior task's explicit report.
- **Graphify version:** 0.9.37
- **Install command:**
  ```
  uv tool install graphifyy
  graphify install --project --strict
  ```
  (`uv` itself was installed via `winget install astral-sh.uv`; PATH did not propagate to the running shell, worked around with the absolute binary path and a `~/.bashrc` PATH append.)
- **Mode enabled:** project-scoped, **strict mode**, **code-only** extraction (no LLM enrichment, no source upload — satisfies requirement #4).
- **Hook/settings files changed:**
  - `.claude/settings.json` (new) — registers two `PreToolUse` hooks: `Bash|Grep` → `graphify hook-guard search`, `Read|Glob` → `graphify hook-guard read --strict`.
  - `.claude/skills/graphify/SKILL.md` + `.claude/skills/graphify/references/*.md` (new, 8 reference docs) — generated skill instructions.
  - `CLAUDE.md` (new, repo root) — 10-line `## graphify` section directing query-first usage.
  - `.graphifyignore` (new) — excludes vendored/build dirs (`.venv-win/`, `node_modules/`, `dist-*`, `data/`, `docs/graphify/`, `graphify-out/`).

## 2. Graph build

- **Files analyzed:** 276 code files (Python + TypeScript/TSX across `apps/api`, `apps/remotion`, `scripts`, `tests`). `config/*.yaml` was **deliberately excluded** — code-only mode classifies YAML as "Docs," which requires LLM extraction, and requirement #4 forbids that. This is a real coverage gap for anyone asking Graphify about config-driven behavior; noted here rather than glossed over.
- **Graph size:** 3410 nodes · 8471 edges · 175 communities (138 shown in the report, 37 thin ones omitted).
- **Edge provenance:** 92% EXTRACTED (real AST call/import edges), 8% INFERRED (avg confidence 0.7), 0% AMBIGUOUS.
- **Build time:** ~2m9s initial extraction + 16.4s community clustering.
- **Token cost:** 0 input / 0 output — confirmed genuinely local, no LLM calls made during the build.
- **Artifacts preserved** under `docs/graphify/`: `graph.html` (3.75MB), `graph.json` (4.9MB), `GRAPH_REPORT.md` (44KB). Live/working copies remain in `graphify-out/` (hardcoded path the skill/hooks depend on).

## 3. Hook verification (requirement #9)

Installer exit code alone was not trusted. Verified by:
1. Reading the actual installed `hook-guard` implementation in the Graphify package source (`_run_hook_guard`, `_hook_strict_enabled`, `_touch_query_stamp`/`_query_stamp_fresh`, `_mark_session_denied`, `_target_is_indexed`) to understand the exact blocking conditions.
2. Black-box testing the hook via direct NDJSON stdin payloads matching Claude Code's real `PreToolUse` protocol.
3. An initial test round showed no blocking where blocking was expected — traced to a **test-methodology bug**, not a Graphify bug: the Bash tool's heredoc quoting was collapsing `\\` to `\` in Windows paths, corrupting the JSON payload, which was then silently swallowed by a broad exception handler downstream. Fixed by using forward-slash paths in test payloads.
4. After the fix, confirmed genuine end-to-end behavior: a broad `Read`/`Glob` on an unindexed/broad target without a prior `graphify query` in the session returns `hookSpecificOutput.permissionDecision: "deny"`; a prior `graphify query`/`explain`/`path` call in the same session (tracked via a query-freshness stamp) unblocks subsequent reads. Requirement #7 (don't block *necessary* direct reads once a graph query has scoped the work) is genuinely satisfied, not just configured.

## 4. Nine architecture questions (requirement #10)

| # | Question | Result |
|---|---|---|
| 1 | topic → final.mp4 execution path | Partial. `graphify query` on this broad a question returns a large, noisy node set (path traversal fuzzy-matches on many loosely related terms); a clean answer required narrowing with `graphify path`/`explain` on specific known anchor functions rather than one broad query. |
| 2 | which module decides visual type | Clean. `graphify explain` on the Director/visual-budget nodes correctly surfaced the decision chain. |
| 3 | where does Paper Craft enter the pipeline | Clean. Traced through `_render_papercraft()` and its callers directly. |
| 4 | where does Paperima enter | Clean. Traced through `_try_paperima()`, `_PAPERIMA_WORTHY`, called from inside `_render_papercraft()`. |
| 5 | fallback chains | Answered via `graphify explain` on `_render_self()`, `_dispatch_scene()`, `_find_chrome()`, `_ensure_worker()` — the graph correctly shows the *call* structure of the fallback ladder (papercraft → paperima → camera-move-only), but exception-handling/"degrade gracefully" boundaries are not represented as edges (see §6, limitation). Confirming *where* a failure is caught still required reading source, not just graph traversal. |
| 6 | high-coupling/god nodes | Clean, directly from `GRAPH_REPORT.md`'s God Nodes section: `settings()` (197 edges), `VideoSpec` (81), `BrandTheme` (68), `SceneGraph` (68), `TopicIntelligenceRepository` (62), `Scene` (61), `TopicCandidate` (60), `TopicIntelligenceSettings` (56), `StoryboardScene` (45), `GeminiClient` (45). |
| 7 | dead/unreachable code | **No dedicated tool.** `GRAPH_REPORT.md` has no dead-code section, and fuzzy `graphify query "dead code unused functions..."` returned mostly irrelevant matches (an unrelated `ambience/longform.py` module, test names) rather than a real reachability analysis. Graphify's BFS/DFS traversal starts from fuzzy-matched nodes, not from a real program-entry-point reachability sweep — it cannot answer this question as asked. |
| 8 | duplicated modules | **No dedicated tool**, and the direct `graphify query` attempt returned near-noise (3 barely-relevant docstring fragments). One genuine, useful signal came indirectly: `graphify explain "_ensure_worker"` returned an "Ambiguous: matches 2 nodes" disambiguation between `paperima_engine.py` and `threejs_engine.py` — correctly surfacing that these two files intentionally share a near-identical NDJSON-worker-process pattern. That is a real (and in this case deliberate, documented) duplication, but it was found by accident of a name collision, not by a duplication-detection feature. |
| 9 | blast radius of `render_ffmpeg.py` | Clean and the most valuable result: reverse-traversal from `render_ffmpeg.py` correctly enumerated every caller/consumer across the pre-render dispatch chain (`broll.py`, `papercraft`, `threejs_engine.py`, `paperima_engine.py`, `visual_budget.py`), giving a genuine, accurate "what breaks if I touch this" answer. |

## 5. A/B benchmark (requirement #11)

**Question investigated (not previously explored this session):** "If Paperima/Chrome is unavailable at render time, what actually happens to a scene that would have used it — does the pipeline fail or degrade, and to what?"

| | Workflow A — plain search | Workflow B — Graphify-first |
|---|---|---|
| Tool calls | 4 (2 Grep, 2 Read) | 5 (1 `query`, 3 `explain`, 1 disambiguation retry) |
| Files opened | 2 (`broll.py`, `paperima_engine.py`) | Same 2, reached via graph traversal + confirmatory read |
| Noise | None — every call was directly on-target | The initial broad `query` returned 235 matching nodes (only 23 shown at an 800-token budget) polluted with unrelated hits from `topic_intelligence`/Gemini fallback code that happens to share vocabulary ("unavailable", "fallback") |
| Correctness | Fully correct: traced `_try_paperima()`'s broad `except Exception` → confirms the pipeline degrades gracefully, leaving the pre-existing papercraft camera-zoompan path untouched | Reached the same correct call chain (`render()` → `_worker_render()` → `_ensure_worker()` → `_find_chrome()`), but the exception-catching boundary itself is not a graph edge — closing the loop still required one direct source read (the same one workflow A used) |
| Outcome | Direct win: grep on the known entry point (`_try_paperima`) went straight to the answer in fewer, cleaner calls | Slower and noisier for *this specific question*, because it hinges on exception-handling control flow, which Graphify's static call/import graph does not model. Its bonus value was serendipitous, not the one it was asked to deliver: the ambiguous-node disambiguation is what actually surfaced the Q8 duplication finding above. |

**Honest conclusion:** for a question already anchored to a known symbol name, plain grep/read was faster and noise-free. Graphify's advantage shows up on the *broad*, symbol-unknown questions (Q6 god-nodes, Q9 blast-radius) where there is no obvious grep starting point and a human/agent would otherwise have to read many files to build the same picture manually. **No token/speed multiplier claim is made here** — this benchmark alone doesn't demonstrate one, and per the explicit constraint for this task, none is asserted beyond what's shown above.

## 6. Top architectural findings

- **God nodes / high coupling:** `settings()` is by a wide margin the most connected node in the repo (197 edges) — essentially a shared-state hub every subsystem depends on. `VideoSpec`, `BrandTheme`, `SceneGraph`, `Scene` form the next tier — the core data contracts every pipeline stage passes through.
- **One real import cycle:** `apps/api/app/director/__init__.py → engine.py → prompts.py → __init__.py` (3-file cycle). Python tolerates this, but it's a genuine structural finding worth knowing about if that module is ever split or refactored.
- **`render_ffmpeg.py` blast radius** is broad and cleanly enumerable via reverse traversal — the single most useful individual result this integration produced (Q9).
- **`config/*.yaml` is a real, deliberate coverage gap** in this graph: code-only mode (required by this task's constraints) treats YAML as "Docs" needing LLM extraction, so config-driven behavior (which many pipeline decisions read from `settings()`) is invisible to the graph. Anyone extending this setup should know config semantics still require manual reading.
- **Duplicated NDJSON-worker pattern** between `paperima_engine.py`/`threejs_engine.py` is real and intentional (documented in both files' own comments), surfaced only indirectly via a name-collision disambiguation rather than a dedicated duplication check.

## 7. Limitations / errors encountered

- No dead-code / unreachable-code detector (Q7).
- No duplicate-module detector (Q8) — the one relevant hit was incidental.
- Fuzzy `graphify query` on broad, multi-concept questions returns large, often noisy node sets dominated by unrelated vocabulary matches; it works best when narrowed to `explain`/`path` on a specific known symbol.
- Static call-graph edges don't represent exception-handling/degrade-gracefully control flow — questions about fallback *behavior* (as opposed to fallback *call structure*) still require reading source.
- `config/*.yaml` is invisible to the graph under the code-only constraint used here.
- Static import-graph blind spot (known from earlier in this session, not re-tested here): `sys.path.insert()` + function-body-scoped imports (used deliberately in `scripts/produce.py`) are invisible to tree-sitter-based cross-file resolution.

## 8. Confirmation

No production code was modified during this task. Only `.graphifyignore`, `.claude/settings.json`, `.claude/skills/graphify/**`, `CLAUDE.md`, and generated graph artifacts under `graphify-out/` and `docs/graphify/` were added or changed.
