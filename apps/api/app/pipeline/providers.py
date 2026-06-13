"""
External provider adapters. ALL behind plain async functions so the pipeline
never imports a vendor SDK directly — swap ElevenLabs->OpenAI or Pexels->Pixabay
without touching pipeline logic. v1 ships real elevenlabs/openai/pexels/manim;
veo3/seedance are stubs that raise unless wired (cost gate).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
from pathlib import Path
from urllib.parse import quote

import httpx

from ..config import settings


# ----------------------------- TTS ----------------------------------------- #
async def elevenlabs_tts(text: str, out: Path, voice) -> None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice.voice_id}"
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            url,
            headers={"xi-api-key": settings().elevenlabs_api_key},
            json={"text": text, "model_id": "eleven_turbo_v2_5",
                  "voice_settings": {"stability": voice.stability,
                                     "similarity_boost": 0.75,
                                     "speed": voice.speed}},
        )
        r.raise_for_status()
        out.write_bytes(r.content)              # mp3; ffprobe handles it


async def openai_tts(text: str, out: Path, voice) -> None:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {settings().openai_api_key}"},
            json={"model": "tts-1", "voice": voice.voice_id or "onyx",
                  "input": text, "response_format": "wav"},
        )
        r.raise_for_status()
        out.write_bytes(r.content)


async def piper_tts(text: str, out: Path, voice) -> None:
    """Fully local fallback (no API cost). Requires piper binary."""
    proc = await asyncio.create_subprocess_exec(
        "piper", "--model", f"/opt/piper/{voice.voice_id}.onnx",
        "--output_file", str(out),
        stdin=asyncio.subprocess.PIPE,
    )
    await proc.communicate(text.encode())


async def espeak_tts(text: str, out: Path, voice) -> None:
    """Zero-dependency local voice (apt install espeak-ng). Robotic but real."""
    proc = await asyncio.create_subprocess_exec(
        "espeak-ng", "-v", "en-us", "-s", "165", "-w", str(out), text,
    )
    await proc.wait()


async def tone_tts(text: str, out: Path, voice) -> None:
    """Last resort, NO speech tool at all: emit silence sized to the estimated
    speaking time (~2.6 words/sec) so the timeline still flows for testing."""
    secs = max(1.0, len(text.split()) / 2.6)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono", "-t", f"{secs:.2f}", "-y", str(out),
    )
    await proc.wait()


# ----------------------------- B-roll -------------------------------------- #
# Real-footage engine. Four search adapters (Pexels/Pixabay × video/image) feed
# the asset resolver's priority chain. Each returns a LOCAL file path or None.
#
#   pick: candidate index — lets the resolver hand adjacent scenes *different*
#         clips for the same query so the video doesn't repeat itself, while
#         staying deterministic (same pick -> same clip).
#
# Per-process caches keep it fast & cheap: search results are memoised by query
# (one API call per unique query per run) and downloads are content-addressed
# (one file per unique URL, ever — see _download).

_SEARCH_CACHE: dict[str, list[str]] = {}
_SEARCH_LOCKS: dict[str, asyncio.Lock] = {}
_DL_LOCKS: dict[str, asyncio.Lock] = {}


async def _cached_search(key: str, fetch) -> list[str]:
    """Memoise a candidate-URL list per query for the lifetime of the process.
    A per-key lock collapses concurrent identical searches into one API call."""
    if key in _SEARCH_CACHE:
        return _SEARCH_CACHE[key]
    lock = _SEARCH_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        if key in _SEARCH_CACHE:
            return _SEARCH_CACHE[key]
        try:
            urls = await fetch()
        except Exception:
            urls = []
        _SEARCH_CACHE[key] = urls
        return urls


async def _pick_download(urls: list[str], pick: int, ext: str) -> str | None:
    if not urls:
        return None
    return await _download(urls[pick % len(urls)], ext)


async def pexels_video(query: str, min_dur: float, pick: int = 0) -> str | None:
    key = settings().pexels_api_key
    if not key:
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": key},
                params={"query": query, "orientation": "portrait",
                        "size": "medium", "per_page": 15},
            )
        if r.status_code != 200:
            return []
        vids = r.json().get("videos", [])
        long_enough = [v for v in vids if v.get("duration", 0) >= min_dur] or vids
        urls: list[str] = []
        for v in long_enough:
            files = sorted(v.get("video_files", []),
                           key=lambda f: f.get("height", 0), reverse=True)
            # tallest file that isn't oversized (<=1920h) keeps download light
            pref = [f for f in files if f.get("height", 0) <= 1920] or files
            if pref:
                urls.append(pref[0]["link"])
        return urls

    urls = await _cached_search(f"pexvid:{min_dur:.0f}:{query}", fetch)
    return await _pick_download(urls, pick, "mp4")


async def pixabay_video(query: str, min_dur: float, pick: int = 0) -> str | None:
    key = settings().pixabay_api_key
    if not key:
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/videos/",
                            params={"key": key, "q": query, "per_page": 15,
                                    "safesearch": "true"})
        if r.status_code != 200:
            return []
        hits = r.json().get("hits", [])
        long_enough = [h for h in hits if h.get("duration", 0) >= min_dur] or hits
        urls: list[str] = []
        for h in long_enough:
            files = h.get("videos", {})
            f = files.get("large") or files.get("medium") or files.get("small")
            if f and f.get("url"):
                urls.append(f["url"])
        return urls

    urls = await _cached_search(f"pixvid:{min_dur:.0f}:{query}", fetch)
    return await _pick_download(urls, pick, "mp4")


async def pexels_image(query: str, pick: int = 0) -> str | None:
    key = settings().pexels_api_key
    if not key:
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": key},
                params={"query": query, "orientation": "portrait", "per_page": 15},
            )
        if r.status_code != 200:
            return []
        out: list[str] = []
        for p in r.json().get("photos", []):
            src = p.get("src") or {}
            u = src.get("portrait") or src.get("large2x") or src.get("large")
            if u:
                out.append(u)
        return out

    urls = await _cached_search(f"peximg:{query}", fetch)
    return await _pick_download(urls, pick, "jpg")


async def pixabay_image(query: str, pick: int = 0) -> str | None:
    key = settings().pixabay_api_key
    if not key:
        return None

    async def fetch() -> list[str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get("https://pixabay.com/api/",
                            params={"key": key, "q": query, "image_type": "photo",
                                    "orientation": "vertical", "per_page": 15,
                                    "safesearch": "true"})
        if r.status_code != 200:
            return []
        out: list[str] = []
        for h in r.json().get("hits", []):
            u = h.get("largeImageURL") or h.get("webformatURL")
            if u:
                out.append(u)
        return out

    urls = await _cached_search(f"piximg:{query}", fetch)
    return await _pick_download(urls, pick, "jpg")


# ----------------------------- Manim --------------------------------------- #
async def manim_render(spec: str, video_id: str, scene_id: str) -> str:
    """Render a chart via a vetted parametric template (no LLM codegen)."""
    from . import manim_templates as mt
    out = settings().data_dir / "jobs" / video_id / f"{scene_id}_chart.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = mt.payload_from_query(spec, title=spec)
    return await mt.render_chart(payload, out)   # raises if manim absent -> solid


# --------------------------- Premium AI video ------------------------------ #
# Hybrid-engine slot #3 (Phase 5.7 — Pika Labs): a SHORT (1–3s) cinematic AI
# insert for PREMIUM documentary beats real footage can't truthfully serve —
# history recreations, political symbolism, election atmosphere, impossible camera
# shots, dark history, abstract economy metaphors. It NEVER replaces real footage:
# the decision engine caps it at ~15–20% of the timeline and the resolver always
# keeps real footage as the safety net, so a missing PIKA_API_KEY or a generation
# failure degrades to footage — the pipeline never breaks.
#
# PROVIDER CHAIN (first configured key wins): Pika (via fal.ai) → Veo3 → Seedance.
# Pika is the real, wired provider; Veo3/Seedance stay stubbed (cost gate). Every
# clip is HARD-CLAMPED + locally trimmed to 1–3s and content-addressed (generated
# once, reused free) so render speed stays reasonable.
AI_INSERT_MIN_S = 1.0
AI_INSERT_MAX_S = 3.0

# Picsart image-to-video inserts are slightly longer (3–5s) — a still gets a real
# cinematic move, so it needs room to breathe vs the 1–3s Pika text→video inserts.
I2V_MIN_S = 3.0
I2V_MAX_S = 5.0


def clamp_i2v_seconds(dur: float) -> float:
    """Picsart image-to-video clips are 3–5s ONLY — clamp any requested duration."""
    return round(max(I2V_MIN_S, min(I2V_MAX_S, dur)), 2)

# Cinematic style baked into every AI-video prompt (matches the AI-image doctrine:
# Netflix/Vox/Bloomberg documentary look, photoreal, vertical 9:16, no text).
AI_VIDEO_STYLE = (
    "cinematic documentary footage, photorealistic, slow deliberate camera move, "
    "dramatic directional lighting, shallow depth of field, 35mm film grain, "
    "muted graded color, American setting, premium Netflix Vox Bloomberg "
    "documentary look, vertical 9:16, highly detailed, no text, no captions, "
    "no watermark, natural undistorted faces"
)
AI_VIDEO_NEGATIVE = (
    "cartoon, illustration, anime, cgi, 3d render, video game, plastic skin, "
    "uncanny faces, deformed face, extra fingers, text, caption, watermark, "
    "logo, lowres, blurry, oversaturated, fast cuts, jittery motion"
)


def clamp_insert_seconds(dur: float) -> float:
    """Premium AI inserts are 1–3s ONLY — clamp any requested duration."""
    return round(max(AI_INSERT_MIN_S, min(AI_INSERT_MAX_S, dur)), 2)


def build_video_prompt(subject: str) -> str:
    """The cinematic prompt sent to Pika for a beat (also used by verification to
    show exactly what was generated)."""
    return (f"{subject.strip()}. {AI_VIDEO_STYLE}. "
            f"Avoid: {AI_VIDEO_NEGATIVE}.").strip(". ")


def _log_video(msg: str) -> None:
    print(f"[ai-video] {msg}", flush=True)


async def ai_video_generate(prompt: str, dur: float, video_id: str,
                            scene_id: str, *, seed: int = 0) -> str:
    """Generate a short (1–3s) cinematic insert. Prefers Pika (fal.ai), then the
    gated Veo3/Seedance stubs; raises if none is configured (cost gate) so the
    resolver falls through to real footage."""
    dur = clamp_insert_seconds(dur)                 # inserts only — never longer
    s = settings()
    if not s.ai_video_enabled:                      # master switch (default OFF)
        raise RuntimeError("AI video disabled (AI_VIDEO_ENABLED=0) → use footage")
    if s.pika_api_key:
        return await pika_generate(prompt, dur, video_id, scene_id, seed=seed)
    if s.veo3_api_key:
        return await veo3_generate(prompt, dur, video_id, scene_id)
    if s.seedance_api_key:
        return await seedance_generate(prompt, dur, video_id, scene_id)
    raise RuntimeError("no AI-video provider key configured (PIKA_API_KEY unset)")


# fal.ai async-queue states that mean "still working" (anything else → check done)
_FAL_PENDING = {"IN_QUEUE", "IN_PROGRESS"}


async def pika_generate(prompt: str, dur: float, video_id: str, scene_id: str,
                        *, seed: int = 0) -> str:
    """Pika Labs cinematic clip via fal.ai's async queue. Submits the job, polls
    until the video is ready, downloads it, then TRIMS to 1–3s locally so the
    insert constraint holds regardless of the provider's native clip length.
    Content-addressed by (model, resolution, prompt, dur) → generated once, reused
    free. Raises on any failure → resolver falls back to real footage."""
    s = settings()
    dur = clamp_insert_seconds(dur)
    cache = _img_cache(
        f"pika:{s.pika_model}:{s.pika_resolution}:{dur}:{seed}:{prompt}", "mp4")
    if cache.exists():
        _log_video(f"{scene_id}: ✓ PIKA clip (cached) → {cache.name}")
        return str(cache)

    _log_video(f"{scene_id}: generating via Pika ({s.pika_model}, {dur:.0f}s, "
               f"{s.pika_resolution})… prompt={prompt[:90]!r}")
    src_url = await _fal_submit_and_wait(prompt, seed)
    raw = await _download(src_url, "mp4")           # provider's native clip
    await _trim_clip(Path(raw), cache, dur)         # enforce 1–3s
    _log_video(f"{scene_id}: ✓ PIKA AI VIDEO inserted ({dur:.0f}s) → {cache.name}")
    return str(cache)


async def _fal_submit_and_wait(prompt: str, seed: int) -> str:
    """Run one fal.ai queued generation and return the resulting video URL.
    Works against any Pika-compatible fal endpoint (PIKA_API_BASE/PIKA_MODEL)."""
    s = settings()
    headers = {"Authorization": f"Key {s.pika_api_key}"}
    body = {
        "prompt": prompt,
        "negative_prompt": AI_VIDEO_NEGATIVE,
        "aspect_ratio": s.pika_aspect_ratio,
        "resolution": s.pika_resolution,
        "seed": seed,
    }
    submit_url = f"{s.pika_api_base.rstrip('/')}/{s.pika_model.lstrip('/')}"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
        r = await c.post(submit_url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        # Sync endpoints return the result directly; queue endpoints hand back
        # status_url / response_url to poll.
        url = _extract_video_url(data)
        if url:
            return url
        status_url = data.get("status_url")
        response_url = data.get("response_url")
        if not response_url:
            raise RuntimeError(f"pika: unexpected submit response {str(data)[:160]}")

        waited = 0.0
        while waited < s.pika_max_wait_seconds:
            await asyncio.sleep(s.pika_poll_seconds)
            waited += s.pika_poll_seconds
            if status_url:
                sr = await c.get(status_url, headers=headers)
                if sr.status_code == 200:
                    st = sr.json().get("status", "")
                    if st in _FAL_PENDING:
                        continue
            fr = await c.get(response_url, headers=headers)
            if fr.status_code == 200:
                url = _extract_video_url(fr.json())
                if url:
                    return url
        raise RuntimeError(f"pika: timed out after {s.pika_max_wait_seconds:.0f}s")


def _extract_video_url(data: dict) -> str | None:
    """Pull the clip URL out of a fal/Pika response (a few known shapes)."""
    if not isinstance(data, dict):
        return None
    v = data.get("video")
    if isinstance(v, dict) and v.get("url"):
        return v["url"]
    if isinstance(v, str):
        return v
    vids = data.get("videos")
    if isinstance(vids, list) and vids:
        first = vids[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first
    if data.get("url"):
        return data["url"]
    return None


async def _trim_clip(src: Path, out: Path, dur: float) -> None:
    """Trim a clip to the first `dur` seconds (1–3s insert). Re-encodes — clips
    are tiny so it's fast, and it guarantees a clean, keyframe-accurate cut."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part.mp4")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-t", f"{dur:.2f}",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(tmp),
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0 or not tmp.exists():
        raise RuntimeError("pika clip trim failed")
    tmp.replace(out)                                 # atomic publish


