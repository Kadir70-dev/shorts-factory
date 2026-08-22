# Graph Report - .  (2026-08-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3410 nodes · 8471 edges · 175 communities (138 shown, 37 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 666 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ae113718`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164

## God Nodes (most connected - your core abstractions)
1. `settings()` - 197 edges
2. `VideoSpec` - 81 edges
3. `BrandTheme` - 68 edges
4. `SceneGraph` - 68 edges
5. `TopicIntelligenceRepository` - 62 edges
6. `Scene` - 61 edges
7. `TopicCandidate` - 60 edges
8. `TopicIntelligenceSettings` - 56 edges
9. `StoryboardScene` - 45 edges
10. `GeminiClient` - 45 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `StoryboardData`  [INFERRED]
  .asset_diag.py → apps/api/app/schemas/scene.py
- `main()` --calls--> `settings()`  [INFERRED]
  .provider_probe.py → apps/api/tests/topic_intelligence/conftest.py
- `Fake` --uses--> `SceneGraph`  [INFERRED]
  .timeout_test.py → apps/api/app/schemas/scene.py
- `run()` --calls--> `load_theme()`  [INFERRED]
  make_gen.py → apps/api/app/brand/theme.py
- `run()` --calls--> `load_theme()`  [INFERRED]
  scripts/produce.py → apps/api/app/brand/theme.py

## Import Cycles
- 3-file cycle: `apps/api/app/director/__init__.py -> apps/api/app/director/engine.py -> apps/api/app/director/prompts.py -> apps/api/app/director/__init__.py`

## Communities (175 total, 37 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (73): format_value(), Render a value the way a finance graphic would: abbreviated magnitudes,…, _beat_year(), build_spec(), classify(), _headline_from(), is_eligible(), Scene (+65 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (66): _ai_image(), _ai_subject(), _ai_video(), _apply_visual_snapshot(), _branded_plate(), _dedupe_real_assets(), _dispatch_scene(), _dispatch_scene_resumable() (+58 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (53): Beat, bounceIn(), Cam, cameraFor(), EASE, emphasisOf(), kenBurns(), punch() (+45 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (62): borders(), centroid(), _name(), place_index(), GeoJSON border source for the `globe_flight` Three.js template. Free and local…, `lowercase place name → source URL`, for template selection. Membership in the…, First place named in `text`, as `(name, source url)`. Longest match wins so…, Vertex mean of the ring with the LARGEST AREA — good enough to aim a camera,… (+54 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (53): APIBackend, OpenRouterBackend, OpenAI-compatible BACKUP brain via OpenRouter (failure recovery only — it is…, Uses the Anthropic Messages API with forced tool-use., _cache_dir(), Path, ai_image_generate(), _comfy_graph() (+45 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (51): get_current_user(), Require authentication under the single-trust-boundary model. Every…, require_admin(), ApiKey, datetime, SQLModel, Additive SQLModel tables for authentication., RefreshToken (+43 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (46): load_channel(), get_director(), Narration stage: local cloned voice only, with measured scene timing., JobStatus, Niche, Platform, BaseModel, Enum (+38 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (43): ChannelBrief, BaseModel, The channel brief handed to a ranker: identity, audience, editorial rules and…, CostReport, GeminiRankingResponse, GeminiTopicVerdict, BaseModel, RankedTopic (+35 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (51): _bg_chain(), _build_args(), compose(), _fx_dir(), _input_args(), _matte_dir(), _matte_oval(), _matte_passthrough() (+43 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (50): _ass_time(), build_image_overlay_chain(), caption_ass(), _caption_event(), disclaimer_filters(), ImageOverlay, intro_filters(), _keyword_index() (+42 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (35): cache_key(), _continuity_seed(), _evidence_fabrication_risk(), FluxAdapter, generate(), GeneratedAsset, prompt_spec(), provider_order() (+27 more)

