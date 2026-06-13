"""
Captions. Preferred path: Whisper.cpp word-level over the master VO (exact
timings, karaoke highlight). Fallback path (no whisper binary): derive caption
segments from each scene's narration spread across its MEASURED duration. The
fallback is good enough to ship and needs zero extra tooling.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from ..schemas.scene import Caption, SceneGraph

WHISPER_BIN = "/opt/whisper.cpp/main"
WHISPER_MODEL = "/opt/whisper.cpp/models/ggml-base.en.bin"
MAX_WORDS_PER_CAPTION = 4   # punchy 3-5 word caption chunks


async def transcribe(graph: SceneGraph) -> SceneGraph:
    if Path(WHISPER_BIN).exists() and graph.audio.voiceover_path:
        try:
            graph.captions = await _whisper(graph)
            return graph
        except Exception:
            pass  # fall through to script-based
    graph.captions = _from_script(graph)
    return graph


# --------------------------- whisper path ---------------------------------- #
async def _whisper(graph: SceneGraph) -> list[Caption]:
    vo = graph.audio.voiceover_path
    out = Path(vo).parent / "captions"
    proc = await asyncio.create_subprocess_exec(
        WHISPER_BIN, "-m", WHISPER_MODEL, "-f", vo,
        "-oj", "-of", str(out), "--max-len", "24", "--split-on-word", "true",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    data = json.loads(out.with_suffix(".json").read_text())
    caps: list[Caption] = []
    for seg in data.get("transcription", []):
        o = seg["offsets"]
        caps.append(Caption(
            start=o["from"] / 1000.0, end=o["to"] / 1000.0, text=seg["text"].strip(),
            words=[{"w": t["text"].strip(), "s": t["offsets"]["from"] / 1000.0,
                    "e": t["offsets"]["to"] / 1000.0}
                   for t in seg.get("tokens", []) if t["text"].strip()],
        ))
    return caps


# --------------------------- fallback path --------------------------------- #
def _from_script(graph: SceneGraph) -> list[Caption]:
    caps: list[Caption] = []
    t = 0.0
    for scene in graph.scenes:
        words = scene.narration.split()
        if not words:
            t += scene.duration_sec
            continue
        # time-budget per word inside this scene's measured window
        per_word = scene.duration_sec / len(words)
        for i in range(0, len(words), MAX_WORDS_PER_CAPTION):
            chunk = words[i:i + MAX_WORDS_PER_CAPTION]
            start = t + i * per_word
            end = t + (i + len(chunk)) * per_word
            caps.append(Caption(
                start=round(start, 3), end=round(end, 3), text=" ".join(chunk),
                words=[{"w": w, "s": round(t + (i + j) * per_word, 3),
                        "e": round(t + (i + j + 1) * per_word, 3)}
                       for j, w in enumerate(chunk)],
            ))
        t += scene.duration_sec
    return caps