# --------- Picsart IMAGE-TO-VIDEO — cinematic motion on a generated still ------- #
# Slot for the desired "IMAGE → VIDEO" branch: take the still LOCAL ComfyUI already
# produced for a cinematic beat and animate it into a SHORT (3–5s) clip via
# Picsart's GenAI API. HERO / high-emotion / anime / dramatic beats only — the
# scene director caps it (MAX_AI_VIDEO_SCENES) and the resolver keeps the still +
# real footage as the safety net, so a missing PICSART_API_KEY or ANY failure
# degrades to the still (Ken Burns) then real footage — the pipeline never breaks.
#
# API (docs.picsart.io): POST {base}{path} multipart with the image file + prompt;
# auth header X-Picsart-API-Key. Returns 202 + an inference id; we poll
# {base}{path}/inferences/{id} until a video URL is ready, download + trim to 3–5s.
# Content-addressed by (model, quality, dur, image-bytes, prompt) → generated once,
# reused free. Optimised for a weak laptop: 480p + wan-2.7 default, server-side gen
# (no local GPU), only a cheap local trim.
# Friendly model name → the value Picsart expects. `wan-2.7` is a plain short
# name (the API default); the Google Veo image-to-video models are addressed by
# URN. Unknown values (already a URN, or a future short name) pass through
# unchanged, so you can always set a raw model string in the env and it just works.
_PICSART_MODEL_ALIASES: dict[str, str] = {
    "wan-2.7": "wan-2.7",
    "veo-2.0": "urn:air:google:model:google:veo-2.0-image-to-video@1",
    "veo-3.1": "urn:air:google:model:google:veo-3.1-image-to-video@1",
    "veo-3.1-fast": "urn:air:google:model:google:veo-3.1-fast-image-to-video@1",
}


