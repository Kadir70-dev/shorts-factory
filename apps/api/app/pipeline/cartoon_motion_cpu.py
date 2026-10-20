"""Deterministic CPU sprite-rig animator for Shorts Factory.

Renders original, separate transparent PNG character parts to video. No diffusion,
GPU, image segmentation, or third-party uploads. The manifest describes the art
and pivot points; it must NOT be a single flattened character illustration.
This module is deliberately independent of the frozen K70 documentary pipeline.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


def _xy(point: Any, label: str) -> tuple[float, float]:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        raise ValueError(f"{label} must be an [x, y] pair")
    return float(point[0]), float(point[1])


def _part(root: Path, raw: Any, label: str) -> tuple[Image.Image, tuple[float, float], tuple[float, float]]:
    if not isinstance(raw, dict) or not isinstance(raw.get('file'), str):
        raise ValueError(f"Missing rig part: {label}.file")
    path = root / raw['file']
    if not path.is_file():
        raise FileNotFoundError(f"Missing sprite for {label}: {path}")
    im = Image.open(path).convert('RGBA')
    if im.width * im.height > 4_000_000:
        raise ValueError(f"Sprite too large for low-memory mode: {label}")
    return im, _xy(raw.get('anchor'), f'{label}.anchor'), _xy(raw.get('pivot'), f'{label}.pivot')


def _attach(canvas: Image.Image, img: Image.Image, anchor: tuple[float, float],
            pivot: tuple[float, float], angle: float = 0) -> None:
    """Rotate a sprite around its local joint/pivot, landing at canvas anchor."""
    if abs(angle) < 0.00001:
        canvas.alpha_composite(img, (round(anchor[0] - pivot[0]), round(anchor[1] - pivot[1])))
        return
    # Padding avoids clipping during rotation; frame buffers remain small.
    margin = max(img.size)
    padded = Image.new('RGBA', (img.width + 2 * margin, img.height + 2 * margin))
    padded.alpha_composite(img, (margin, margin))
    spun = padded.rotate(angle, resample=Image.Resampling.BICUBIC,
                         center=(margin + pivot[0], margin + pivot[1]))
    canvas.alpha_composite(spun, (round(anchor[0] - margin - pivot[0]),
                                   round(anchor[1] - margin - pivot[1])))


@dataclass
class _VoiceEnvelope:
    rms: list[float]
    steps_per_second: int

    def active(self, t: float) -> bool:
        i = int(t * self.steps_per_second)
        return 0 <= i < len(self.rms) and self.rms[i] > 0.14


def _voice_envelope(path: Path) -> _VoiceEnvelope:
    """Cheap, deterministic RMS mouth-gating; not phoneme-level lip-sync."""
    with wave.open(str(path), 'rb') as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        if width != 2 or channels not in (1, 2):
            raise ValueError('Voice WAV must be mono/stereo 16-bit PCM')
        hop = max(1, round(rate / 20))
        level: list[float] = []
        while True:
            frames = wav.readframes(hop)
            if not frames:
                break
            nums = array.array('h')
            nums.frombytes(frames)
            if not nums:
                break
            amp = math.sqrt(sum(v * v for v in nums) / len(nums)) / 32768.0
            level.append(amp)
    peak = max(level, default=0)
    norm = [v / peak if peak else 0 for v in level]
    return _VoiceEnvelope(norm, 20)


class CartoonMotion:
    """Reusable preloaded sprite rig (one asset load per scene, not per frame)."""

    def __init__(self, manifest: dict[str, Any], root: Path):
        self.root = root
        self.width = int(manifest.get('width', 360))
        self.height = int(manifest.get('height', 640))
        self.fps = int(manifest.get('fps', 12))
        self.duration = float(manifest.get('duration_sec', 5))
        if not (120 <= self.width <= 1920 and 120 <= self.height <= 1920):
            raise ValueError('Canvas width/height out of supported bounds')
        if not (6 <= self.fps <= 30 and 0.1 < self.duration <= 600):
            raise ValueError('FPS or duration out of supported bounds')
        if self.width * self.height > 2_100_000:
            raise ValueError('Canvas too large for CPU low-memory safety')
        rig = manifest.get('rig', {})
        required = ('leg_left', 'leg_right', 'arm_left', 'body', 'arm_right', 'head')
        self.parts = {name: _part(root, rig.get(name), name) for name in required}
        self.face = {}
        for optional in ('eyes_open', 'eyes_closed', 'mouth_closed', 'mouth_open'):
            if rig.get(optional) is not None:
                self.face[optional] = _part(root, rig[optional], optional)
        self.motion = set(manifest.get('motions', ('idle', 'wave', 'blink', 'talk')))
        valid = {'idle', 'wave', 'walk', 'blink', 'talk', 'nod'}
        if not self.motion <= valid:
            raise ValueError(f'Unknown motion(s): {sorted(self.motion - valid)}')
        self.background = []
        for name in ('far', 'near'):
            path = manifest.get('background', {}).get(name)
            if path:
                image = Image.open(root / path).convert('RGBA')
                self.background.append((name, image))
        self.bg_color = manifest.get('background_color', '#b8e6fd')
        self.voice_path = root / manifest['voice_wav'] if manifest.get('voice_wav') else None
        if self.voice_path is not None and not self.voice_path.is_file():
            raise FileNotFoundError(self.voice_path)
        sync_source = root / manifest['lip_sync_wav'] if manifest.get('lip_sync_wav') else self.voice_path
        self.env = _voice_envelope(sync_source) if sync_source else None

    def _pose(self, name: str, t: float) -> tuple[float, float, float]:
        bob = 2.5 * math.sin(2 * math.pi * t / 1.5) if 'idle' in self.motion else 0
        walk = 'walk' in self.motion
        angle = 0.0
        if name.startswith('leg_') and walk:
            sign = 1 if name.endswith('left') else -1
            angle = sign * 16 * math.sin(2 * math.pi * t * 1.4)
            bob += 1.5 * abs(math.sin(2 * math.pi * t * 1.4))
        elif name.startswith('arm_'):
            if name == 'arm_right' and 'wave' in self.motion:
                angle = 35 + 28 * math.sin(2 * math.pi * t * 1.4)
            elif walk:
                sign = 1 if name.endswith('left') else -1
                angle = -sign * 12 * math.sin(2 * math.pi * t * 1.4)
        elif name == 'head' and 'nod' in self.motion:
            angle = 5 * math.sin(2 * math.pi * t / 1.9)
        return 0.0, bob, angle

    def frame(self, t: float) -> Image.Image:
        canvas = Image.new('RGBA', (self.width, self.height), self.bg_color)
        for index, (name, image) in enumerate(self.background):
            # Small parallax offsets: near moves more than far, never slideshow zoom.
            drift = round((2 if name == 'far' else 7) * math.sin(t * 0.42))
            bg = image
            if bg.size != canvas.size:
                bg = bg.resize(canvas.size, Image.Resampling.BILINEAR)
            canvas.alpha_composite(bg, (drift, 0))
        for name in ('leg_left', 'leg_right', 'arm_left', 'body', 'arm_right', 'head'):
            sprite, anchor, pivot = self.parts[name]
            dx, dy, angle = self._pose(name, t)
            if name == 'head' and self.face:
                composed = sprite.copy()
                closed = ('blink' in self.motion and (t % 2.7) > 2.58)
                is_talking = 'talk' in self.motion and (
                    self.env.active(t) if self.env else int(t * 6) % 3 != 0)
                for kind, visible in (('eyes_closed', closed), ('eyes_open', not closed),
                                      ('mouth_open', is_talking), ('mouth_closed', not is_talking)):
                    if visible and kind in self.face:
                        part, at, pivot_part = self.face[kind]
                        _attach(composed, part, at, pivot_part)
                sprite = composed
            _attach(canvas, sprite, (anchor[0] + dx, anchor[1] + dy), pivot, angle)
        return canvas.convert('RGB')


def render_manifest(manifest_path: Path, output: Path, *, duration_override: float | None = None,
                    fps_override: int | None = None,
                    lip_sync_override: Path | None = None) -> Path:
    """Render an MP4 with ffmpeg via streamed raw frames (bounded memory)."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if duration_override is not None:
        manifest['duration_sec'] = duration_override
    if fps_override is not None:
        manifest['fps'] = fps_override
    engine = CartoonMotion(manifest, manifest_path.parent)
    if lip_sync_override is not None:
        engine.env = _voice_envelope(Path(lip_sync_override))
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.stem + '.partial.mp4')
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
           '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size',
           f'{engine.width}x{engine.height}', '-framerate', str(engine.fps),
           '-i', 'pipe:0']
    if engine.voice_path:
        cmd.extend(['-i', str(engine.voice_path)])
    cmd.extend(['-map', '0:v:0'])
    if engine.voice_path:
        cmd.extend(['-map', '1:a:0', '-c:a', 'aac', '-b:a', '96k'])
    cmd.extend(['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
                '-pix_fmt', 'yuv420p', '-threads', '2', '-t', str(engine.duration),
                '-movflags', '+faststart', str(tmp)])
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        for n in range(max(1, round(engine.duration * engine.fps))):
            proc.stdin.write(engine.frame(n / engine.fps).tobytes())
        proc.stdin.close()
        assert proc.stderr is not None
        msg = proc.stderr.read().decode(errors='replace')
        status = proc.wait()
        if status:
            raise RuntimeError(f'ffmpeg failed ({status}): {msg[-1200:]}')
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise RuntimeError('ffmpeg did not produce video')
        tmp.replace(output)
        return output
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        tmp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='CPU-only character sprite animator')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(render_manifest(args.manifest, args.out))


if __name__ == '__main__':
    main()