### Community 11 - "Community 11"
Cohesion: 0.09
Nodes (50): _first_hit(), _image(), Real-footage VIDEO: Pexels then Pixabay (priority tiers 1+2). When `query_text`…, Real-footage PHOTO: Pexels then Pixabay (realism tier, gets Ken Burns). See…, Try each term in order (mirrors `_first_hit`'s tier fallthrough): fetch a…, _semantic_pick(), _video(), fetch() (+42 more)

### Community 12 - "Community 12"
Cohesion: 0.07
Nodes (46): from_scene(), parse_number(), Scene, Promote a beat's `stat` overlay into a single-value chart. This is the safety…, Best-effort (value, prefix, suffix) from a human string like "$3.8 billion" or…, _parsed(), decide(), Stable asset-resolver boundary; enhanced policy is opt-in and compared. (+38 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (34): Director factory. Picks the real Claude engine or the offline mock., _hft_graph(), MockDirector, SceneGraph, Offline Director. Produces a valid SceneGraph from a template WITHOUT calling…, Deterministic offline fixture for the approved HFT smoke topic., Overlay, BaseModel (+26 more)

### Community 14 - "Community 14"
Cohesion: 0.10
Nodes (33): Credibility CLASS, not a truth claim. Reddit upvotes never buy a better tier., SourceTier, approval_bundle(), audit_entry(), candidate_view(), _canonical_key_for(), decode_audit(), encode_audit() (+25 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (41): available(), _cache_dir(), _cache_path(), cosine(), embed_image_path(), embed_text(), _feature_tensor(), is_near_duplicate() (+33 more)

### Community 16 - "Community 16"
Cohesion: 0.06
Nodes (30): apply(), check(), ComplianceReport, description_block(), _match_case(), Policy, publish_checklist(), SceneGraph (+22 more)

### Community 17 - "Community 17"
Cohesion: 0.07
Nodes (27): Phase 2A — Gemini-powered finance trend intelligence. An ISOLATED package that…, ProviderStatus, The complete, persistable decision for one run., SelectionResult, Provenance: the evidence bundle that travels with a decision. The bundle…, A provider that only returns old material is degraded, not healthy., Never raises. Partial success is success., CollectionOutcome (+19 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (24): _csv(), init_ti_db(), Persistence for topic intelligence — the same SQLModel/SQLite setup the rest of…, Append to the ledger — this is what makes the topic un-reusable., Move the run's selection to another ranked candidate, keeping the per-result…, Stamp a review decision onto BOTH the candidate row and the ranking result row,…, Create the topic-intelligence tables if absent. Never alters existing ones., All reads/writes for the engine. One instance per run; sessions are short. (+16 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (39): _build_alias_patterns(), compile_markers(), detect_asset_classes(), detect_event_type(), detect_factual_state(), extract_entities(), extract_tickers(), Pattern (+31 more)

### Community 20 - "Community 20"
Cohesion: 0.07
Nodes (34): client(), job_db(), make_job(), fixture, Fixtures for the API-surface tests. Each test gets its own SQLite file and its…, Point `app.db` at a fresh SQLite file and create the Job table., TestClient over the real app, with the job store isolated. The app's lifespan…, Insert a Job row directly and return it. (+26 more)

### Community 21 - "Community 21"
Cohesion: 0.06
Nodes (31): any_channel(), broken_pool(), FakePool, pool(), fixture, Tests for /generate — validation, enqueue, idempotency, queue failure. No real…, Regression: create_pool was never closed, leaking one connection pool per…, A queued row may re-submit the same arq job id so a prior Redis outage can… (+23 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (40): All dimensions are 0-100 relative scores. `risk_penalty` is subtractive., One clustered story, pre-Gemini. Carries the deterministic truth., TopicCandidate, TopicScores, known_numbers(), Digit strings that legitimately appear in this candidate's own data., audience_relevance(), blend_gemini_scores() (+32 more)

### Community 23 - "Community 23"
Cohesion: 0.08
Nodes (39): evidence_bundle(), Any, A self-contained, JSON-serializable record of the selection decision., apply(), evaluate(), Finance safety gate — CODE-level, not prompt-level. This runs before Gemini…, Stamp every candidate with risk_flags / risk_penalty / eligibility., Post-Gemini guard: flag unsafe phrasing in a model-authored angle or hook. (+31 more)

### Community 24 - "Community 24"
Cohesion: 0.10
Nodes (38): camera_vf(), Paper Craft — camera movement for a rendered document page. Built on the same…, _checksum(), _cta_text(), _dominant_windows(), _env_expr(), _esc_path(), _ff() (+30 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (27): _Breaker, cache_get(), _cache_key(), cache_put(), _CacheEntry, circuit_state(), CircuitOpen, ProviderError (+19 more)

### Community 26 - "Community 26"
Cohesion: 0.11
Nodes (35): ease_in_out(), ease_out_cubic(), ease_out_expo(), Dependency-free 2D rasteriser (numpy) + ffmpeg encoders. Why this exists: the…, rgb(), auto_kind(), _bars(), _base_canvas() (+27 more)

### Community 27 - "Community 27"
Cohesion: 0.12
Nodes (35): get_job(), get_session(), Job, list_jobs(), SQLModel, Persistence. SQLite via SQLModel for v1 (local-first). Swap to Postgres by…, set_status(), upsert_job() (+27 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (35): apply_dedup(), check_candidate(), DedupVerdict, Existing-topic and video deduplication against the topic ledger. Two layers,…, Annotate every candidate with its dedup verdict and drop hard blocks. Also de-…, A confirmed event is materially new information relative to the forecast or…, _state_supersedes(), canonical_key() (+27 more)

### Community 29 - "Community 29"
Cohesion: 0.05
Nodes (37): dependencies, puppeteer, react, react-dom, remotion, @remotion/captions, @remotion/cli, @remotion/google-fonts (+29 more)

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (35): build_query(), cache(), cache_path(), _content_words(), _dedup(), eligible(), intent_key(), legal() (+27 more)

### Community 31 - "Community 31"
Cohesion: 0.11
Nodes (34): _aggregate_metrics(), _build_candidate(), cluster_signals(), _competition_metrics(), _cosine(), _evidence_from(), _median(), _pick_canonical() (+26 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (32): create_access_token(), verify_password(), login(), LoginRequest, make_user(), _assert_no_hashes(), _bearer(), asyncio (+24 more)

### Community 33 - "Community 33"
Cohesion: 0.09
Nodes (33): _load_font(), _metrics(), Real per-glyph advance widths, via fontTools — for deciding whether a string…, (cmap, glyph-name -> advance-width, unitsPerEm), or None if unreadable., Real rendered advance width of `text` at `size_px`, or None when the font can't…, The font file's OWN family name (`name` table ID 16, else ID 1) — NOT whatever…, real_family_name(), text_width_px() (+25 more)

### Community 34 - "Community 34"
Cohesion: 0.09
Nodes (19): BaseProvider, datetime, Protocol, Structural contract — anything with this shape is a provider., Shared plumbing: enablement, timeout, circuit state, status reporting., Feature flag only (ignores credentials)., Credentials/endpoints present., TrendProvider (+11 more)

### Community 35 - "Community 35"
Cohesion: 0.11
Nodes (27): asset_dir(), _caption_plate(), clear_cache(), _disclaimer_strip(), _endcard(), ensure_assets(), _intro_rule(), _lower_third() (+19 more)

### Community 36 - "Community 36"
Cohesion: 0.12
Nodes (31): Path, Stream an iterable of RGBA canvases/arrays straight into ffmpeg. `alpha=True`…, write_video(), cache_key(), Path, Everything the drawn pixels depend on, and nothing else. A chart is a pure…, Render one chart to an MP4 the renderer can drop in as a scene background.…, render() (+23 more)

### Community 37 - "Community 37"
Cohesion: 0.15
Nodes (29): AudioConfig, Compositor, build_master(), EncodeConfig, open_frame_writer(), probe(), Path, Encoding: render the loop once, then multiply it out to full length. This is… (+21 more)

### Community 38 - "Community 38"
Cohesion: 0.11
Nodes (28): _caption_from_words(), _from_script(), Caption, SceneGraph, Captions. Preferred path: Whisper.cpp word-level over the master VO (exact…, transcribe(), _whisper(), AudioTrack (+20 more)

### Community 39 - "Community 39"
Cohesion: 0.18
Nodes (25): GeminiClient, Thin, testable wrapper. Inject `sdk_factory` in tests to avoid the network., GeminiGroundingProvider, _FakeClient, _FakeModels, GeminiClient + Google Search grounding. The SDK is stubbed, so these run with…, A URL the model asserted but never actually grounded on is demoted., _response() (+17 more)

### Community 40 - "Community 40"
Cohesion: 0.08
Nodes (24): XProvider, brief(), datetime, Exception, fixture, Shared stubs for the topic-intelligence tests. No network, no API keys., A provider whose behaviour is fully scripted., StubProvider (+16 more)

### Community 41 - "Community 41"
Cohesion: 0.09
Nodes (24): BrandConfig, ChannelConfig, BaseModel, Path, Config system. Two layers: 1. Settings — process/infra config from env (.env).…, # NOTE: on a CPU-only laptop SD1.5 is slow; lower comfyui_steps for speed, or, # NOTE: Google AI Studio image generation needs BILLING enabled on the key —, Project root, resolved for the runtime we are actually in. Order of precedence:… (+16 more)

### Community 42 - "Community 42"
Cohesion: 0.10
Nodes (23): bloom_pass(), Per-frame compositor: relight the 4K hearth plate from the flame, then stack.…, Optional wide bloom over the finished linear frame (used for the thumbnail,…, SceneConfig, EmberField, ndarray, Rising ember particles, drawn at native 4K. Embers are the one moving element…, Normalised round falloff used as the ember sprite. (+15 more)

### Community 43 - "Community 43"
Cohesion: 0.13
Nodes (28): _cap(), _classify(), _classify_enhanced(), compare(), ComparisonReport, _decide_enhanced(), _decide_existing(), _decide_from_budget() (+20 more)

### Community 44 - "Community 44"
Cohesion: 0.23
Nodes (29): find_invented_metrics(), GeminiRanker, Numeric engagement/volume claims whose value is nowhere in our data., The ranking engine. `rank()` never raises — it returns ([], cost, warnings)…, A GeminiClient that returns canned text (or raises) without any SDK., StubGeminiClient, _candidates(), _payload() (+21 more)

### Community 45 - "Community 45"
Cohesion: 0.09
Nodes (25): _aware(), optional_auth(), datetime, FastAPI dependencies for access-token and API-key authentication., Authentication for a single trusted operator boundary. Every credential is…, Small in-process sliding-window rate limiter for authentication endpoints., AccessTokenError, decode_access_token() (+17 more)

### Community 46 - "Community 46"
Cohesion: 0.10
Nodes (18): CLIBackend, FallbackBackend, get_backend(), Director backends. Both return RAW TEXT expected to be a JSON object; the…, The primary brain (Claude CLI / API) with an OpenRouter safety net. The primary…, Pick the primary Director backend (Claude CLI by default, or the Anthropic…, Uses the local `claude` CLI on the Max plan., Director (+10 more)

### Community 47 - "Community 47"
Cohesion: 0.16
Nodes (29): get(), approve_review(), candidate_detail(), candidates(), collect(), override_duplicate_review(), providers_status(), BaseModel (+21 more)

### Community 48 - "Community 48"
Cohesion: 0.12
Nodes (25): _asset_priority(), _asset_priority_for_channel(), _company(), _emotion(), _entities(), generate_semantic(), _location(), Scene (+17 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (24): Brand package — the permanent visual identity of the channel. Four modules,…, BrandManager, BrandValidation, SceneGraph, Phase 7 central Brand Manager. This extends the established YAML/theme path; it…, One entry point shared by renderers and generation engines., theme_for(), validate() (+16 more)

### Community 50 - "Community 50"
Cohesion: 0.11
Nodes (20): extract_grounding_chunks(), GeminiBudgetExceeded, GeminiResponse, GeminiUnavailable, _load_sdk(), next_day_start(), parse_json_response(), Any (+12 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (24): FlameFrame, Flame, smoke and fire-light simulation — the only per-frame heavy work. Model…, blur(), box_blur_1d(), ndarray, ramp(), Small, dependency-free image maths: separable blur, upscale, colour ramps.…, Piecewise-linear colour ramp. `x` is (H, W); returns (H, W, 3) float32. Used… (+16 more)

### Community 52 - "Community 52"
Cohesion: 0.15
Nodes (24): cache_key(), dimensions(), map_template(), MotionSpec, Path, Scene, SceneGraph, Validated finance templates extending the existing numpy/FFmpeg motion path. (+16 more)

### Community 53 - "Community 53"
Cohesion: 0.20
Nodes (27): SceneGraph, synthesize(), batch_kokoro(), batch_piper(), _cache_dir(), cache_key(), cache_lookup(), cache_store() (+19 more)

### Community 54 - "Community 54"
Cohesion: 0.18
Nodes (26): CompletedProcess, _clipped_fraction(), collect(), _duration(), load_manifest(), main(), _measure(), _noise_floor() (+18 more)

### Community 55 - "Community 55"
Cohesion: 0.11
Nodes (19): Applied, apply(), Dictionary, find_untranslated(), _Guard, load(), _lower_keys(), _merge() (+11 more)

### Community 56 - "Community 56"
Cohesion: 0.10
Nodes (21): _attach_evidence(), build_topic_prompt(), build_video_spec(), enqueue_topic(), Any, The ONE seam into the existing production pipeline. A selected topic becomes a…, Store the evidence bundle on the job's metadata_json. Additive: it writes only…, The topic string the Director receives. Deliberately a rich, single line: the… (+13 more)

### Community 57 - "Community 57"
Cohesion: 0.09
Nodes (11): build_providers(), Instantiate every provider. Disabled/unconfigured ones are still returned so…, BaseSettings, field_validator, TopicIntelligenceSettings, _FakeTypes, GenerateContentConfig, GoogleSearch (+3 more)

### Community 58 - "Community 58"
Cohesion: 0.13
Nodes (23): _clear_cache(), fixture, parametrize, Voice identity: the profile, the cascade lock, and speakable-text conversion.…, Build a profile file and point the loader at it., Blanket letter-spacing would wreck NASA and OPEC, so `say_as` is an explicit…, Captions and overlays must keep "$4.2B" while the voice says the words., The point of the lock: falling back changes FIDELITY, never who is speaking.… (+15 more)

### Community 59 - "Community 59"
Cohesion: 0.18
Nodes (11): Canvas, ndarray, Annulus arc. `start`/`sweep` are turns (0..1), 0 = 12 o'clock, CW — the…, Thick line segment (capsule SDF)., Soft fill between a polyline and a baseline — the 'financial chart' gradient…, Straight-alpha RGBA canvas. Premultiplication is avoided so a caller can read…, Source-over one coverage tile at (x0, y0)., Clipped pixel-centre coordinate grid for a bbox, or None if off-canvas. (+3 more)

### Community 60 - "Community 60"
Cohesion: 0.14
Nodes (20): _load_progress(), _progress_path(), Read-modify-write, no `await` between read and write — safe under the single-…, A snapshot with no asset_path (a `solid`/no-op outcome) is always reusable; one…, _save_progress_entry(), _snapshot_is_reusable(), _minimal_graph_json(), asyncio (+12 more)

### Community 61 - "Community 61"
Cohesion: 0.15
Nodes (18): generation_job_view(), Read model + the five review actions. Framework-free on purpose., Live view of the EXISTING render Job linked by Phase 2B approval., review_status(), TopicReviewService, asyncio, Focused Phase 2B -> existing generation pipeline integration tests., test_approval_response_links_existing_generation_job() (+10 more)

### Community 62 - "Community 62"
Cohesion: 0.16
Nodes (19): Voice identity — the channel's narrator. Kokoro CANNOT clone a voice. It is a…, _decade_words(), _decimal_words(), has_clone(), _int_words(), load_profile(), _money(), profile_path() (+11 more)

### Community 63 - "Community 63"
Cohesion: 0.17
Nodes (15): Path, Strict orchestration for local cloned-voice synthesis., VoiceManager, inspect(), Path, RuntimeError, QAResult, Fast, dependency-free gates for synthesized narration. (+7 more)

### Community 64 - "Community 64"
Cohesion: 0.13
Nodes (21): fresh_config(), fixture, Regression tests for runtime project-root resolution. Guards the bug where…, Belt and braces: no setting may carry /repo on a local checkout., Reimport app.config with a clean env and no cached settings()., Local WSL: root is the checkout, never /repo., The values the pipeline actually uses stay inside the project dir., The regression itself: the resolved data dir must be usable, not /repo. (+13 more)

### Community 65 - "Community 65"
Cohesion: 0.17
Nodes (20): Minimal zlib PNG writer, used for proof frames and the thumbnail. Pillow is not…, write_png(), add_red_circle(), add_stamp(), age(), _fold_shadows(), _grain(), _load_png() (+12 more)

### Community 66 - "Community 66"
Cohesion: 0.18
Nodes (20): AnimationType, ASPECT_PRESETS, BackgroundMode, clickById(), closestAspect(), configureAnimation(), configureBackground(), configureExportSettings() (+12 more)

### Community 67 - "Community 67"
Cohesion: 0.16
Nodes (19): _bed_shape(), _circular_filtered_noise(), _grain_bank(), _pop_bank(), ndarray, Path, Original fireplace audio: a seamless, exactly-periodic stereo crackle bed.…, Rarer, lower, woodier thumps — the occasional loud crack in a log. (+11 more)

### Community 68 - "Community 68"
Cohesion: 0.16
Nodes (19): character_prompt(), CharacterRef, get_or_create(), _load(), BaseModel, Path, Reusable CHARACTER MEMORY (Phase 2) — the fix for cross-scene consistency.…, A locked, reusable character. First definition wins (so it never drifts). (+11 more)

### Community 69 - "Community 69"
Cohesion: 0.17
Nodes (19): add_music(), bed_path(), build_envelope(), choose_bed(), ensure_beds(), MusicPreset, Path, SceneGraph (+11 more)

### Community 70 - "Community 70"
Cohesion: 0.12
Nodes (19): ai_video_generate(), build_video_prompt(), clamp_i2v_seconds(), clamp_insert_seconds(), Picsart image-to-video clips are 3–5s ONLY — clamp any requested duration., Premium AI inserts are 1–3s ONLY — clamp any requested duration., The cinematic prompt sent to Pika for a beat (also used by verification to show…, Generate a short (1–3s) cinematic insert. Prefers Pika (fal.ai), then the gated… (+11 more)

### Community 71 - "Community 71"
Cohesion: 0.18
Nodes (18): _atoms_faststart(), _filter_log(), format_production_report(), _fps(), _g(), _media_probe(), _numbers(), production_analyze() (+10 more)

### Community 72 - "Community 72"
Cohesion: 0.18
Nodes (12): _ahash(), _cache_path(), _comfy_pid(), main(), main_async(), _probe(), _prompt(), ndarray (+4 more)

### Community 73 - "Community 73"
Cohesion: 0.15
Nodes (14): Story structure library + rotation. The old pipeline had ONE shape: a fixed 4–7…, What the rotation decided, carried through the pipeline for logging., Stable per-video seed. Reproducible renders matter: the same short must rebuild…, seed_for(), StructureChoice, _pick(), plan(), Random (+6 more)

### Community 74 - "Community 74"
Cohesion: 0.18
Nodes (12): Octave, PeriodicFBM, ndarray, Tileable, exactly-periodic 3-D value noise (the loop's core invariant). The…, Per-octave x gather indices + weights. Fixed for the whole render., Bilinear sample of one z-slice onto the output grid., Contrast-normalised fBm for `frame`: mean 0.5, std 0.25, unclipped., fBm for `frame`, shape (height, width), before contrast normalisation. (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.16
Nodes (17): _cgroup_limit_mb(), changed_scenes(), detect_resources(), graph_cache_report(), preview_manifest(), QueueResult, Phase 9 resource-aware orchestration for the existing production pipeline. This…, Promote only changed/never-approved scenes; final composition and QA stay… (+9 more)

### Community 76 - "Community 76"
Cohesion: 0.20
Nodes (18): allocate(), audit_unused(), Band, eligibility(), _has_data(), _improve(), Policy, Path (+10 more)

### Community 77 - "Community 77"
Cohesion: 0.11
Nodes (17): compilerOptions, module, moduleResolution, noEmit, outDir, extends, include, compilerOptions (+9 more)

### Community 78 - "Community 78"
Cohesion: 0.17
Nodes (17): choose(), library(), Pick the structure for one short. `forced` (e.g. a preset pinning a structure)…, Most-recent-first list of the last picks for one dimension., recent(), Story structure rotation and the variety planner. The property these tests…, test_choice_is_deterministic_for_a_video(), test_every_structure_is_usable() (+9 more)

### Community 79 - "Community 79"
Cohesion: 0.17
Nodes (17): available(), cache_key(), close_worker(), _ensure_worker(), _find_chrome(), _paperima_version(), Process, Local adapter for Paperima (github.com/nurimator/paperima, AGPL-3.0-only,… (+9 more)

### Community 80 - "Community 80"
Cohesion: 0.15
Nodes (15): NOTE: a bundle-once warm service can only serve assets that exist in the public, server, aggregateRssMb(), ensurePage(), handle(), handleInternal(), Region, renderFlat() (+7 more)

### Community 81 - "Community 81"
Cohesion: 0.15
Nodes (13): _fc_match(), FontFace, GradeVariant, _is_variable(), _looks_bold(), BrandTheme — config/brand/<id>.yaml parsed into something the renderer can use.…, Filesystem fallback — also the path that finds static Bold faces that…, First installed face from the preference list → (file path, family name). Both… (+5 more)

### Community 82 - "Community 82"
Cohesion: 0.21
Nodes (14): Assignment, parametrize, Tests for the plan-vs-delivery QA gate (OpenMontage-audit gap #3).…, rows: [(scene_id, planned_channel, delivered_channel), ...], _report(), test_analyze_fails_above_the_downgrade_threshold(), test_analyze_passes_below_the_downgrade_threshold(), test_falling_to_unresolved_is_always_silent() (+6 more)

### Community 83 - "Community 83"
Cohesion: 0.23
Nodes (10): classify_source(), host_of(), Host-based tiering. Social providers are pinned to `social` regardless of…, FinanceNewsProvider, _parse_date(), datetime, Finance news connector — configurable RSS feeds and/or NewsAPI. RSS is parsed…, Normalized-title hash. Identical wire copy across outlets -> same group. (+2 more)

### Community 84 - "Community 84"
Cohesion: 0.21
Nodes (10): EconomicEvent, A scheduled macro event. Values are OPTIONAL and stay None when the provider…, _affected(), EconomicCalendarProvider, _importance(), _parse_dt(), datetime, Economic-calendar connector — a vendor ABSTRACTION, not a hardcoded provider.… (+2 more)

### Community 85 - "Community 85"
Cohesion: 0.22
Nodes (12): _cpu_s(), _dump_graph(), _grounding_summary(), _load_graph(), _load_preset(), main(), Path, RamSampler (+4 more)

### Community 86 - "Community 86"
Cohesion: 0.15
Nodes (12): apply(), freeze(), Path, SceneGraph, Pin this job's dice roll to disk., The pinned plan for an existing job, or None to draw a fresh one. Re-rendering…, Write the plan onto the scenes. Respects what the Director deliberately…, One short's creative dice roll. Serialised onto the SceneGraph. (+4 more)

### Community 87 - "Community 87"
Cohesion: 0.14
Nodes (8): _dt(), datetime, Low-level ledger append for the review workflow, which works from persisted…, Every ledger row for one story, whichever run produced it. This is how…, Total estimated Gemini spend since `since` — the daily budget guard., SQLite round-trips naive datetimes; normalize everything to aware UTC., What this channel has ALREADY committed to — the dedup memory. One row per…, TopicLedger

### Community 88 - "Community 88"
Cohesion: 0.13
Nodes (14): compilerOptions, esModuleInterop, jsx, lib, module, moduleResolution, skipLibCheck, strict (+6 more)

### Community 89 - "Community 89"
Cohesion: 0.25
Nodes (13): _ahash(), _as_coro(), _consistency_pct(), _cpu_seconds(), _ffprobe(), main(), ndarray, Path (+5 more)

### Community 90 - "Community 90"
Cohesion: 0.35
Nodes (14): generate_script(), import_mobile_recording(), install_models_and_engines(), install_uv(), main(), open_recording_script(), _probe_source(), Path (+6 more)

### Community 91 - "Community 91"
Cohesion: 0.20
Nodes (12): bootstrap_admin(), main(), Create the first administrator without exposing credentials in shell output., init_auth_db(), Create only auth tables; never inspect or alter existing tables., hash_password(), auth_client(), auth_db() (+4 more)

### Community 92 - "Community 92"
Cohesion: 0.22
Nodes (13): add_sound_design(), build_cues(), ensure_pack(), Path, SceneGraph, Sound design stage — MICRO-EDITING / RETENTION SFX. Two jobs: 1.…, Pipeline stage: ensure the SFX pack exists and attach the cue list. Runs after…, Synthesize any missing SFX files (idempotent). Failures are swallowed — a… (+5 more)

### Community 93 - "Community 93"
Cohesion: 0.22
Nodes (7): Check, main(), build(), main(), Path, Assemble takes until the target minutes are covered, keeping block balance., write_session()

### Community 94 - "Community 94"
Cohesion: 0.21
Nodes (3): CacheCoordinator, CacheStats, test_safe_cache_pruning_keeps_nonreproducible()

### Community 95 - "Community 95"
Cohesion: 0.26
Nodes (11): cooldown_weights(), _load(), _path(), Cross-upload ROTATION LEDGER — the memory that stops the channel from looking…, Atomic write so a crash mid-render can't leave a truncated ledger., Push one pick onto the front of a dimension's history., Record several dimensions in ONE read-modify-write (the render path)., Multiplier per option from how recently it was used. The most recent pick is… (+3 more)

### Community 96 - "Community 96"
Cohesion: 0.32
Nodes (11): profile(), asyncio, test_browser_worker_restarts_at_job_threshold(), test_cache_key_lock_deduplicates_concurrent_work(), test_checkpoint_resume_rejects_stale_or_modified_output(), test_memory_floor_applies_backpressure(), test_optimizer_defaults_off(), test_resumable_stage_loads_valid_checkpoint() (+3 more)

### Community 97 - "Community 97"
Cohesion: 0.24
Nodes (10): available(), _module(), Scene, SceneGraph, Bridge to the Fashion Visualization Engine. The engine is FROZEN and channel-…, Import the fashion_viz package standalone, or return None. It is imported as a…, The (module, params) a scene asked for, or None. Accepts `fashionviz:<module>`…, Render every fashion-viz beat. Returns {scene_id: provenance dict}. Runs before… (+2 more)

### Community 98 - "Community 98"
Cohesion: 0.40
Nodes (5): CheckpointStore, Path, resumable_stage(), End-to-end glue check: a stage wrapped through `_stage_op` + `resumable_stage`…, test_resumable_stage_skips_the_second_call_via_stage_op()

### Community 99 - "Community 99"
Cohesion: 0.22
Nodes (9): Check, format_report(), plan_vs_delivery(), PlanVsDelivery, BaseModel, QAReport, One-block human readout of a QA report (for logs / the CLI harness)., One scene's planned-vs-delivered outcome. `silent` is the flag this whole check… (+1 more)

### Community 100 - "Community 100"
Cohesion: 0.27
Nodes (10): _collect(), main(), _parser(), _rank(), CLI: python -m app.topic_intelligence collect --channel usa_trading python -m…, _run(), _status(), One-screen human summary — printed by the CLI, logged by the API. (+2 more)

### Community 101 - "Community 101"
Cohesion: 0.42
Nodes (10): graph_with(), precise_scene(), Scene, SceneGraph, spec(), test_comparison_is_read_only_and_reports_cost(), test_disabled_public_path_is_identical_to_existing_policy(), test_enhanced_path_uses_precise_authored_subject() (+2 more)

### Community 102 - "Community 102"
Cohesion: 0.33
Nodes (7): _assets(), _cpu_s(), main(), RamSampler, _recommend(), run(), _run_one()

### Community 103 - "Community 103"
Cohesion: 0.33
Nodes (10): _decisions_only(), _full_render(), main(), main_async(), _mix(), _print_decisions(), Run the engine WITHOUT downloading assets, plus AI-on vs all-real retention., One full pipeline run → MP4, with a stage-timed readout and mix. (+2 more)

### Community 104 - "Community 104"
Cohesion: 0.22
Nodes (5): Beat, Fit the beat list to a scene count by growing/shrinking the middle., Beat roles that should carry a real animated data visualisation., The structure rendered as Director instructions. Beats are mapped onto the…, Structure

### Community 105 - "Community 105"
Cohesion: 0.22
Nodes (10): analyze(), _black_seconds(), _probe(), Average luma (0..255) of the frame at `at` seconds, or -1 on failure., Total seconds flagged as (near-)black by ffmpeg blackdetect, or -1.0 if the…, Run the full QA audit on a finished short. Pure I/O on the file + metrics;…, _stream_types(), _yavg() (+2 more)

### Community 106 - "Community 106"
Cohesion: 0.31
Nodes (6): apply(), BudgetReport, measure(), SceneGraph, Write the allocation onto the graph so the resolver honours it.…, The DELIVERED mix, classified from what actually resolved on disk. Deliberately…

### Community 107 - "Community 107"
Cohesion: 0.27
Nodes (9): Test hook — the breaker is process-global by design., reset_cache(), reset_circuits(), fixture, Global test setup. Every test runs with NO real API keys and NO network. The…, Circuit breakers and the HTTP cache are process-global by design., A repository backed by a fresh SQLite file per test., _reset_module_state() (+1 more)

### Community 108 - "Community 108"
Cohesion: 0.36
Nodes (9): _delivered_report(), main(), _probe(), Path, MD5 of the VIDEO bitstream alone — demuxed, never decoded (~0.1s). This is the…, The QA report for the packaged file. Reuses produce.py's persisted audit when…, run(), _srt_time() (+1 more)

### Community 109 - "Community 109"
Cohesion: 0.33
Nodes (8): chat(), enabled(), enhance_image_prompt(), log(), OpenRouter — OPTIONAL backup / augmentation provider. NEVER the primary brain.…, True iff an OpenRouter key is configured. Logs '[openrouter] enabled' once., One OpenAI-compatible chat completion via OpenRouter. Returns the assistant…, Sharpen an AI-image subject line via the cheap backup model. BEST-EFFORT:…

### Community 110 - "Community 110"
Cohesion: 0.22
Nodes (5): EngineBinding, Ready NON-cloning engines. A different speaker from the enrolled identity, so…, Why each engine is or isn't available — the message a user needs when the…, How one engine holds this voice., Is this binding usable right now → (ok, why not).

### Community 111 - "Community 111"
Cohesion: 0.36
Nodes (7): main(), peak_child_rss_mb(), build(), fallback_2d(), main(), Path, SAFE 2D MAP — same rings, same flight, no GPU. Equirectangular projection…

### Community 112 - "Community 112"
Cohesion: 0.42
Nodes (8): bundle(), has_cuda(), has_piper_train(), main(), Path, Zip the dataset for upload., train_locally(), write_notebook()

### Community 113 - "Community 113"
Cohesion: 0.29
Nodes (7): payload_from_query(), Path, Parametric Manim templates. We do NOT let Claude write Manim code (unsafe +…, v1 heuristic: 'bar' in query -> bar chart, else line. Real numbers should come…, render_chart(), manim_render(), Render a chart via a vetted parametric template (no LLM codegen).

### Community 114 - "Community 114"
Cohesion: 0.43
Nodes (4): StageScheduler, execute(), main(), Path

### Community 115 - "Community 115"
Cohesion: 0.43
Nodes (7): _duration(), _loudness(), main(), _only(), Path, A copy of the profile exposing exactly one engine., run()

### Community 116 - "Community 116"
Cohesion: 0.43
Nodes (5): estimate(), main(), Director-side duration estimate. Overwritten by measured TTS at render., write_narration(), write_timeline()

### Community 117 - "Community 117"
Cohesion: 0.33
Nodes (3): Limit attempts in one process. This limiter is intentionally dependency-free…, Clear recorded attempts, primarily for isolated application tests., SlidingWindowLimiter

### Community 118 - "Community 118"
Cohesion: 0.33
Nodes (4): BaseSettings, The effective HF token from either supported env name (HF_TOKEN wins)., True when the narration→visual grounding lock is active (any of the three…, Settings

### Community 119 - "Community 119"
Cohesion: 0.47
Nodes (3): Any, field_validator, Gemini occasionally emits 0-1 floats, strings, or out-of-range values. Coerce…

### Community 120 - "Community 120"
Cohesion: 0.33
Nodes (5): MKL_NUM_THREADS, OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, PYTORCH_NO_CUDA_MEMORY_CACHING, comfyui_cpu.sh script

### Community 121 - "Community 121"
Cohesion: 0.70
Nodes (4): _cached_color(), _define_color(), main(), Scribus-side runner. Executed BY Scribus's embedded interpreter (`scribus -g…

### Community 122 - "Community 122"
Cohesion: 0.60
Nodes (4): _ago(), _ahead(), datetime, Realistic fixture signals covering the seven scenarios the phase must handle:…

### Community 123 - "Community 123"
Cohesion: 0.50
Nodes (4): _ahash(), consistency_pct(), 64-bit average hash via ffmpeg 8x8 gray (no PIL). Returns list[int] or None., Average-hash similarity % between two image/frame files (-1 if unprobeable).

### Community 124 - "Community 124"
Cohesion: 0.67
Nodes (4): Path, SceneGraph, _render_cli(), render_remotion()

### Community 125 - "Community 125"
Cohesion: 0.67
Nodes (3): main(), Measure which FREE asset providers actually work, and how slow each one is., timed()

## Knowledge Gaps
- **111 isolated node(s):** `.aiprog.sh script`, `.confirm.sh script`, `.frames.sh script`, `.go.sh script`, `.kill.sh script` (+106 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `settings()` connect `Community 4` to `Community 0`, `Community 1`, `Community 3`, `Community 5`, `Community 6`, `Community 8`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 15`, `Community 24`, `Community 27`, `Community 30`, `Community 32`, `Community 35`, `Community 36`, `Community 37`, `Community 38`, `Community 40`, `Community 41`, `Community 43`, `Community 45`, `Community 46`, `Community 48`, `Community 49`, `Community 52`, `Community 53`, `Community 57`, `Community 60`, `Community 68`, `Community 69`, `Community 70`, `Community 71`, `Community 72`, `Community 75`, `Community 79`, `Community 85`, `Community 89`, `Community 91`, `Community 92`, `Community 95`, `Community 96`, `Community 97`, `Community 98`, `Community 101`, `Community 102`, `Community 105`, `Community 108`, `Community 109`, `Community 113`, `Community 114`, `Community 117`, `Community 124`, `Community 125`?**
  _High betweenness centrality (0.191) - this node is a cross-community bridge._
- **Why does `TopicIntelligenceSettings` connect `Community 57` to `Community 34`, `Community 4`, `Community 39`, `Community 7`, `Community 40`, `Community 44`, `Community 14`, `Community 17`, `Community 50`, `Community 23`, `Community 25`, `Community 28`, `Community 61`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `VideoSpec` connect `Community 6` to `Community 1`, `Community 3`, `Community 10`, `Community 12`, `Community 13`, `Community 21`, `Community 27`, `Community 43`, `Community 46`, `Community 48`, `Community 52`, `Community 53`, `Community 56`, `Community 61`, `Community 72`, `Community 85`, `Community 89`, `Community 101`, `Community 102`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 194 inferred relationships involving `settings()` (e.g. with `optional_auth()` and `.check()`) actually correct?**
  _`settings()` has 194 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `VideoSpec` (e.g. with `FakePool` and `Adapter`) actually correct?**
  _`VideoSpec` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `BrandTheme` (e.g. with `BrandManager` and `BrandValidation`) actually correct?**
  _`BrandTheme` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `SceneGraph` (e.g. with `main()` and `main()`) actually correct?**
  _`SceneGraph` has 22 INFERRED edges - model-reasoned connections that need verification._