def resolve_picsart_model(name: str) -> str:
    """Map a friendly Picsart model name to its API value; pass unknowns through."""
    n = (name or "").strip()
    return _PICSART_MODEL_ALIASES.get(n, n)


def _picsart_poll_url(inference_id: str) -> str:
    s = settings()
    base = s.picsart_api_base.rstrip("/")
    path = s.picsart_i2v_path.strip("/")
    return f"{base}/{path}/inferences/{inference_id}"


def _extract_inference_id(data: dict) -> str | None:
    """Pull the async job id out of a Picsart 202 response (a few known shapes)."""
    if not isinstance(data, dict):
        return None
    for k in ("inference_id", "transaction_id", "id"):
        v = data.get(k)
        if isinstance(v, str) and v:
            return v
    inner = data.get("data")
    if isinstance(inner, dict):
        for k in ("inference_id", "transaction_id", "id"):
            v = inner.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _picsart_status(data: dict) -> str:
    """Normalised lowercase status from a Picsart poll response."""
    st = data.get("status") if isinstance(data, dict) else ""
    if not st and isinstance(data.get("data"), dict):
        st = data["data"].get("status", "")
    return str(st or "").lower()


# Picsart async states that mean "still working" (anything else → check for a URL).
_PICSART_PENDING = {"queued", "in_progress", "in-progress", "processing", "pending",
                    "accepted", "running"}


