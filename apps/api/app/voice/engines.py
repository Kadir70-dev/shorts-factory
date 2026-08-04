"""Local adapters for the one enrolled narrator identity."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from ..config import ROOT, settings
from .profile import VoiceProfile, _abs

_CHATTERBOX_SCRIPT = ROOT / "scripts" / "tts_chatterbox.py"
_OPENF5_SCRIPT = ROOT / "scripts" / "tts_openf5.py"
_KOKORO_SCRIPT = ROOT / "scripts" / "tts_kokoro.py"


class VoiceIdentityError(RuntimeError):
    """No permitted local engine could render the enrolled voice."""


# --------------------------------------------------------------------------- #
# Narration cache
#
# Synthesis is deterministic for a given (text, engine, voice, speed): the same
# line re-narrates to the same waveform. Re-running a Short after a visual-only
# edit therefore pays the full TTS cost to reproduce audio it already has. The
# cache is keyed on exactly the inputs the engines consume, so a hit is the same
# bytes the engine would have produced — the voice cannot drift through it.
#
# The stored file is the POST-normalize WAV (44.1k mono s16le), which is what
# every downstream stage reads.
# --------------------------------------------------------------------------- #
def cache_key(text: str, engine: str, profile: VoiceProfile) -> str:
    binding = profile.binding(engine)
    settings_ = dict(binding.settings) if binding else {}
    body = json.dumps({
        "text": text, "engine": engine, "identity": profile.identity,
        "speed": round(profile.speed, 4),
        "voice": settings_.get("voice", ""),
        "model": str(binding.model_path) if binding else "",
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _cache_dir() -> Path:
    path = settings().data_dir / "cache" / "narration"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_lookup(text: str, profile: VoiceProfile,
                 cascade: list[str]) -> tuple[Path, str] | None:
    """The cached WAV for the FIRST engine in the cascade that has one.

    Walking the cascade in preference order matters: a hit on a later engine
    must not shadow a cloned engine that has since become available.
    """
    for engine in cascade:
        hit = _cache_dir() / f"{cache_key(text, engine, profile)}.wav"
        if hit.is_file() and hit.stat().st_size > 256:
            return hit, engine
    return None


def cache_store(text: str, engine: str, profile: VoiceProfile,
                produced: Path) -> None:
    if not produced.is_file() or produced.stat().st_size <= 256:
        return
    target = _cache_dir() / f"{cache_key(text, engine, profile)}.wav"
    tmp = target.with_suffix(".wav.tmp")
    try:
        shutil.copyfile(produced, tmp)
        tmp.replace(target)          # atomic: no torn file for a parallel reader
    except OSError as exc:           # a cache miss is always survivable
        tmp.unlink(missing_ok=True)
        print(f"[voice] cache store failed ({type(exc).__name__}): {exc}",
              flush=True)


def _find_piper() -> str:
    configured = settings().piper_bin
    if configured and Path(configured).is_file():
        return configured
    bundled = Path(settings().tts_models_dir) / "piper" / "piper" / "piper"
    return str(bundled) if bundled.is_file() else (shutil.which("piper") or "")


async def _worker(script: Path, args: list[str], out: Path, timeout: int = 600,
                  python_bin: str = "") -> None:
    if not script.is_file():
        raise RuntimeError(f"local worker missing at {script}")
    proc = await asyncio.create_subprocess_exec(
        python_bin or sys.executable, str(script), *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"{script.stem} timed out") from None
    if proc.returncode or not out.is_file() or out.stat().st_size <= 256:
        raise RuntimeError(f"{script.stem} failed: {err.decode(errors='replace')[:240]}")


async def _chatterbox(text: str, out: Path, profile: VoiceProfile) -> None:
    binding = profile.binding("chatterbox")
    args = ["--text", text, "--out", str(out), "--reference",
            str(_abs(binding.reference_wav)), "--speed", str(profile.speed)]
    for key, value in binding.settings.items():
        if key == "python_bin":
            continue
        args.extend((f"--{key}", str(value)))
    python_bin = str(_abs(binding.settings.get("python_bin", ""))) \
        if binding.settings.get("python_bin") else ""
    await _worker(_CHATTERBOX_SCRIPT, args, out, python_bin=python_bin)


async def _openf5(text: str, out: Path, profile: VoiceProfile) -> None:
    binding = profile.binding("openf5")
    args = [
        "--text", text, "--out", str(out),
        "--reference", str(_abs(binding.reference_wav)),
        "--reference-text", binding.reference_text,
        "--model", str(_abs(binding.model_path)),
        "--config", str(_abs(binding.config_path)),
        "--vocab", str(_abs(binding.vocab_path)),
        "--speed", str(profile.speed),
    ]
    for key, value in binding.settings.items():
        if key == "python_bin":
            continue
        args.extend((f"--{key.replace('_', '-')}", str(value)))
    python_bin = str(_abs(binding.settings.get("python_bin", ""))) \
        if binding.settings.get("python_bin") else ""
    await _worker(_OPENF5_SCRIPT, args, out, python_bin=python_bin)


async def _piper(text: str, out: Path, profile: VoiceProfile) -> None:
    binding = profile.binding("piper")
    binary = _find_piper()
    if not binary:
        raise RuntimeError("piper binary not found")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{Path(binary).parent}:{env.get('LD_LIBRARY_PATH', '')}"
    args = [binary, "--model", str(_abs(binding.model_path)),
            "--output_file", str(out), "--length_scale",
            f"{1.0 / max(.5, min(2.0, profile.speed)):.3f}"]
    for option in ("noise_scale", "noise_w", "sentence_silence"):
        if option in binding.settings:
            args.extend((f"--{option}", str(binding.settings[option])))
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE, env=env)
    _, err = await asyncio.wait_for(proc.communicate(text.encode()), timeout=180)
    if proc.returncode or not out.is_file() or out.stat().st_size <= 256:
        raise RuntimeError(f"piper failed: {err.decode(errors='replace')[:240]}")


# Each worker loads the full 325 MB ONNX graph. The narration stage gathers every
# scene at once, so on a 4 GB box seven concurrent loads swap instead of running —
# a batch of seven took under a minute serialized and had not finished after 400s
# in parallel. One model resident at a time is the difference between slow and
# stuck. (`scripts/tts_kokoro.py --manifest` amortises the load across scenes and
# is the faster fix, but it needs the narration stage to hand over all scenes.)
_KOKORO_LOCK = asyncio.Semaphore(1)


async def _kokoro(text: str, out: Path, profile: VoiceProfile) -> None:
    """Stock local narrator (kokoro-onnx). NOT the enrolled identity — reachable
    only via `profile.fallback_cascade()`."""
    binding = profile.binding("kokoro")
    args = ["--model", str(_abs(binding.model_path)),
            "--voices", str(_abs(binding.voices_path)),
            "--voice", str(binding.settings.get("voice", "am_michael")),
            "--speed", f"{profile.speed:.3f}",
            "--out", str(out), "--text", text]
    async with _KOKORO_LOCK:
        await _worker(_KOKORO_SCRIPT, args, out, timeout=300)


_ADAPTERS = {"chatterbox": _chatterbox, "openf5": _openf5, "piper": _piper,
             "kokoro": _kokoro}


async def normalize(raw: Path, final: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(raw),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-y", str(final),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode or not final.is_file():
        raise RuntimeError(f"audio normalization failed: {err.decode(errors='replace')[:240]}")


async def synthesize(text: str, out: Path, profile: VoiceProfile) -> str:
    # Cloned engines first, always. A permitted stock engine is appended after
    # them, never in front, so enrolling the clone silently takes the voice back.
    cascade = profile.cascade() + profile.fallback_cascade()
    if not cascade:
        raise VoiceIdentityError(
            f"cloned voice {profile.identity!r} is unavailable:\n" +
            "\n".join(profile.diagnostics()))
    cached = cache_lookup(text, profile, cascade)
    if cached is not None:
        hit, engine = cached
        shutil.copyfile(hit, out)
        return engine

    errors: list[str] = []
    for engine in cascade:
        raw = out.with_name(f"{out.stem}.{engine}.raw")
        raw.unlink(missing_ok=True)
        try:
            await _ADAPTERS[engine](text, raw, profile)
            await normalize(raw, out)
            from .qa import inspect
            inspect(out)
            cache_store(text, engine, profile, out)
            return engine
        except Exception as exc:  # each fallback is still the enrolled identity
            errors.append(f"{engine}: {type(exc).__name__}: {str(exc)[:160]}")
            out.unlink(missing_ok=True)
        finally:
            raw.unlink(missing_ok=True)
    raise VoiceIdentityError(
        f"every local engine failed for cloned voice {profile.identity!r}: " +
        " | ".join(errors))


async def batch_kokoro(lines: list[str], outs: list[Path], profile: VoiceProfile,
                       produced: list[str | None]) -> None:
    """One Kokoro model load for all still-missing scenes.

    The per-scene adapter serialises behind _KOKORO_LOCK because each worker
    loads the full 325 MB ONNX graph and concurrent loads swap a 4 GB box into
    uselessness. Serialising fixed the thrashing but still paid one load PER
    SCENE. `--manifest` is what the worker was built for: one process, one load,
    every scene synthesised inside it.

    Indices absent from the manifest result are left untouched, so the caller's
    per-scene cascade still runs for them.
    """
    binding = profile.binding("kokoro")
    if not binding or not lines or not binding.ready()[0]:
        return
    raws = [out.with_name(f"{out.stem}.kokoro.raw") for out in outs]
    jobs = [{"text": text, "out": str(raw), "voice": str(
                binding.settings.get("voice", "am_michael")),
             "speed": round(profile.speed, 4)}
            for text, raw in zip(lines, raws)]
    manifest = outs[0].parent / "kokoro_manifest.json"
    manifest.write_text(json.dumps(jobs))
    args = ["--model", str(_abs(binding.model_path)),
            "--voices", str(_abs(binding.voices_path)),
            "--manifest", str(manifest)]
    try:
        async with _KOKORO_LOCK:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(_KOKORO_SCRIPT), *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            try:
                await asyncio.wait_for(proc.communicate(),
                                       timeout=120 + 60 * len(jobs))
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return
    except OSError as exc:
        print(f"[voice] kokoro batch could not start: {exc}", flush=True)
        return
    finally:
        manifest.unlink(missing_ok=True)

    for index, (raw, out, text) in enumerate(zip(raws, outs, lines)):
        if raw.is_file() and raw.stat().st_size > 256:
            try:
                await normalize(raw, out)
                from .qa import inspect
                inspect(out)
                cache_store(text, "kokoro", profile, out)
                produced[index] = "kokoro"
            except (RuntimeError, ValueError):
                out.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)


async def batch_piper(lines: list[str], outs: list[Path], profile: VoiceProfile,
                      produced: list[str | None]) -> None:
    """One Piper model load for all still-missing scenes."""
    binding = profile.binding("piper")
    binary = _find_piper()
    if not binding or not binary or not binding.ready()[0] or not lines:
        return
    raws = [out.with_suffix(".piper.wav") for out in outs]
    payload = "\n".join(json.dumps({"text": text, "output_file": str(raw)})
                        for text, raw in zip(lines, raws))
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{Path(binary).parent}:{env.get('LD_LIBRARY_PATH', '')}"
    proc = await asyncio.create_subprocess_exec(
        binary, "--model", str(_abs(binding.model_path)), "--json-input",
        "--output_dir", str(outs[0].parent), "--length_scale",
        f"{1.0 / max(.5, min(2.0, profile.speed)):.3f}",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE, env=env)
    try:
        await asyncio.wait_for(proc.communicate(payload.encode()), timeout=600)
    except (TimeoutError, OSError):
        proc.kill()
        await proc.wait()
        return
    for index, (raw, out) in enumerate(zip(raws, outs)):
        if raw.is_file() and raw.stat().st_size > 256:
            try:
                await normalize(raw, out)
                produced[index] = "piper"
            except RuntimeError:
                out.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)
