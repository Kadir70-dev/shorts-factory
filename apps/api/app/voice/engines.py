"""Local adapters for the one enrolled narrator identity."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from ..config import ROOT, settings
from .profile import VoiceProfile, _abs

_CHATTERBOX_SCRIPT = ROOT / "scripts" / "tts_chatterbox.py"
_OPENF5_SCRIPT = ROOT / "scripts" / "tts_openf5.py"


class VoiceIdentityError(RuntimeError):
    """No permitted local engine could render the enrolled voice."""


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


_ADAPTERS = {"chatterbox": _chatterbox, "openf5": _openf5, "piper": _piper}


async def normalize(raw: Path, final: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(raw),
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-y", str(final),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode or not final.is_file():
        raise RuntimeError(f"audio normalization failed: {err.decode(errors='replace')[:240]}")


async def synthesize(text: str, out: Path, profile: VoiceProfile) -> str:
    cascade = profile.cascade()
    if not cascade:
        raise VoiceIdentityError(
            f"cloned voice {profile.identity!r} is unavailable:\n" +
            "\n".join(profile.diagnostics()))
    errors: list[str] = []
    for engine in cascade:
        raw = out.with_name(f"{out.stem}.{engine}.raw")
        raw.unlink(missing_ok=True)
        try:
            await _ADAPTERS[engine](text, raw, profile)
            await normalize(raw, out)
            from .qa import inspect
            inspect(out)
            return engine
        except Exception as exc:  # each fallback is still the enrolled identity
            errors.append(f"{engine}: {type(exc).__name__}: {str(exc)[:160]}")
            out.unlink(missing_ok=True)
        finally:
            raw.unlink(missing_ok=True)
    raise VoiceIdentityError(
        f"every local engine failed for cloned voice {profile.identity!r}: " +
        " | ".join(errors))


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