async def picsart_image_to_video(image_path: str, prompt: str, dur: float,
                                 video_id: str, scene_id: str, *,
                                 seed: int = 0, model: str | None = None) -> str:
    """Animate a local still into a 3–5s cinematic clip via Picsart. Submits the
    image + prompt, polls until ready, downloads + trims to 3–5s. Content-addressed
    → generated once, reused free. `model` overrides settings().picsart_model (used
    for the hero beat). Raises on any failure → resolver falls back to the still
    (Ken Burns) then real footage."""
    s = settings()
    if not s.enable_image_to_video:
        raise RuntimeError("image-to-video disabled (ENABLE_IMAGE_TO_VIDEO=0)")
    if not s.picsart_api_key:
        raise RuntimeError("no PICSART_API_KEY configured")
    img = Path(image_path)
    if not img.exists():
        raise RuntimeError(f"picsart: source still missing ({image_path})")

    dur = clamp_i2v_seconds(dur)
    eff_model = resolve_picsart_model(model or s.picsart_model)
    img_sig = hashlib.sha1(img.read_bytes()).hexdigest()[:16]
    cache = _img_cache(
        f"picsart:{eff_model}:{s.picsart_quality}:{dur}:{img_sig}:{prompt}",
        "mp4")
    if cache.exists():
        _log_video(f"{scene_id}: ✓ PICSART clip (cached) → {cache.name}")
        return str(cache)

    _log_video(f"{scene_id}: image→video via Picsart ({eff_model}, "
               f"{dur:.0f}s, {s.picsart_quality})… still={img.name}")
    src_url = await _picsart_submit_and_wait(img, prompt, dur, eff_model)
    raw = await _download(src_url, "mp4")
    await _trim_clip(Path(raw), cache, dur)          # enforce 3–5s
    _log_video(f"{scene_id}: ✓ PICSART AI VIDEO inserted ({dur:.0f}s) → {cache.name}")
    return str(cache)


async def _picsart_submit_and_wait(img: Path, prompt: str, dur: float,
                                   model: str) -> str:
    """Run one Picsart image-to-video job and return the result video URL."""
    s = settings()
    headers = {"X-Picsart-API-Key": s.picsart_api_key, "accept": "application/json"}
    submit_url = f"{s.picsart_api_base.rstrip('/')}/{s.picsart_i2v_path.strip('/')}"
    data = {
        "prompt": prompt,
        "model": model,
        "quality": s.picsart_quality,
        "length": str(int(round(dur))),
        "audio": "true" if s.picsart_audio else "false",
    }
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
        with img.open("rb") as fh:
            files = {"image": (img.name, fh, "application/octet-stream")}
            r = await c.post(submit_url, headers=headers, data=data, files=files)
        r.raise_for_status()
        payload = r.json()
        # A sync-style response may hand back the URL directly.
        url = _extract_video_url(payload)
        if url:
            return url
        inference_id = _extract_inference_id(payload)
        if not inference_id:
            raise RuntimeError(f"picsart: no inference id {str(payload)[:160]}")

        poll_url = _picsart_poll_url(inference_id)
        waited = 0.0
        while waited < s.picsart_max_wait_seconds:
            await asyncio.sleep(s.picsart_poll_seconds)
            waited += s.picsart_poll_seconds
            pr = await c.get(poll_url, headers=headers)
            if pr.status_code in (200, 201):
                body = pr.json()
                url = _extract_video_url(body)
                if url:
                    return url
                if _picsart_status(body) not in _PICSART_PENDING:
                    # terminal non-pending state with no URL → treat as failure
                    if _picsart_status(body) in ("failed", "error", "cancelled"):
                        raise RuntimeError(
                            f"picsart: job {_picsart_status(body)} {str(body)[:120]}")
            elif pr.status_code == 202:
                continue                              # still queued
        raise RuntimeError(
            f"picsart: timed out after {s.picsart_max_wait_seconds:.0f}s")


async def veo3_generate(prompt: str, dur: float, video_id: str, scene_id: str) -> str:
    raise NotImplementedError("Veo3 gated — wire the API call when budget approved")


