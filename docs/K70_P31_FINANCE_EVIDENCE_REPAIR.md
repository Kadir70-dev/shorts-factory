# K70 P3.1 — Finance Archival Priority and Chart Recovery

Scope: long-form landscape usa_finance documentaries, PLUS the original 156-scene K70 Bitcoin history episode and its F4/P0 production copies. Their video IDs, channel, title, and format may legitimately differ across authoring and production. Identification now requires matching sequential s1..s156 scene IDs and at least 3 of 4 distinct history-story narration anchors (gold reserves, savings-and-loan cleanup, David Chaum, Zimbabwe note) **in both graphs**. This avoids blindly trusting a renamed video or enabling an entire usa_history channel. The global visual budget, frozen 14-layer structure and protected masters stay unchanged.

## Production routing update

The multi-source asset engine could previously discover and cache an archival image, then discard it because the visual budget allocated the corresponding scene to stock. The live b-roll resolver now makes a **finance-long-form-only exception**:

- Author-intended sourced data charts remain chart scenes, even if a generic visual budget would demote them. These require actual numerical data points and source attribution.
- Already-selected licensed archival media may override stock if it passes the original asset engine's commercial license check plus relevance, specificity, confidence and matching-provenance thresholds.
- Original authored Three.js, AI cinematics and charts are exempt from the archive-over-stock override.
- No new media providers or paid API calls; only existing catalog/cache assets.
- Non-finance films and Shorts remain unaffected.

This is a source-priority/routing improvement, NOT an automatic guarantee that the picture accurately depicts an historical person. Human frame validation remains mandatory.

## Already voiced P0 Bitcoin documentary — SAFE REPAIR

Do **not** re-run the entire asset resolver on the prepared P0 graph; that risks replacing the restored 3D and cinematic assets. Use the new read-only-first utility instead.

Read-only review:

    .venv/bin/python scripts/k70_p31_evidence_repair.py \
      --graph data/finance_p0/cinematic_balanced/scene_graph_p0.json \
      --baseline data/series/bitcoin_history/ep01_f4/scene_graph.json \
      --out-dir data/finance_p31/bitcoin_review_v1

The tool outputs a repair_report.json, with lost chart IDs, qualified cached archives, scenes requiring identity review and a disk-space report. It never overwrites the original P0 graph, MP4, narration or captions.

**After** checking the original source figures, confirming disk space is sufficient, and ensuring the render job is idle:

    .venv/bin/python scripts/k70_p31_evidence_repair.py \
      --graph data/finance_p0/cinematic_balanced/scene_graph_p0.json \
      --baseline data/series/bitcoin_history/ep01_f4/scene_graph.json \
      --out-dir data/finance_p31/bitcoin_repaired_v1 --apply

The --apply command creates a **NEW** copied graph and renders only lost source-backed charts using the existing local CPU dataviz renderer. Its default disk gate is 2 GiB free. Source charts cannot be restored from a text label alone; actual authored data and attribution must be present. It does not render the complete documentary.

Outputs: repair_report.json, scene_graph_p31_repaired.json and charts/<scene>_sourced_chart.mp4 (only for qualifying lost charts).

Identity risks in s42 (Nixon address) and s82 (David Chaum) are deliberately left for manual verification instead of blindly substituting another face.

### Important pending editorial work

- s30 and s126 voiceover defects are in existing recorded speech, not repaired by changing a compliance rule; these still need selected fresh takes and synchronized captions.
- Repetitive text-card runs and crossfade monotony need editorial repair.
- Approximately 950 MB free on the reported laptop is not enough for rendering. The tool never deletes files; clear space with care while retaining masters, cached 3D and voiceover.
- A successful source graph patch is **not** a finished or visually verified Premium V2 MP4.

## Verification

    .venv/bin/python -m pytest -q tests/test_k70_p31_finance_priority.py

GitHub's P3 CI workflow has been extended to cover these regressions. Green unit tests cannot prove the laptop's actual archival image correctness or final rendered video quality.
