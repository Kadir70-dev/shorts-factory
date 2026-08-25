#!/usr/bin/env python3
"""Import a mobile recording, install local clone engines, and smoke-test them."""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "k70_host_v1"
VOICE_DIR = ROOT / "data" / "voice" / IDENTITY
REFERENCE = VOICE_DIR / "reference" / "ref_01.wav"
SCRIPT = VOICE_DIR / "RECORDING_SCRIPT.txt"
MODEL_DIR = ROOT / "data" / "models" / "openf5"
VOICE_VENV = ROOT / ".venv-voice"
OUTPUT = ROOT / "output" / "my-voice-test.wav"
OPENF5_REPO = "mrfakename/OpenF5-TTS-Base"
SUPPORTED_RECORDINGS = {".wav", ".flac", ".m4a", ".aac", ".mp3"}
TEST_TEXT = (
    "The Federal Reserve held interest rates steady as inflation cooled to "
    "three point four percent. Revenue reached four point two billion dollars."
)


def run(command: list[str], *, check: bool = True, **kwargs):
    print("  $ " + " ".join(command), flush=True)
    return subprocess.run(command, check=check, **kwargs)


def validate_wav(path: Path, *, minimum: float, maximum: float | None = None) -> None:
    if not path.is_file() or path.stat().st_size <= 256:
        raise RuntimeError(f"missing or empty WAV: {path}")
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, 44100, 2):
            raise RuntimeError(f"unexpected WAV format: {path}")
        seconds = wav.getnframes() / wav.getframerate()
        frames = wav.readframes(min(wav.getnframes(), wav.getframerate() * 30))
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    rms = int((sum(sample * sample for sample in samples) / max(1, len(samples))) ** .5)
    if seconds < minimum or (maximum is not None and seconds > maximum):
        raise RuntimeError(
            f"duration {seconds / 60:.1f} minutes is outside the required range")
    if rms < 20:
        raise RuntimeError(f"audio is effectively silent (RMS {rms})")
    print(f"  ✓ {path.relative_to(ROOT)} — {seconds:.1f}s, mono 44.1kHz, RMS {rms}")


def generate_script() -> None:
    run([sys.executable, str(ROOT / "scripts" / "voice_record_plan.py"),
         "--identity", IDENTITY, "--minutes", "25"])
    words = len(SCRIPT.read_text().split())
    minutes = words / 135
    if not 20 <= minutes <= 30:
        raise RuntimeError(f"generated script is {minutes:.1f} minutes, expected 20–30")
    print(f"  ✓ finance recording script: {words} words (~{minutes:.1f} minutes)")


def open_recording_script() -> None:
    """Open only the teleprompter; this workflow performs no audio capture."""
    try:
        subprocess.Popen(["notepad.exe", str(SCRIPT)])
    except FileNotFoundError:
        print(f"\nOpen this recording script: {SCRIPT}")


def _resolve_mobile_path(value: str) -> Path:
    value = value.strip().strip('"').strip("'")
    if not value:
        raise RuntimeError("no mobile recording path was provided")
    # Accept a pasted Windows path as well as an ordinary WSL/Linux path.
    if len(value) >= 3 and value[1:3] in (":\\", ":/") and shutil.which("wslpath"):
        converted = subprocess.run(["wslpath", "-u", value], capture_output=True,
                                   text=True, check=True).stdout.strip()
        value = converted
    return Path(value).expanduser().resolve()


def _probe_source(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate",
         "-of", "json", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffmpeg cannot read the mobile recording: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if not data.get("streams"):
        raise RuntimeError("the selected file contains no audio stream")
    return data


def import_mobile_recording() -> None:
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    if REFERENCE.exists():
        try:
            validate_wav(REFERENCE, minimum=18 * 60, maximum=35 * 60)
            answer = input("Reuse this already validated recording? [Y/n] ").strip().lower()
            if answer in ("", "y", "yes"):
                return
        except RuntimeError:
            pass

    print("\nRecord the complete script on your mobile, copy the file to this laptop,")
    print("then paste its WSL/Linux or Windows path below.")
    source = _resolve_mobile_path(input("Mobile recording path: "))
    if not source.is_file():
        raise RuntimeError(f"mobile recording not found: {source}")
    if source.suffix.lower() not in SUPPORTED_RECORDINGS:
        supported = ", ".join(sorted(SUPPORTED_RECORDINGS))
        raise RuntimeError(f"unsupported recording type {source.suffix!r}; use {supported}")

    probe = _probe_source(source)
    stream = probe["streams"][0]
    source_minutes = float(probe["format"]["duration"]) / 60
    if not 18 <= source_minutes <= 35:
        raise RuntimeError(
            f"recording is {source_minutes:.1f} minutes; expected roughly 20–30")
    if source.suffix.lower() == ".mp3":
        bitrate = int(stream.get("bit_rate") or probe["format"].get("bit_rate") or 0)
        if bitrate and bitrate < 160_000:
            raise RuntimeError(
                f"MP3 bitrate is only {bitrate // 1000} kbps; export at 160 kbps or higher")
    print(f"  ✓ source: {source_minutes:.1f} min, {stream.get('codec_name', 'audio')}, "
          f"{stream.get('sample_rate', '?')}Hz, {stream.get('channels', '?')} channel(s)")

    chain = (
        "highpass=f=70,afftdn=nr=10:nf=-28,"
        "silenceremove=start_periods=1:start_silence=0.25:start_threshold=-48dB,"
        "areverse,silenceremove=start_periods=1:start_silence=0.35:"
        "start_threshold=-48dB,areverse,"
        "loudnorm=I=-19:TP=-3:LRA=9,aresample=44100:resampler=soxr"
    )
    temporary = REFERENCE.with_suffix(".importing.wav")
    temporary.unlink(missing_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source),
         "-af", chain, "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
         "-y", str(temporary)])
    validate_wav(temporary, minimum=18 * 60, maximum=35 * 60)
    temporary.replace(REFERENCE)
    validate_wav(REFERENCE, minimum=18 * 60, maximum=35 * 60)