async def seedance_generate(prompt: str, dur: float, video_id: str, scene_id: str) -> str:
    raise NotImplementedError("Seedance gated — wire the API call when budget approved")


# ----------------------- Premium AI documentary IMAGES --------------------- #
# Phase-5.6 slot: a cinematic AI still (gets Ken Burns motion downstream) for
# beats real footage can't truthfully serve — history recreations, symbolic
# politics, scandals/elections, dark history, impossible-to-film moments. The
# decision engine (`scene_director.py`) picks WHICH beats; this just GENERATES.
#
# IMAGE BACKEND chain (OpenAI is intentionally NOT used — OPENAI_API_KEY ignored):
#   1. PRIMARY — Google AI Studio (GOOGLE_API_KEY): gemini-2.5-flash-image
#      (:generateContent) → imagen-*:predict. Needs BILLING on the key.
#   2. FREE FALLBACK #1 — Hugging Face Inference Providers (HF_TOKEN): cinematic
#      FLUX (FLUX.1-dev → FLUX.1-schnell). Free with a HF token; no Google/OpenAI
#      billing. Returns raw image bytes from the router.
#   3. FREE FALLBACK #2 — Pollinations (no key): photoreal `flux` model. Keeps real
#      AI images flowing for free when Google + HF are unavailable / fail.
#   4. else → raise, and the resolver falls back to real footage (Pexels/Pixabay).
# `ai_image_demo` (default OFF) enables a local ffmpeg plate for fully-offline
# testing. The pipeline never breaks. Results are content-addressed by prompt hash
# → generated once, reused free.

# Style suffix that bakes in the IMAGE QUALITY RULES (Netflix/Vox/Bloomberg doc).
AI_IMAGE_STYLE = (
    "cinematic documentary still, photorealistic, dramatic directional lighting, "
    "shallow depth of field, 35mm film grain, muted graded color, American "
    "setting, premium Netflix Vox Bloomberg documentary look, vertical 9:16 "
    "portrait framing, highly detailed, no text, no captions, no watermark, "
    "natural undistorted faces"
)
AI_IMAGE_NEGATIVE = (
    "cartoon, illustration, anime, cgi, 3d render, video game, plastic skin, "
    "uncanny faces, deformed face, extra fingers, distorted hands, text, "
    "caption, watermark, logo, signature, lowres, blurry, oversaturated"
)
# Cinematic palettes per subject bucket. A BRIGHT key-light colour (c0) falls off
# to a dark base (c1) so the off-centre gradient reads as dramatic directional
# lighting, not a flat near-black card.
_PLATE_PALETTE: dict[str, tuple[str, str, str]] = {
    "history":  ("0xb8842f", "0x140d05", "0x161009"),   # warm amber key on sepia
    "politics": ("0x3f6fb0", "0x4a0f1c", "0x05070d"),   # blue key ↔ deep red
    "business": ("0x4a7fb8", "0xb89a4a", "0x06121f"),   # steel blue + gold key
    "abstract": ("0x2f7a5c", "0x0a1a14", "0x0a0f14"),   # teal key / charcoal
    "default":  ("0x5a5a7a", "0x121218", "0x07070a"),   # neutral cinematic
}


def _img_cache(key: str, ext: str) -> Path:
    cache = settings().data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / f"ai_img_{hashlib.sha1(key.encode()).hexdigest()}.{ext}"


def _log(msg: str) -> None:
    print(f"[ai-image] {msg}", flush=True)


async def ai_image_generate(subject: str, video_id: str, scene_id: str,
                            *, category: str = "default", seed: int = 0) -> str:
    """Generate ONE cinematic documentary still via Google AI Studio (free-first).
    Returns a file path, or RAISES so the resolver falls back to real footage.
    Logs exactly where a Google AI image was inserted (or why it fell back)."""
    # OPTIONAL OpenRouter augmentation: sharpen the subject into a richer cinematic
    # prompt. No-op (returns the original subject) when OpenRouter isn't configured,
    # so image generation behaves exactly as before unless OPENROUTER_API_KEY is set.
    from ..openrouter import enhance_image_prompt
    subject = await enhance_image_prompt(subject)
    prompt = (f"{subject.strip()}. {AI_IMAGE_STYLE}. "
              f"Avoid: {AI_IMAGE_NEGATIVE}.").strip(". ")
    s = settings()

    # 0) PRIMARY (when enabled) — remote ComfyUI on a GPU (Colab + Cloudflare
    #    tunnel). Runs a DreamShaper SD1.5 txt2img graph and returns a real still.
    #    ANY failure (tunnel down, timeout, bad graph) logs and falls through to the
    #    existing chain below — the pipeline never breaks.
    if s.comfyui_enabled and s.comfyui_base_url:
        _log(f"{scene_id}: generating via remote ComfyUI "
             f"({s.comfyui_checkpoint})… subject={subject!r}")
        try:
            path = await _remote_comfyui_image(prompt, seed)
            _log(f"{scene_id}: ✓ COMFYUI image inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            _log(f"{scene_id}: ✗ ComfyUI failed "
                 f"({type(e).__name__}: {str(e)[:120]}) → falling back to chain")

    # 1) PRIMARY — Google AI Studio (needs billing on the key).
    if s.google_api_key:
        _log(f"{scene_id}: generating via Google AI Studio "
             f"({s.google_image_model})… subject={subject!r}")
        try:
            path = await _google_ai_studio_image(prompt)
            _log(f"{scene_id}: ✓ GOOGLE AI IMAGE inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            _log(f"{scene_id}: ✗ Google generation FAILED "
                 f"({type(e).__name__}: {str(e)[:120]}) → trying Pollinations (free)")
    else:
        _log(f"{scene_id}: GOOGLE_API_KEY not set → trying Pollinations (free)")

    # 2) FREE FALLBACK #1 — Hugging Face Inference Providers (FLUX, free with a HF
    #    token). FLUX.1-dev (preferred) → FLUX.1-schnell (fast free). Any failure or
    #    rate-limit cleanly degrades to Pollinations next — the pipeline never breaks.
    if s.hf_api_token:
        _log(f"{scene_id}: generating via HuggingFace FLUX "
             f"({s.huggingface_image_model})… subject={subject!r}")
        try:
            path = await _huggingface_image(prompt, seed)
            _log(f"{scene_id}: ✓ HF image inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            _log(f"{scene_id}: ✗ HF failed "
                 f"({type(e).__name__}: {str(e)[:120]}) → fallback to Pollinations")
    else:
        _log(f"{scene_id}: HF_TOKEN not set → trying Pollinations (free)")

    # 3) FREE FALLBACK #2 — Pollinations (no key). Keeps real AI images flowing free.
    if s.pollinations_enabled:
        _log(f"{scene_id}: generating via Pollinations "
             f"({s.pollinations_model}, free)… subject={subject!r}")
        try:
            path = await _pollinations_image(prompt, seed)
            _log(f"{scene_id}: ✓ POLLINATIONS (free) AI IMAGE inserted → {Path(path).name}")
            return path
        except Exception as e:  # noqa: BLE001
            _log(f"{scene_id}: ✗ Pollinations FAILED "
                 f"({type(e).__name__}: {str(e)[:120]}) → fallback to real footage")

    # 4) optional offline plate, else raise → resolver uses real footage (Pexels)
    if s.ai_image_demo:
        _log(f"{scene_id}: AI_IMAGE_DEMO on → local cinematic plate (offline test)")
        return await _local_cinematic_plate(subject, category, seed)
    raise RuntimeError("no AI image (google + pollinations unavailable); use footage")


