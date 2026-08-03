"""
Config system. Two layers:
  1. Settings  — process/infra config from env (.env). Secrets live here.
  2. Channel   — per-channel creative + branding config from YAML.

Multi-channel is config-driven: drop a new file in config/channels/ and it
exists. No code change to add "usa_finance_v2".
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_FILE = Path(__file__).resolve()

# Container fallback root. In the image, `app/` is COPYed to /app/app (see
# apps/api/Dockerfile), so the source checkout is NOT present and config/ + data/
# arrive only as Compose bind mounts under /repo.
_CONTAINER_ROOT = Path("/repo")


def _resolve_root() -> Path:
    """Project root, resolved for the runtime we are actually in.

    Order of precedence:
      1. PROJECT_ROOT — explicit override, always wins (any runtime).
      2. Source checkout — <root>/apps/api/app/config.py, detected by walking up
         and confirming the sibling `apps/` directory exists. This is local WSL /
         bare-metal dev, where the root is wherever the repo was cloned.
      3. /repo — the Docker Compose mount root, used when the checkout layout is
         absent (i.e. inside the image, where config.py lives at /app/app/).

    Never hardcodes a user path and never invents /repo on a local box.
    """
    override = os.getenv("PROJECT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if len(_CONFIG_FILE.parents) > 3:
        candidate = _CONFIG_FILE.parents[3]     # <root>/apps/api/app/config.py
        if (candidate / "apps").is_dir():       # real source checkout
            return candidate

    return _CONTAINER_ROOT


ROOT = _resolve_root()
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM (Director Brain) ---
    anthropic_api_key: str = ""
    director_model: str = "claude-opus-4-8"
    director_max_tokens: int = 8000

    # --- OpenRouter (OPTIONAL backup / augmentation provider) ---
    # NEVER the primary brain — Claude CLI (Claude Max) stays the default Director.
    # OpenRouter is wired only as a cheap, OpenAI-compatible fallback for: (a) AI
    # image-prompt enhancement, (b) backup LLM routing, (c) failure recovery when
    # the Claude CLI director crashes outright. If `openrouter_api_key` is blank the
    # whole layer is a SILENT no-op and the pipeline behaves exactly as before.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"     # default cheap backup model

    # --- Local cloned-voice TTS --------------------------------------------- #
    # Chatterbox -> Apache-2.0 OpenF5 -> the host's fine-tuned Piper model.
    # Model identity and paths are pinned in config/voice/profile.yaml.
    tts_models_dir: Path = DATA_DIR / "models"
    piper_bin: str = ""

    # --- assets ---
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # --- premium video (gated) ---
    veo3_api_key: str = ""
    seedance_api_key: str = ""

    # --- Pika Labs cinematic AI VIDEO inserts (Phase 5.7) ---
    # Short (1–3s) cinematic clips for PREMIUM documentary beats only — history
    # recreations, political symbolism, election atmosphere, impossible camera
    # shots, dark history, abstract economy metaphors. NEVER replaces real footage:
    # the decision engine caps Pika at ~15–20% of the timeline and EVERY Pika beat
    # falls back to real footage (Pexels/Pixabay) if generation fails or no key is
    # set — so the pipeline never breaks and costs nothing unless PIKA_API_KEY is
    # configured. Pika is served via fal.ai's async queue (the official path); set
    # PIKA_API_KEY to a fal key. PIKA_API_BASE/PIKA_MODEL let you retarget another
    # Pika-compatible host (Pollo, 302.ai, etc.) without code changes.
    # MASTER SWITCH for ALL AI-video generation (Pika/Veo3/Seedance). OFF by
    # default → the pipeline is a stable, CPU-friendly local shorts factory:
    # local AI images + real footage + ffmpeg cinematic motion, NO AI video.
    # The scene director never allocates an ai_video beat and ai_video_generate()
    # refuses immediately, so every beat resolves to an image or real footage.
    ai_video_enabled: bool = False
    pika_api_key: str = ""                              # fal.ai key (Authorization)
    pika_api_base: str = "https://queue.fal.run"        # fal async-queue host
    pika_model: str = "fal-ai/pika/v2.2/text-to-video"  # text→video endpoint path
    pika_resolution: str = "720p"                       # 720p = faster/cheaper
    pika_aspect_ratio: str = "9:16"                     # vertical Shorts framing
    pika_poll_seconds: float = 6.0                      # queue poll interval
    pika_max_wait_seconds: float = 240.0               # give up → real footage

    # --- Picsart image-to-video (NEW, opt-in cinematic motion) ----------------- #
    # Animates a still the LOCAL ComfyUI already generated into a short (3–5s)
    # cinematic clip via Picsart's GenAI API — for HERO / high-emotion / anime /
    # dramatic beats only. Fully additive and OFF by default: with
    # ENABLE_IMAGE_TO_VIDEO=0 (the default) the scene director never allocates an
    # ai_video beat and the resolver never calls Picsart, so the pipeline behaves
    # EXACTLY as before. When ON, the same image-first → still+Ken-Burns fallback
    # the AI-image path already uses is the safety net: a missing PICSART_API_KEY
    # or ANY generation failure degrades to the still (then real footage) — never
    # breaks the render. Endpoint: POST {base}{path} with header X-Picsart-API-Key;
    # returns 202 + an inference id, polled until a video URL is ready.
    #   AI_VIDEO_PROVIDER selects the engine ("picsart" = image→video via Picsart;
    #   anything else keeps the legacy Pika text→video path in providers.py).
    enable_image_to_video: bool = False             # ENABLE_IMAGE_TO_VIDEO master switch
    ai_video_provider: str = "picsart"              # config-driven engine select
    picsart_api_key: str = ""                       # X-Picsart-API-Key header
    picsart_api_base: str = "https://genai-api.picsart.io"
    picsart_i2v_path: str = "/v1/image2video"       # image-to-video endpoint path
    picsart_model: str = "wan-2.7"                  # cheap default for most beats
    # OPTIONAL quality override for the single HERO beat (highest-emotion ai_video
    # scene per short). Blank → every clip uses picsart_model. Set to a premium
    # model (e.g. "veo-3.1-fast") to spend extra ONLY on the hero shot. Friendly
    # names are resolved to Picsart model URNs in providers.py (unknown values pass
    # through unchanged, so a full URN works too).
    picsart_hero_model: str = ""                    # PICSART_HERO_MODEL (optional)
    picsart_quality: str = "480p"                   # 480p/720p/1080p; 480p = laptop-friendly
    picsart_length_s: float = 4.0                   # target clip length (clamped 3–5s)
    picsart_audio: bool = False                     # request an audio track (usually off)
    picsart_poll_seconds: float = 5.0              # status poll interval
    picsart_max_wait_seconds: float = 240.0        # give up → still / real footage
    # Hard cap on Picsart clips per short (cost/CPU guard). Even if more beats are
    # AI-eligible, only the highest-emotion `max_ai_video_scenes` get a clip.
    max_ai_video_scenes: int = 2                    # MAX_AI_VIDEO_SCENES

    # --- Local ComfyUI image backend (CPU/GPU on THIS machine) ----------------- #
    # PRIMARY image generator when enabled: a LOCAL ComfyUI instance (default
    # http://127.0.0.1:8188) running a plain text→image SD1.5 graph on the
    # DreamShaper_8_pruned checkpoint. Generated stills are saved into the SAME
    # content-addressed cache the other providers use, so all downstream editing
    # (Ken Burns / ffmpeg motion) is unchanged. comfyui_mode is informational
    # ("local" / "remote") — the provider just talks to comfyui_base_url. If
    # COMFYUI_ENABLED=0, ComfyUI isn't running, or generation fails for ANY reason,
    # ai_image_generate() cleanly falls through to the existing chain (Google AI
    # Studio → HuggingFace FLUX → Pollinations → real footage) — never breaks.
    # NOTE: on a CPU-only laptop SD1.5 is slow; lower comfyui_steps for speed, or
    # leave ComfyUI off and let the free Pollinations tier serve AI stills.
    comfyui_enabled: bool = False                 # COMFYUI_ENABLED=1 to turn on
    comfyui_mode: str = "local"                   # "local" (this machine) / "remote"
    # Local ComfyUI API. Reads either COMFYUI_BASE_URL (original) or COMFYUI_URL
    # (alias) — COMFYUI_BASE_URL wins if both are set. Backward compatible.
    comfyui_base_url: str = Field(
        "http://127.0.0.1:8188",
        validation_alias=AliasChoices("COMFYUI_BASE_URL", "COMFYUI_URL"),
    )
    comfyui_timeout: int = 1200                   # seconds: submit + poll + fetch
    #   NOTE: on a GPU-less i5, an 8-step LCM 512x768 still is ~10-12 min (650-900s+),
    #   so the budget must clear ~1200s+. Keep the model RESIDENT (launch ComfyUI
    #   WITHOUT --disable-smart-memory) to avoid a ~2min model reload every image.
    comfyui_checkpoint: str = "DreamShaper_8_pruned.safetensors"
    comfyui_width: int = 512                      # SD1.5 native-ish; renderer crops 9:16
    comfyui_height: int = 896                     # ~9:16 vertical
    comfyui_steps: int = 25
    comfyui_cfg: float = 7.0
    comfyui_sampler: str = "dpmpp_2m"
    comfyui_scheduler: str = "karras"
    comfyui_poll_seconds: float = 2.0             # /history poll interval

    # --- CPU-first LCM optimization (Phase 1 — opt-in, default OFF) ----------- #
    # On a GPU-less i5/12GB box the stock 25-step graph is ~3-5 min/image. With an
    # LCM-LoRA the same DreamShaper checkpoint generates a usable still in ~8 steps
    # (~35-60s on CPU). COMFYUI_LCM=1 inserts a LoraLoaderModelOnly node and swaps
    # the sampler/steps/cfg to the LCM-tuned values below — WITHOUT disturbing the
    # standard path (when OFF, _comfy_graph is byte-identical to before). Drop
    # lcm-lora-sdv1-5.safetensors in ComfyUI's models/loras/.
    comfyui_lcm: bool = False                     # COMFYUI_LCM=1 → 8-step LCM path
    comfyui_lcm_lora: str = "lcm-lora-sdv1-5.safetensors"
    comfyui_lcm_strength: float = 1.0
    comfyui_lcm_steps: int = 8                    # LCM needs only ~6-10 steps
    comfyui_lcm_cfg: float = 2.0                  # LCM wants low cfg (1.5-2.5)
    comfyui_lcm_sampler: str = "lcm"
    comfyui_lcm_scheduler: str = "sgm_uniform"
    # Tiled VAE decode — lower peak RAM (good for 12GB). OFF = stock VAEDecode.
    comfyui_vae_tiled: bool = False
    comfyui_vae_tile_size: int = 512
    # Optional negative-prompt override for ComfyUI ONLY. Blank → the global photoreal
    # AI_IMAGE_NEGATIVE (which bars cartoon/anime/3d). Set this for an ANIME/CARTOON
    # checkpoint so the negative doesn't fight the very style you want. Other
    # providers (Google/HF/Pollinations) are unaffected.
    comfyui_negative: str = ""

    # --- premium AI documentary IMAGES (Phase 5.6) ---
    # FREE-FIRST, Google AI Studio ONLY. Set GOOGLE_API_KEY (free AI Studio key).
    # OpenAI is NOT used for images. If the key is missing or generation fails the
    # resolver falls back to real footage (Pexels/Pixabay) — never breaks.
    google_api_key: str = ""                          # Google AI Studio key
    google_image_model: str = "gemini-2.5-flash-image"    # Gemini image (primary)
    google_imagen_model: str = "imagen-4.0-generate-001"  # Imagen fallback
    # NOTE: Google AI Studio image generation needs BILLING enabled on the key —
    # the free tier is 0 image requests (Imagen is "paid plans only", Gemini-image
    # free-tier limit is 0). With a billing-enabled key these models work as wired;
    # otherwise every AI beat cleanly falls back to real footage (Pexels/Pixabay).
    # Pollinations — FREE image generation (no key), used as the fallback when
    # Google is unavailable (billing off) or fails. Keeps real AI images flowing
    # for free. Disable with POLLINATIONS_ENABLED=false → fall back to footage.
    pollinations_enabled: bool = True
    pollinations_model: str = "flux"        # photoreal; avoids cartoon/anime
    pollinations_token: str = ""            # optional free token (lifts rate limit)
    # OFF by default: the spec'd fallback is real footage, not a synthetic plate.
    # Set AI_IMAGE_DEMO=true for a fully-offline local plate (free, no network).
    ai_image_demo: bool = False

    # --- FREE AI images via Hugging Face Inference Providers (Phase 5.6 tier) ---
    # Slots BETWEEN Google AI Studio and Pollinations in the image chain. FREE with
    # a HF token that has the "Inference Providers" permission — no OpenAI/Google
    # billing. FLUX.1-dev is the preferred cinematic look; FLUX.1-schnell is the fast
    # free fallback served by the `hf-inference` provider (FLUX.1-dev itself routes
    # through a credited partner provider, so on a free token the schnell fallback is
    # what actually delivers). IMAGE-ONLY — never the Director brain. Blank token →
    # the whole HF tier is skipped and the image chain behaves exactly as before.
    hf_token: str = ""                          # HF_TOKEN (primary env name)
    huggingface_api_key: str = ""               # HUGGINGFACE_API_KEY (accepted alias)
    huggingface_base_url: str = "https://router.huggingface.co/v1"
    huggingface_image_provider: str = "hf-inference"   # free serverless provider
    huggingface_image_model: str = "black-forest-labs/FLUX.1-dev"           # primary
    huggingface_image_model_fast: str = "black-forest-labs/FLUX.1-schnell"  # fast free

    @property
    def hf_api_token(self) -> str:
        """The effective HF token from either supported env name (HF_TOKEN wins)."""
        return (self.hf_token or self.huggingface_api_key).strip()

    # --- render backend (CPU/stability) ---
    # "auto"   → Remotion service → Remotion CLI → ffmpeg (original behavior).
    # "ffmpeg" → skip Remotion/Node entirely and render with pure ffmpeg. Most
    #            stable on a laptop with no Node render service; CPU-friendly.
    render_backend: str = "auto"
    # Optional cinematic motion blur on stills/footage (ffmpeg renderer). OFF by
    # default — frame-blending costs CPU; enable for a more filmic look on a
    # capable machine.
    ffmpeg_motion_blur: bool = False

    # --- Visual accuracy / narration grounding (GLOBAL storytelling rule) ------ #
    # Point-to-point narration↔visual lock: every beat's footage/image must show
    # EXACTLY what the line says (Brazil 1970 trophy lift, not "random football"),
    # across ALL niches (history, politics, business, sports, crime, cybersecurity,
    # finance, documentary, dark facts, anime). When STRICT:
    #   • the Director authors exact, event-grounded broll_keywords per sentence;
    #   • the resolver tries those EXACT terms first, then an AI RECREATION of the
    #     exact event, and only then (last resort) generic stock — and never the
    #     SAME clip twice (cross-scene anti-repeat).
    # Safe + backward compatible: defaults below = today's behavior. Set
    # VISUAL_ACCURACY_MODE=strict (or SCENE_GROUNDING / NARRATION_TO_VISUAL_LOCK
    # =true) to turn the lock on. Generic b-roll stays available as the final
    # safety net (never a black frame) — it's demoted, not forbidden.
    visual_accuracy_mode: str = "normal"        # "strict" = grounding lock ON
    scene_grounding: bool = False               # force per-sentence exact intent
    narration_to_visual_lock: bool = False      # ban generic/repeat; prefer exact

    # Phase 1 Visual Intelligence comparison. OFF preserves the established
    # scene_director policy exactly; ON runs the enhanced policy and records a
    # side-by-side semantic score before the asset resolver sees the result.
    visual_intelligence_enabled: bool = False
    # Phase 2 structured semantic storyboard. OFF leaves SceneGraph.storyboard
    # unset and performs no splitting or extraction work.
    storyboard_engine_enabled: bool = False
    # Phase 3 provenance-aware, narration-specific asset routing. OFF preserves
    # the established b-roll resolver byte-for-byte.
    multi_source_asset_engine_enabled: bool = False
    multi_source_asset_min_match: float = 0.58
    multi_source_asset_priority: str = (
        "government_public_domain,sec_regulatory,company_ir,wikimedia_commons,"
        "pexels,pixabay,ai_generation")
    # Phase 4 deterministic Three.js finance graphics. OFF preserves asset
    # resolution and rendering exactly.
    threejs_visual_engine_enabled: bool = False
    threejs_quality: str = "final"
    threejs_browser_executable: str = ""
    threejs_worker_url: str = ""
    threejs_render_timeout_s: float = 180.0
    threejs_max_frames: int = 360
    # Phase 5 lightweight branded finance explainers. OFF leaves Phase 1-4
    # selection and rendering untouched.
    motion_graphics_engine_enabled: bool = False
    motion_graphics_quality: str = "final"
    # Phase 6 storyboard-grounded cinematic generation. Provider priority is a
    # registry order, not a hardcoded backend choice.
    ai_broll_engine_enabled: bool = False
    ai_broll_provider_priority: str = "flux,stable_diffusion,wan"
    ai_broll_quality: str = "final"
    ai_broll_timeout_s: float = 1200.0

    @property
    def strict_visuals(self) -> bool:
        """True when the narration→visual grounding lock is active (any of the
        three switches set). Read by the Director prompt + the asset resolver."""
        return (self.visual_accuracy_mode.strip().lower() == "strict"
                or self.scene_grounding or self.narration_to_visual_lock)

    # --- CPU layered rendering (Phase 2/3 — opt-in, default OFF) -------------- #
    # Master switch for the multi-layer cinematic path (storyboard → per-scene
    # layers → FFmpeg compositor) and reusable character memory. OFF = the current
    # single-asset pipeline is byte-identical. CPU budget: 1 AI still/short.
    layered_render: bool = False                 # LAYERED_RENDER=1 to enable
    character_memory: bool = True                # reuse a locked character seed+desc

    # --- Phase 3: FFmpeg multi-layer composer (only consulted when layered_render
    #     is ON — every value below is a safe, conservative default for a 12GB i5).
    #     The composer stacks background ▸ subject(alpha) ▸ fx(screen) into one
    #     scene clip with 2-plane parallax + subtle motion; on low RAM or ANY
    #     ffmpeg failure it returns False and the renderer falls back to the
    #     simple single-asset path (so the short always ships).
    layered_min_free_mb: int = 1100              # RAM floor; below → simple render
    layered_ffmpeg_threads: int = 4              # pin ffmpeg threads (CPU-safe)
    layered_max_hero_scenes: int = 1             # scenes that get the full layered stack
    # subject cutout: auto|rembg|oval|none. 'oval' = CPU-only feathered matte (no
    # dependency); 'rembg' uses the rembg package IF importable, else falls to oval.
    layered_subject_matte: str = "oval"
    layered_subject_scale: float = 0.72          # subject width as a fraction of frame
    layered_subject_anchor: float = 0.5          # vertical anchor (0=top … 1=bottom)
    layered_oversize: float = 1.18               # parallax headroom (bg pre-scale)
    layered_drift_px: float = 26.0               # max near-plane parallax drift, px
    layered_force_fallback: bool = False         # test hook: force the simple render
    # Live layer-asset wiring (Phase 3): cache-first generation under a HARD budget.
    layered_ai_still_budget: int = 2             # MAX unique AI stills generated per short
    layered_ai_timeout_s: float = 1200.0         # per-still generation timeout guard (CPU LCM ~11min)

    # --- Phase 4: post-render QA / stabilization gates (CPU-first; pipeline/qa.py).
    #     A non-fatal observability pass over the finished MP4 + render metrics:
    #     black-frame detection, per-scene non-black, RAM peak + free-floor, render
    #     wall-time budget, and character consistency. Default OFF and NEVER blocks a
    #     render — it only reports — so it's fully backward compatible.
    qa_enabled: bool = False                     # QA_ENABLED=1 → run the QA report
    qa_black_max_fraction: float = 0.06          # max black fraction (allows brief dip transitions; catches a whole black scene)
    qa_scene_yavg_min: float = 14.0              # per-scene min avg luma (non-black)
    qa_ram_peak_max_mb: int = 4000               # render ffmpeg RAM-peak ceiling (12GB box)
    qa_min_free_floor_mb: int = 800              # free RAM must never dip below this
    qa_render_budget_s: float = 900.0            # hard wall-time budget per short
    qa_consistency_min_pct: float = 95.0         # character-consistency floor (when applicable)

    # --- infra ---
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = f"sqlite:///{DATA_DIR}/factory.db"

    # --- authentication ---
    auth_required: bool = True
    auth_secret_key: str = ""
    auth_access_token_minutes: int = 30
    auth_refresh_token_days: int = 14
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    auth_min_password_length: int = 12
    remotion_render_url: str = "http://localhost:3001"   # remotion render service
    data_dir: Path = DATA_DIR

    # --- uploads ---
    # Defaults under the resolved CONFIG_DIR so it follows the runtime root
    # (checkout locally, /repo in Compose) instead of being pinned to /repo.
    youtube_client_secret_path: str = str(
        CONFIG_DIR / "secrets" / "youtube_client_secret.json")


class BrandConfig(BaseModel):
    primary_color: str = "#e11d2a"
    accent_color: str = "#f5c518"
    font: str = "Inter"
    watermark_path: str | None = None
    intro_card: bool = True


class ChannelConfig(BaseModel):
    """Loaded from config/channels/<id>.yaml — the creative DNA of a channel."""

    id: str
    name: str
    niche: str
    voice_provider: str = "elevenlabs"
    voice_id: str = "Rachel"
    music_dir: str = "data/assets/music/news"
    brand: BrandConfig = BrandConfig()
    # editorial guardrails injected into the Director system prompt
    style_notes: str = ""
    banned_topics: list[str] = []
    cta: str = "Follow for daily updates."


@functools.lru_cache
def settings() -> Settings:
    return Settings()


@functools.lru_cache
def load_channel(channel_id: str) -> ChannelConfig:
    path = CONFIG_DIR / "channels" / f"{channel_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No channel config: {path}")
    data = yaml.safe_load(path.read_text())
    return ChannelConfig(**data)


def validate_providers() -> list[str]:
    """Non-fatal startup validation. Returns a list of human-readable WARNINGS for
    misconfigured-but-not-broken provider setups (e.g. image-to-video enabled with
    no API key). It NEVER raises and NEVER blocks startup — every condition has a
    safe runtime fallback — so an incomplete .env degrades gracefully instead of
    crashing the app. Call `log_provider_validation()` at startup to surface these."""
    s = settings()
    warns: list[str] = []
    if s.enable_image_to_video:
        if s.ai_video_provider == "picsart" and not s.picsart_api_key:
            warns.append(
                "ENABLE_IMAGE_TO_VIDEO=1 but PICSART_API_KEY is empty → image-to-"
                "video beats will fall back to the still + ffmpeg Ken Burns motion "
                "(no crash, no cost).")
        if s.max_ai_video_scenes < 0:
            warns.append(
                f"MAX_AI_VIDEO_SCENES={s.max_ai_video_scenes} (<0) → treated as 0; "
                "no AI-video beats will be allocated.")
        if s.ai_video_provider != "picsart":
            warns.append(
                f"ENABLE_IMAGE_TO_VIDEO=1 but AI_VIDEO_PROVIDER={s.ai_video_provider!r} "
                "(not 'picsart') → the legacy text→video path is used, not Picsart "
                "image-to-video.")
    if s.strict_visuals:
        warns.append(
            "VISUAL_ACCURACY_MODE=strict → narration↔visual grounding lock ON: "
            "exact footage → AI recreation → (last-resort) generic, no repeats.")
    return warns


def log_provider_validation() -> list[str]:
    """Print the startup validation warnings (one `[config]` line each) and return
    them. Safe to call from any entrypoint (API lifespan, worker, CLI)."""
    warns = validate_providers()
    for w in warns:
        print(f"[config] ⚠ {w}", flush=True)
    return warns
