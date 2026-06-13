"""
TTS stage — premium documentary narration.

THE KEY INSIGHT is unchanged: we synthesize per-scene, measure the REAL audio
duration with ffprobe, overwrite scene.duration_sec, then concat the per-scene
clips into one master VO track so captions + visuals line up to the actual
spoken audio.

What this stage now does (Phase 4 + local-fallback stack):
  * ElevenLabs first — a real, authoritative American-male documentary voice,
    used ONLY while the account has credit (a 401/402/429-quota cleanly cascades).
  * NO hard ElevenLabs dependency. When ElevenLabs is unavailable or out of
    credit, narration auto-switches to FREE, CPU-only LOCAL engines:
        Kokoro (kokoro-onnx)  — primary free local documentary voice.
        Piper  (piper binary) — emergency local fallback; self-contained, offline.
    Both run as isolated subprocesses so onnxruntime/piper never load into the API
    worker and a crash can't take down the render.
  * TWO FIXED documentary voices only — a male dark-history narrator (primary) and
    a secondary voice — selected per niche via the preset `slot`.
  * A correct fallback CASCADE: ElevenLabs -> OpenAI -> Kokoro -> Piper -> espeak
    -> tone. Tried in order of availability; a per-scene failure drops to the next.
    `tone` (silence) is the never-raise backstop and is loudly flagged — in
    practice the always-available offline Piper means renders are never silent.
  * Every scene is normalised to a uniform WAV (44.1k mono) regardless of which
    provider produced it, so the concat is always glitch-free.

The pipeline contract (synthesize(graph, spec, channel)) is identical to before,
so make_gen.py and the workers are untouched.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import ROOT, ChannelConfig, settings
from ..schemas.scene import SceneGraph
from ..schemas.video_spec import VideoSpec
from .util import ffmpeg_concat_audio, ffprobe_duration

_KOKORO_SCRIPT = ROOT / "scripts" / "tts_kokoro.py"


# --------------------------------------------------------------------------- #
# Voice presets — the "premium USA Shorts narration" DNA, keyed by niche.
# ElevenLabs voice IDs are public stock voices (Adam = deep American narrator,
# Antoni = warm confident American male). stability low-ish + a touch of style
# kills the robotic rhythm; `speed` gives the slightly-brisk Bloomberg/Vox feel.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class VoicePreset:
    label: str
    el_voice: str           # ElevenLabs voice id
    el_model: str           # ElevenLabs model id
    stability: float        # lower = more expressive / less monotone
    similarity: float       # timbre lock to the voice
    style: float            # 0..1 delivery exaggeration (urgency)
    speaker_boost: bool
    speed: float            # ~1.0 natural; >1 = slightly faster pacing
    oai_voice: str          # OpenAI fallback voice (American male)
    slot: str = "primary"   # LOCAL voice slot: "primary" (dark doc) | "secondary"


_ADAM = "pNInz6obpgDQGcFmaJgB"     # deep American male — documentary narrator
_ANTONI = "ErXwobaYiN019PkySvjV"   # warm, confident American male

# serious, measured documentary — the default
_FINANCE = VoicePreset("finance: serious documentary", _ADAM,
                       "eleven_multilingual_v2", 0.50, 0.80, 0.22, True, 1.07, "onyx")
# urgent breaking-news energy — more style, less stability, a touch faster
_URGENT = VoicePreset("politics: urgent news", _ADAM,
                      "eleven_multilingual_v2", 0.38, 0.78, 0.45, True, 1.12, "onyx")
# polished, steady, professional — uses the SECONDARY local voice slot
_BUSINESS = VoicePreset("business: professional confident", _ANTONI,
                        "eleven_multilingual_v2", 0.55, 0.82, 0.18, True, 1.05, "echo",
                        slot="secondary")
# dark, slow, suspenseful — Netflix true-crime / dark-history doc narration
_DARK = VoicePreset("history: dark documentary", _ADAM,
                    "eleven_multilingual_v2", 0.45, 0.82, 0.30, True, 0.98, "onyx")

_PRESETS: dict[str, VoicePreset] = {
    "usa_finance": _FINANCE,          # economy explained — serious documentary
    "usa_politics": _URGENT,
    "usa_election": _URGENT,
    "usa_facts": _BUSINESS,           # curiosity documentary — warm, engaging
    "usa_history": _DARK,             # dark-history — slow, suspenseful
    "usa_business": _BUSINESS,        # business + tech — polished, confident
    "business": _BUSINESS,            # legacy alias
}


def _preset(channel: ChannelConfig, spec: VideoSpec) -> VoicePreset:
    """Pick the narration preset for this channel/niche (falls back to the
    serious documentary voice). A spec-level ElevenLabs voice id, if set to
    something other than the channel default, overrides the preset voice."""
    base = _PRESETS.get(channel.niche) or _PRESETS.get(spec.niche.value) or _FINANCE
    vid = getattr(spec.voice, "voice_id", "") if spec.voice else ""
    if vid and vid not in ("", "Rachel"):     # explicit override, keep the rest of the preset
        from dataclasses import replace
        return replace(base, el_voice=vid)
    return base


# --------------------------------------------------------------------------- #
# Provider cascade  (ElevenLabs → Kokoro → Piper → espeak → tone)
# --------------------------------------------------------------------------- #
# Cap concurrent cloud-TTS requests. Firing every scene at once trips the
# providers' concurrent-request limits (ElevenLabs 429s on lower tiers); a small
# semaphore keeps us premium-first without falling back to robotic voices.
_NET_SEM = asyncio.Semaphore(3)

# Once ElevenLabs returns a permanent auth/quota error (401/402 — invalid key or
# credits exhausted), we stop trying it for the REST of the process. In a 500-short
# batch this means the moment credits run out we auto-switch to Kokoro and never
# waste another EL round-trip. (Transient 429/5xx do NOT disable it — those retry.)
_EL_DISABLED = False


def _kokoro_paths() -> tuple[str, str] | None:
    """(model, voices) for kokoro-onnx if both files exist, else None."""
    s = settings()
    base = Path(s.tts_models_dir) / "kokoro"
    model = s.kokoro_model_path or str(base / "kokoro-v1.0.onnx")
    voices = s.kokoro_voices_path or str(base / "voices-v1.0.bin")
    if Path(model).exists() and Path(voices).exists() and _KOKORO_SCRIPT.exists():
        return model, voices
    return None


def _find_piper() -> str:
    """Path to the piper binary (bundled under data/models, or on PATH), or ""."""
    s = settings()
    if s.piper_bin and Path(s.piper_bin).exists():
        return s.piper_bin
    bundled = Path(s.tts_models_dir) / "piper" / "piper" / "piper"
    if bundled.exists():
        return str(bundled)
    return shutil.which("piper") or ""


def _piper_paths(slot: str) -> tuple[str, str] | None:
    """(binary, voice.onnx) for the requested voice slot if available, else None."""
    s = settings()
    binp = _find_piper()
    if not binp:
        return None
    base = Path(s.tts_models_dir) / "piper"
    if slot == "secondary":
        voice = s.piper_voice_secondary or str(base / "en_US-lessac-medium.onnx")
    else:
        voice = s.piper_voice_primary or str(base / "en_US-ryan-high.onnx")
    return (binp, voice) if Path(voice).exists() else None


def _kokoro_voice(preset: VoicePreset) -> str:
    s = settings()
    return (s.kokoro_voice_secondary if preset.slot == "secondary"
            else s.kokoro_voice_primary)


def _cascade() -> list[str]:
    """Ordered provider names by availability:
        ElevenLabs (with credit) → OpenAI → Kokoro → Piper → espeak → tone.
    Local Kokoro/Piper give a FREE, offline guarantee so `tone` (silence) is the
    never-raise backstop only — in practice it is never reached."""
    s = settings()
    order: list[str] = []
    if s.elevenlabs_api_key and not _EL_DISABLED:
        order.append("elevenlabs")
    if s.openai_api_key:
        order.append("openai")
    if _kokoro_paths():
        order.append("kokoro")
    if _find_piper():
        order.append("piper")
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        order.append("espeak")
    order.append("tone")
    return order


async def synthesize(graph: SceneGraph, spec: VideoSpec, channel: ChannelConfig) -> SceneGraph:
    out = settings().data_dir / "jobs" / graph.meta.video_id / "vo"
    out.mkdir(parents=True, exist_ok=True)

    preset = _preset(channel, spec)
    texts = [_clean(s.narration) for s in graph.scenes]
    clips = [out / f"scene_{i:02d}.wav" for i in range(len(texts))]
    produced: list[str | None] = [None] * len(texts)

    # 1) BATCH KOKORO PRE-PASS — only when a LOCAL engine is the cascade lead (i.e.
    #    ElevenLabs is absent or already exhausted this run). Renders every scene in
    #    ONE process so the 325 MB model loads once per short, not once per scene —
    #    the key optimisation for 500-short automated batches.
    lead = _cascade()[0]
    did_batch = lead == "kokoro" and _kokoro_paths() is not None
    if did_batch:
        await _kokoro_batch(texts, clips, preset, produced)

    # 2) PER-SCENE CASCADE for the EL/OAI-lead case and for any scene the batch pass
    #    missed. After a batch pass we drop kokoro from the per-scene cascade (it was
    #    just tried for these scenes) so gaps go straight to Piper.
    async def one(i: int) -> None:
        if produced[i]:
            return
        casc = _cascade()
        if did_batch:
            casc = [c for c in casc if c != "kokoro"]
        produced[i] = await _synth_scene(texts[i], clips[i], preset, casc)

    await asyncio.gather(*[one(i) for i in range(len(texts))])

    used = {}
    for e in produced:
        used[e] = used.get(e, 0) + 1
    print(f"[tts] narration engines: "
          f"{', '.join(f'{k}×{v}' for k, v in used.items())}", flush=True)
    # NEVER-SILENT guard: tone == silence. With offline Piper this should be 0.
    if used.get("tone"):
        print(f"[tts] ⚠️  {used['tone']} scene(s) fell to SILENCE (tone) — local "
              "engines unavailable; install Kokoro/Piper models", flush=True)

    # overwrite estimated durations with measured reality
    for scene, clip in zip(graph.scenes, clips):
        scene.duration_sec = round(ffprobe_duration(clip), 3)

    master = out / "voiceover.wav"
    ffmpeg_concat_audio(clips, master)
    graph.audio.voiceover_path = str(master)
    graph.audio.music_path = _pick_music(channel)
    return graph


# --------------------------------------------------------------------------- #
# Per-scene synthesis with cascade fallback
# --------------------------------------------------------------------------- #
async def _synth_scene(text: str, final: Path, preset: VoicePreset,
                       cascade: list[str]) -> str:
    """Try providers in cascade order; first success wins. Every provider writes
    a raw file which we then normalise to a uniform WAV."""
    raw = final.with_suffix(".raw")
    for name in cascade:
        try:
            if name == "elevenlabs":
                await _elevenlabs(text, raw, preset)
            elif name == "openai":
                await _openai(text, raw, preset)
            elif name == "kokoro":
                await _kokoro(text, raw, preset)
            elif name == "piper":
                await _piper(text, raw, preset)
            elif name == "espeak":
                await _espeak(text, raw, preset)
            else:
                await _tone(text, raw, preset)
            if raw.exists() and raw.stat().st_size > 256:
                await _to_wav(raw, final)
                raw.unlink(missing_ok=True)
                return name
        except Exception:                      # noqa: BLE001 — degrade, try next
            continue
    # absolute last resort: a silent clip sized to the text (never raises)
    await _tone(text, raw, preset)
    await _to_wav(raw, final)
    raw.unlink(missing_ok=True)
    return "tone"


# --------------------------------------------------------------------------- #
# Local FREE engines — Kokoro (primary) and Piper (emergency). CPU-only, offline.
# --------------------------------------------------------------------------- #
async def _kokoro_batch(texts: list[str], clips: list[Path], preset: VoicePreset,
                        produced: list[str | None]) -> None:
    """Synthesise every scene of a short in ONE Kokoro process (model loaded once).
    Best-effort: scenes that fail stay None for the per-scene cascade to fill."""
    paths = _kokoro_paths()
    if not paths:
        return
    model, voices = paths
    voice = _kokoro_voice(preset)
    raws = [c.with_suffix(".kok.wav") for c in clips]
    manifest = [{"text": t, "out": str(r), "voice": voice,
                 "speed": round(preset.speed, 2)} for t, r in zip(texts, raws)]
    mf = clips[0].parent / "kokoro_manifest.json"
    mf.write_text(json.dumps(manifest))
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(_KOKORO_SCRIPT), "--model", model,
            "--voices", voices, "--manifest", str(mf),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=600)
    except Exception:                          # noqa: BLE001
        return
    for i, raw in enumerate(raws):
        if raw.exists() and raw.stat().st_size > 256:
            try:
                await _to_wav(raw, clips[i])
                produced[i] = "kokoro"
            except Exception:                  # noqa: BLE001
                pass
            raw.unlink(missing_ok=True)
    mf.unlink(missing_ok=True)
    n = sum(1 for p in produced if p == "kokoro")
    print(f"[tts] Kokoro batch: {n}/{len(texts)} scenes (single model load, "
          f"voice={voice})", flush=True)


async def _kokoro(text: str, out: Path, preset: VoicePreset) -> None:
    """Single-scene Kokoro (used when EL/OAI is the lead and a scene cascades down).
    Spawns the isolated worker so onnxruntime never enters this process."""
    paths = _kokoro_paths()
    if not paths:
        raise RuntimeError("kokoro models not installed")
    model, voices = paths
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(_KOKORO_SCRIPT), "--model", model, "--voices", voices,
        "--voice", _kokoro_voice(preset), "--speed", f"{preset.speed:.2f}",
        "--out", str(out), "--text", text,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=180)
    if not (out.exists() and out.stat().st_size > 256):
        raise RuntimeError(f"kokoro failed: {err.decode()[:160]}")


async def _piper(text: str, out: Path, preset: VoicePreset) -> None:
    """Emergency local voice — the self-contained Piper binary (offline, no Python
    deps). `length_scale` = 1/speed maps the preset pacing onto Piper."""
    paths = _piper_paths(preset.slot)
    if not paths:
        raise RuntimeError("piper not installed")
    binp, voice = paths
    env = os.environ.copy()                    # piper finds its bundled .so neighbours
    env["LD_LIBRARY_PATH"] = f"{Path(binp).parent}:{env.get('LD_LIBRARY_PATH', '')}"
    length_scale = 1.0 / max(0.5, min(2.0, preset.speed))
    proc = await asyncio.create_subprocess_exec(
        binp, "--model", voice, "--output_file", str(out),
        "--length_scale", f"{length_scale:.3f}",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, env=env,
    )
    await asyncio.wait_for(proc.communicate(text.encode()), timeout=180)
    if not (out.exists() and out.stat().st_size > 256):
        raise RuntimeError("piper produced no audio")


async def _elevenlabs(text: str, out: Path, p: VoicePreset) -> None:
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{p.el_voice}"
           "?output_format=mp3_44100_128")
    body = json.dumps({
        "text": text,
        "model_id": p.el_model,
        "voice_settings": {
            "stability": p.stability,
            "similarity_boost": p.similarity,
            "style": p.style,
            "use_speaker_boost": p.speaker_boost,
            "speed": p.speed,
        },
    })
    headers = {"xi-api-key": settings().elevenlabs_api_key,
               "accept": "audio/mpeg", "content-type": "application/json"}
    global _EL_DISABLED
    async with _NET_SEM:                       # respect concurrency limits
        status = None
        for attempt in range(3):
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(url, headers=headers, content=body)
            if r.status_code == 200:
                out.write_bytes(r.content)     # mp3; _to_wav normalises it
                return
            status = r.status_code
            # 401/402/403 = invalid key or credits EXHAUSTED → permanent for this
            # run. Disable EL so every later scene/short skips straight to Kokoro.
            if status in (401, 402, 403):
                _EL_DISABLED = True
                print(f"[tts] ElevenLabs unavailable (status {status}: invalid key "
                      "or credits exhausted) → auto-switching to Kokoro for the rest "
                      "of this run", flush=True)
                raise RuntimeError(f"elevenlabs disabled (status {status})")
            if status in (429, 500, 502, 503):  # transient -> back off and retry
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            r.raise_for_status()               # hard error -> cascade to next provider
        raise RuntimeError(f"elevenlabs failed (status {status}) after retries")


async def _openai(text: str, out: Path, p: VoicePreset) -> None:
    async with _NET_SEM:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings().openai_api_key}"},
                json={"model": "tts-1-hd", "voice": p.oai_voice, "input": text,
                      "response_format": "wav", "speed": round(p.speed, 2)},
            )
            r.raise_for_status()
            out.write_bytes(r.content)


async def _espeak(text: str, out: Path, p: VoicePreset) -> None:
    """Local American-English fallback (apt install espeak-ng). Robotic, but real
    speech — and it respects the preset's slightly-faster pacing."""
    binary = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
    rate = str(int(170 * p.speed))             # ~170 wpm baseline, nudged by speed
    proc = await asyncio.create_subprocess_exec(
        binary, "-v", "en-us", "-s", rate, "-w", str(out), text,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


async def _tone(text: str, out: Path, p: VoicePreset) -> None:
    """No speech tool at all: emit silence sized to the estimated speaking time
    (~2.6 words/sec, scaled by pacing) so the timeline still flows."""
    secs = max(1.0, len(text.split()) / (2.6 * p.speed))
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono", "-t", f"{secs:.2f}",
        "-f", "wav", "-y", str(out),           # force WAV: the .raw ext can't be inferred
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


async def _to_wav(raw: Path, final: Path) -> None:
    """Normalise any provider output (mp3/wav, any rate) to a uniform mono 44.1k
    PCM WAV so per-scene clips concat cleanly. Speed is already baked in by each
    provider, so this is a straight transcode."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(raw),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-y", str(final),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not final.exists():
        raise RuntimeError(f"ffmpeg wav normalise failed: {err.decode()[:200]}")


def _clean(text: str) -> str:
    """Light normalisation for clean prosody: collapse whitespace and ensure the
    line ends on sentence punctuation so the voice lands a clean closing pause."""
    t = " ".join(text.split())
    if t and t[-1] not in ".!?":
        t += "."
    return t


def _pick_music(channel: ChannelConfig) -> str | None:
    d = Path(channel.music_dir)
    beds = sorted(d.glob("*.mp3")) if d.exists() else []
    return str(beds[0]) if beds else None   # v1: deterministic; v2: rotate