# --------- Remote ComfyUI — GPU text→image on the DreamShaper checkpoint -------- #
# Talks to a stock ComfyUI HTTP API (no SDK): POST /prompt to enqueue a graph, poll
# /history/{prompt_id} until the run finishes, then GET /view to download the PNG.
# The graph is a clean, minimal SD1.5 text→image pipeline (CheckpointLoader →
# 2×CLIPTextEncode → EmptyLatentImage → KSampler → VAEDecode → SaveImage). It reuses
# the shared documentary style + negative prompt so output matches the other
# providers. Content-addressed → generated once, reused free. Raises on any failure
# so ai_image_generate() falls through to the existing provider chain.
def _comfy_graph(prompt: str, seed: int) -> dict:
    """Build a ComfyUI prompt graph (node-id → node) for SD1.5 txt2img.

    Default = the stock 25-step graph (UNCHANGED — backward compatible). When
    COMFYUI_LCM=1, a LoraLoaderModelOnly node is inserted and the KSampler is fed
    the LCM model + LCM-tuned steps/cfg/sampler/scheduler, so the same checkpoint
    renders in ~8 steps (the CPU win). COMFYUI_VAE_TILED=1 swaps in a tiled VAE
    decode to cap peak RAM on a 12GB box. Negative prompt is overridable
    (COMFYUI_NEGATIVE) so an anime/cartoon checkpoint isn't fought by the global
    photoreal negative."""
    s = settings()
    negative = s.comfyui_negative.strip() or AI_IMAGE_NEGATIVE

    if s.comfyui_lcm:
        model_ref = ["10", 0]                       # KSampler reads the LCM model
        steps, cfg = s.comfyui_lcm_steps, s.comfyui_lcm_cfg
        sampler, scheduler = s.comfyui_lcm_sampler, s.comfyui_lcm_scheduler
    else:
        model_ref = ["4", 0]                         # checkpoint model (stock path)
        steps, cfg = s.comfyui_steps, s.comfyui_cfg
        sampler, scheduler = s.comfyui_sampler, s.comfyui_scheduler

    if s.comfyui_vae_tiled:
        # Newer ComfyUI VAEDecodeTiled also requires overlap + temporal_* (it's the
        # shared image/video decoder). The temporal params are inert for a single
        # still but must be present or the prompt fails validation.
        decode = {"class_type": "VAEDecodeTiled",
                  "inputs": {"samples": ["3", 0], "vae": ["4", 2],
                             "tile_size": s.comfyui_vae_tile_size,
                             "overlap": 64,
                             "temporal_size": 64, "temporal_overlap": 8}}
    else:
        decode = {"class_type": "VAEDecode",
                  "inputs": {"samples": ["3", 0], "vae": ["4", 2]}}

    graph = {
        "4": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": s.comfyui_checkpoint}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": s.comfyui_width, "height": s.comfyui_height,
                         "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": int(seed), "steps": steps,
                         "cfg": cfg, "sampler_name": sampler,
                         "scheduler": scheduler, "denoise": 1.0,
                         "model": model_ref, "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": decode,
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0], "filename_prefix": "shortsfactory"}},
    }
    if s.comfyui_lcm:                                # insert the LCM-LoRA on the model
        graph["10"] = {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"lora_name": s.comfyui_lcm_lora,
                                  "strength_model": s.comfyui_lcm_strength,
                                  "model": ["4", 0]}}
    return graph


