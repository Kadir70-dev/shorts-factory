"""Opt-in bridge: layer-rig MP4 → existing Shorts Factory SceneGraph renderer.

No SceneGraph schema changes. Invoke this after timing/TTS and BEFORE existing
render_ffmpeg.render(); existing subtitles, branding, and final audio are reused.
Only explicitly selected scene IDs are replaced. All failures leave the caller's
graph unchanged so finance/K70 workflows never silently change.
"""
from __future__ import annotations

from pathlib import Path

from .cartoon_motion_cpu import render_manifest


def apply_cartoon_to_graph(graph, scene_manifests: dict[str, Path], output_dir: Path,
                           *, scene_voice_wavs: dict[str, Path] | None = None):
    """Return a new SceneGraph copy with cartoon scene visuals populated.

    Args:
        graph: Existing Pydantic SceneGraph after measured TTS timing.
        scene_manifests: Mapping of scene.id → sprite-rig manifest paths.
        output_dir: Working directory for silent cartoon clips.

    Requires source manifest voice_wav to be absent: existing TTS runs in the
    final render to avoid double voiceover. Pass scene_voice_wavs to use
    existing per-scene voice audio for coarse RMS mouth movement WITHOUT
    mixing it into the silent clips or duplicating narration.
    """
    if not scene_manifests:
        return graph
    known = {scene.id for scene in graph.scenes}
    unknown = set(scene_manifests) - known
    if unknown:
        raise ValueError(f'Unknown scene IDs: {sorted(unknown)}')
    output_dir = Path(output_dir)
    rendered: dict[str, Path] = {}
    for scene in graph.scenes:
        manifest = scene_manifests.get(scene.id)
        if manifest is None:
            continue
        manifest = Path(manifest)
        import json
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        if payload.get('voice_wav'):
            raise ValueError('Use silent sprite manifests with existing SceneGraph TTS')
        if int(payload.get('width', 360)) != graph.width or int(payload.get('height', 640)) != graph.height:
            raise ValueError('Cartoon manifest canvas must match SceneGraph size')
        clip = output_dir / f'cartoon_{scene.id}.mp4'
        rendered[scene.id] = render_manifest(
            manifest, clip,
            duration_override=scene.duration_sec,
            fps_override=graph.fps,
            lip_sync_override=(scene_voice_wavs or {}).get(scene.id))
    updated = graph.model_copy(deep=True)
    for scene in updated.scenes:
        if scene.id in rendered:
            scene.visual.type = 'broll'
            scene.visual.asset_path = str(rendered[scene.id])
            scene.visual.motion = 'none'
            scene.visual.layers = []
    return updated