def install_uv() -> Path:
    existing = shutil.which("uv")
    if existing:
        return Path(existing)
    target = ROOT / ".voice-tools"
    target.mkdir(exist_ok=True)
    installer = target / "uv-install.sh"
    print("\nDownloading the uv Python installer...")
    urllib.request.urlretrieve("https://astral.sh/uv/install.sh", installer)
    env = os.environ.copy()
    env["UV_INSTALL_DIR"] = str(target / "bin")
    run(["sh", str(installer)], env=env)
    uv = target / "bin" / "uv"
    if not uv.is_file():
        raise RuntimeError("uv installation failed")
    return uv


def install_models_and_engines() -> Path:
    uv = install_uv()
    python = VOICE_VENV / "bin" / "python"
    if not python.is_file():
        print("\nCreating the isolated Python 3.11 voice environment...")
        run([str(uv), "venv", "--python", "3.11", str(VOICE_VENV)])
    else:
        print("\nReusing the existing Python 3.11 voice environment...")
    run([str(uv), "pip", "install", "--python", str(python),
         "huggingface_hub[cli]", "f5-tts", "chatterbox-tts"])

    print(f"\nDownloading the pinned Apache-2.0 model: {OPENF5_REPO}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    run([str(VOICE_VENV / "bin" / "hf"), "download", OPENF5_REPO,
         "--local-dir", str(MODEL_DIR)])
    for name in ("model.pt", "config.yaml", "vocab.txt"):
        if not (MODEL_DIR / name).is_file():
            raise RuntimeError(f"OpenF5 download did not provide {name}")
    return python


def update_reference_transcript() -> None:
    # The reference transcript is deterministic because this is a continuous read
    # of the generated script. JSON quoting is valid YAML and avoids a PyYAML
    # dependency in the bootstrap process.
    profile = ROOT / "config" / "voice" / "profile.yaml"
    text = profile.read_text()
    replacement = "    reference_text: " + json.dumps(" ".join(SCRIPT.read_text().split()))
    lines = [replacement if line.strip().startswith("reference_text:") else line
             for line in text.splitlines()]
    profile.write_text("\n".join(lines) + "\n")


def test_voice(python: Path) -> None:
    update_reference_transcript()
    temp = ROOT / "output" / ".voice-test"
    temp.mkdir(parents=True, exist_ok=True)
    chatterbox = temp / "chatterbox.wav"
    openf5 = temp / "openf5.wav"
    env = os.environ.copy()
    env["PATH"] = f"{VOICE_VENV / 'bin'}:{env.get('PATH', '')}"
    for stale in temp.glob("*.wav"):
        stale.unlink()

    print("\nTesting Chatterbox with your reference voice...")
    run([str(python), str(ROOT / "scripts" / "tts_chatterbox.py"),
         "--text", TEST_TEXT, "--out", str(chatterbox), "--reference",
         str(REFERENCE), "--device", "auto"], env=env)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(chatterbox),
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-y",
         str(chatterbox.with_suffix(".normalized.wav"))])
    chatterbox = chatterbox.with_suffix(".normalized.wav")
    validate_wav(chatterbox, minimum=.2)

    print("\nTesting Apache-2.0 OpenF5 with your reference voice...")
    run([str(python), str(ROOT / "scripts" / "tts_openf5.py"),
         "--text", TEST_TEXT, "--out", str(openf5), "--reference", str(REFERENCE),
         "--reference-text", " ".join(SCRIPT.read_text().split()),
         "--model", str(MODEL_DIR / "model.pt"),
         "--config", str(MODEL_DIR / "config.yaml"),
         "--vocab", str(MODEL_DIR / "vocab.txt")], env=env)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(openf5),
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-y",
         str(openf5.with_suffix(".normalized.wav"))])
    openf5 = openf5.with_suffix(".normalized.wav")
    validate_wav(openf5, minimum=.2)

    OUTPUT.parent.mkdir(exist_ok=True)
    listing = temp / "concat.txt"
    listing.write_text(f"file '{chatterbox}'\nfile '{openf5}'\n")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
         "-safe", "0", "-i", str(listing), "-c:a", "pcm_s16le", "-y", str(OUTPUT)])
    validate_wav(OUTPUT, minimum=.4)


def main() -> int:
    os.chdir(ROOT)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    generate_script()
    open_recording_script()
    import_mobile_recording()
    python = install_models_and_engines()
    test_voice(python)
    print(f"\n✓ Complete. Listen to: {OUTPUT}")
    print("  Piper training was not started.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled. Re-run the same command to start again.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        raise SystemExit(1)