async def _remote_comfyui_image(prompt: str, seed: int = 0) -> str:
    s = settings()
    base = s.comfyui_base_url.rstrip("/")
    if not base:
        raise RuntimeError("COMFYUI_BASE_URL not set")
    # the render settings live in the key so an LCM still and a stock still (or a
    # changed negative) never collide in the content-addressed cache.
    variant = (f"lcm{s.comfyui_lcm_steps}@{s.comfyui_lcm_cfg}" if s.comfyui_lcm
               else f"std{s.comfyui_steps}@{s.comfyui_cfg}")
    out = _img_cache(f"comfyui:{base}:{s.comfyui_checkpoint}:{variant}:"
                     f"{s.comfyui_width}x{s.comfyui_height}:{seed}:{prompt}", "png")
    if out.exists():
        return str(out)

    graph = _comfy_graph(prompt, seed)
    timeout = float(s.comfyui_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        # 1) enqueue the graph
        r = await c.post(f"{base}/prompt", json={"prompt": graph})
        r.raise_for_status()
        prompt_id = r.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI /prompt returned no prompt_id: {r.text[:120]}")

        # 2) poll /history until this prompt_id has outputs (bounded by comfyui_timeout)
        deadline = timeout
        waited = 0.0
        entry: dict = {}
        while waited < deadline:
            h = await c.get(f"{base}/history/{prompt_id}")
            if h.status_code == 200:
                entry = h.json().get(prompt_id) or {}
                if entry.get("outputs"):
                    break
            await asyncio.sleep(s.comfyui_poll_seconds)
            waited += s.comfyui_poll_seconds
        if not entry.get("outputs"):
            raise RuntimeError(f"ComfyUI timed out after {deadline:.0f}s (prompt {prompt_id})")

        # 3) locate the first produced image and download it via /view
        img = None
        for node_out in entry["outputs"].values():
            for i in node_out.get("images", []):
                img = i
                break
            if img:
                break
        if not img:
            raise RuntimeError("ComfyUI run produced no image output")
        v = await c.get(f"{base}/view", params={
            "filename": img["filename"],
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        })
        v.raise_for_status()
        if len(v.content) < 1024:
            raise RuntimeError(f"ComfyUI /view returned tiny image ({len(v.content)}B)")

    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(v.content)
    tmp.replace(out)                              # atomic publish
    _log(f"  ComfyUI {s.comfyui_checkpoint.split('.')[0]} "
         f"({s.comfyui_width}x{s.comfyui_height}, {len(v.content)//1024}KB)")
    return str(out)


# Google AI Studio model defaults (overridable via env GOOGLE_IMAGE_MODEL /
# GOOGLE_IMAGEN_MODEL). Gemini flash-image is the free-first path.
async def _google_ai_studio_image(prompt: str) -> str:
    """Google AI Studio image gen: Gemini flash-image first, Imagen as fallback.
    Both use the Generative Language API authed by GOOGLE_API_KEY (AI Studio)."""
    try:
        return await _gemini_image(prompt)
    except Exception:
        return await _imagen_image(prompt)


async def _gemini_image(prompt: str) -> str:
    """Gemini image generation via :generateContent (inline base64 image)."""
    model = settings().google_image_model
    out = _img_cache(f"gemini:{model}:{prompt}", "png")
    if out.exists():
        return str(out)
    key = settings().google_api_key
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        })
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                out.write_bytes(base64.b64decode(inline["data"]))
                return str(out)
    raise RuntimeError("gemini returned no inline image data")


async def _imagen_image(prompt: str) -> str:
    """Google Imagen via the Generative Language predict endpoint (AI Studio)."""
    model = settings().google_imagen_model
    out = _img_cache(f"imagen:{model}:{prompt}", "png")
    if out.exists():
        return str(out)
    key = settings().google_api_key
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:predict?key={key}")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, json={
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "9:16"},
        })
        r.raise_for_status()
        b64 = r.json()["predictions"][0]["bytesBase64Encoded"]
        out.write_bytes(base64.b64decode(b64))
    return str(out)


# --------- Hugging Face Inference Providers — FREE cinematic FLUX images -------- #
# Text-to-image via the HF router (https://router.huggingface.co). Hits the
# serverless provider endpoint `{router}/{provider}/models/{model}`, which returns
# RAW image bytes. Tries FLUX.1-dev (preferred look) then FLUX.1-schnell (fast free
# fallback served by `hf-inference`). It REUSES the shared documentary style +
# negative prompt, so HF output matches the Google/Pollinations look — photoreal,
# Netflix/Vox/Bloomberg, and NEVER anime/cartoon (cartoon/anime are in the negative).
# Content-addressed → generated once, reused free. Optimised for the AI-eligible
# buckets (history / politics / scandal / elections / dark-history) the decision
# engine routes here. Raises on any failure → caller degrades to Pollinations.
async def _huggingface_image(prompt: str, seed: int = 0) -> str:
    s = settings()
    token = s.hf_api_token
    if not token:
        raise RuntimeError("no HF token (HF_TOKEN / HUGGINGFACE_API_KEY unset)")
    host = s.huggingface_base_url.rstrip("/")
    if host.endswith("/v1"):                  # strip OpenAI-style suffix → router host
        host = host[: -len("/v1")]
    provider = s.huggingface_image_provider.strip("/") or "hf-inference"
    headers = {"Authorization": f"Bearer {token}"}
    models = [m for m in (s.huggingface_image_model,
                          s.huggingface_image_model_fast) if m]

    last = ""
    for model in models:
        out = _img_cache(f"hf:{provider}:{model}:{seed}:{prompt}", "png")
        if out.exists():
            return str(out)
        # schnell is a 4-step distilled model; dev wants more steps for quality.
        steps = 4 if "schnell" in model.lower() else 28
        body = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": AI_IMAGE_NEGATIVE,     # bars cartoon/anime/3d
                "num_inference_steps": steps,
                "width": 768, "height": 1344,             # 9:16 vertical (renderer crops)
                "seed": seed,
            },
        }
        url = f"{host}/{provider}/models/{model}"
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
                r = await c.post(url, headers=headers, json=body)
                if r.status_code == 503:           # model cold-loading → one retry
                    await asyncio.sleep(6)
                    r = await c.post(url, headers=headers, json=body)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ct.startswith("image") and len(r.content) >= 1024:
                tmp = out.with_name(out.name + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(out)                   # atomic publish
                _log(f"  HF FLUX via {provider}/{model.split('/')[-1]} "
                     f"({len(r.content)//1024}KB)")
                return str(out)
            # 429 rate-limit / 404 not-served-here / JSON error → record and try next.
            detail = r.text[:100].replace("\n", " ") if not ct.startswith("image") else ""
            last = f"{model.split('/')[-1]}: {r.status_code} {detail}"
        except Exception as e:  # noqa: BLE001
            last = f"{model.split('/')[-1]}: {type(e).__name__}"
    raise RuntimeError(f"huggingface unavailable ({last})")


# Pollinations' free/anonymous tier allows only ONE in-flight request per IP
# (extra concurrent calls get 402 "queue full max:1") and occasionally returns an
# empty body. The pipeline resolves scenes CONCURRENTLY, so we serialize all
# Pollinations calls through this lock and retry-with-backoff on 402/429/empty.
_POLLI_LOCK = asyncio.Lock()
_POLLI_BACKOFF = (4, 8, 14, 22)   # seconds between attempts (queue drains)


async def _pollinations_image(prompt: str, seed: int = 0) -> str:
    """Pollinations — FREE image generation (no key needed; a free POLLINATIONS_
    TOKEN lifts the rate limit). Forces photoreal documentary style (NOT cartoon/
    anime) via the prompt. Serialized + retried to respect the 1-concurrent free
    tier. Content-addressed → generated once, reused free."""
    s = settings()
    model = s.pollinations_model
    out = _img_cache(f"pollinations:{model}:{seed}:{prompt}", "jpg")
    if out.exists():
        return str(out)
    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    params = {"width": 768, "height": 1344,    # 9:16; renderer crops to fill
              "model": model, "seed": seed, "nologo": "true",
              "enhance": "false", "private": "true"}
    if s.pollinations_token:                    # registered free token (optional)
        params["token"] = s.pollinations_token
    headers = ({"Authorization": f"Bearer {s.pollinations_token}"}
               if s.pollinations_token else {})

    last = ""
    async with _POLLI_LOCK:                      # one Pollinations call at a time
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
            for i in range(len(_POLLI_BACKOFF) + 1):
                try:
                    r = await c.get(url, params=params, headers=headers)
                except Exception as e:          # noqa: BLE001
                    last = f"{type(e).__name__}"
                else:
                    ct = r.headers.get("content-type", "")
                    if r.status_code == 200 and ct.startswith("image") \
                            and len(r.content) >= 1024:
                        tmp = out.with_name(out.name + ".part")
                        tmp.write_bytes(r.content)
                        tmp.replace(out)         # atomic publish
                        return str(out)
                    last = (f"{r.status_code} {ct} {len(r.content)}B"
                            if r.status_code != 200 else "empty image")
                if i < len(_POLLI_BACKOFF):
                    await asyncio.sleep(_POLLI_BACKOFF[i])
    raise RuntimeError(f"pollinations unavailable after retries ({last})")


async def _local_cinematic_plate(subject: str, category: str, seed: int) -> str:
    """Zero-key fallback: synthesize a 1080x1920 cinematic PLATE with ffmpeg
    (graded gradient + grain + vignette). This is NOT a photoreal neural image —
    it is an atmospheric backdrop so the AI-image SLOT (and its Ken Burns motion)
    is exercised end-to-end without a paid key. Content-addressed → made once."""
    c0, c1, base = _PLATE_PALETTE.get(category, _PLATE_PALETTE["default"])
    sd = (abs(hash(subject)) + seed) % 100000
    # recipe version in the key → tweaking the palette/grade busts stale plates.
    out = _img_cache(f"plate:v2:{category}:{subject}:{seed}", "jpg")
    if out.exists():
        return str(out)
    # off-centre gradient (cinematic key-light feel) → grain → vignette → grade.
    src = (f"gradients=s=1080x1920:c0={c0}:c1={c1}:x0=360:y0=620:"
           f"x1=1020:y1=1820:nb_colors=2:seed={sd}")
    vf = ("noise=alls=11:allf=t,vignette=PI/4.6,"
          "eq=contrast=1.08:saturation=1.02:brightness=0.02,format=yuv420p")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", src, "-frames:v", "1", "-vf", vf, "-y", str(out),
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0 or not out.exists():
        raise RuntimeError("local cinematic plate generation failed")
    return str(out)


async def _download(url: str, ext: str) -> str:
    """Content-addressed cache. The filename is sha1(url) so the SAME asset is
    only ever fetched once across runs (deterministic, no duplicate downloads).
    A per-file lock collapses concurrent requests for the same URL, and the
    bytes are published atomically via rename so a crash can't leave a truncated
    file masquerading as a cache hit."""
    cache = settings().data_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    name = cache / f"{hashlib.sha1(url.encode()).hexdigest()}.{ext}"
    if name.exists():
        return str(name)
    lock = _DL_LOCKS.setdefault(str(name), asyncio.Lock())
    async with lock:
        if name.exists():                       # won the race while waiting
            return str(name)
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            tmp = name.with_name(name.name + ".part")
            tmp.write_bytes(r.content)
            tmp.replace(name)                   # atomic publish
    return str(name)
