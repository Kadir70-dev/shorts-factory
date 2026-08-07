"""
Paper Craft — camera movement for a rendered document page.

Built on the same `zoompan` primitive `render_ffmpeg.py`'s `_kenburns_vf`
already uses (proven in production), parametrized differently per requested
movement rather than inventing an untested new filter shape under time
pressure. Two movements are honest approximations, documented as such:
`page_turn` (true 3D page-curl isn't expressible in a plain ffmpeg filter
graph without a shader step this pipeline doesn't have; approximated as a
fast directional wipe+scale) and `parallax` (a single flat page has no depth
layers to separate; approximated as a two-axis drift distinct from
`page_slide`'s single-axis pan, close but not a real multi-plane parallax).
"""
from __future__ import annotations

CameraMovement = str  # see spec.CameraMovement for the closed set


def camera_vf(movement: CameraMovement, w: int, h: int, fps: int, dur: float) -> str:
    n = max(1, round(dur * fps))
    base = (f"scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,"
            f"crop={2 * w}:{2 * h}")

    if movement == "slow_zoom":
        # z starts at 1.0, not 1.06: `base`'s cover-crop already discards
        # ~27% of the page's width to make a 0.77-aspect portrait page fill a
        # 0.5625-aspect vertical frame without distortion (fixed by geometry,
        # not adjustable here) — starting the zoom already 6% in threw away
        # MORE width for no reason. y is anchored toward the top-of-page
        # content cluster (every template puts its headline/body/evidence in
        # roughly the top third) instead of the page's geometric vertical
        # center, so the zoom spends the shot on actual content instead of
        # panning across blank lower-page paper.
        return (f"{base},zoompan=z='min(1.0+0.04*on/{n},1.04)':d={n}:"
                f"x='iw/2-(iw/zoom/2)':y='ih*0.30-(ih/zoom/2)':s={w}x{h}:fps={fps}")

    if movement == "page_slide":
        return (f"{base},zoompan=z='1.12':d={n}:"
                f"x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")

    if movement == "macro_close_up":
        return (f"{base},zoompan=z='min(1.05+0.55*on/{n},1.60)':d={n}:"
                f"x='iw/2-(iw/zoom/2)':y='ih*0.35-(ih/zoom/2)':s={w}x{h}:fps={fps}")

    if movement == "headline_punch_in":
        # Fast zoom onto the top third (masthead/headline zone) in the first
        # third of the shot, then hold — the "read the headline" beat.
        return (f"{base},zoompan=z='if(lt(on,{n}//3),1.0+0.35*on/({n}//3),1.35)':"
                f"d={n}:x='iw/2-(iw/zoom/2)':y='ih*0.12-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps}")

    if movement == "source_citation_reveal":
        # Mirror of headline_punch_in aimed at the page footer, arriving in
        # the FINAL third — the "here's the source" beat.
        return (f"{base},zoompan="
                f"z='if(gt(on,{n}*2//3),1.0+0.4*(on-{n}*2//3)/({n}//3),1.0)':"
                f"d={n}:x='iw/2-(iw/zoom/2)':y='ih*0.92-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps}")

    if movement == "highlight_reveal":
        return (f"{base},zoompan=z='min(1.03+0.22*on/{n},1.25)':d={n}:"
                f"x='iw/2-(iw/zoom/2)+sin(on/6)*4':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps}")

    if movement == "parallax":
        # Two-axis drift distinct from page_slide's single-axis pan — a real
        # multi-plane parallax needs depth-separated layers this engine
        # doesn't produce; this is the closest single-image approximation.
        return (f"{base},zoompan=z='1.14':d={n}:"
                f"x='(iw-iw/zoom)*on/{n}':y='(ih-ih/zoom)*0.4*sin(on/{n}*PI)':"
                f"s={w}x{h}:fps={fps}")

    if movement == "page_turn":
        # Honest approximation — see module docstring.
        half = max(1, n // 2)
        return (f"{base},zoompan=z='if(lt(on,{half}),1.0+0.10*on/{half},1.10)':"
                f"d={n}:x='iw/2-(iw/zoom/2)+(iw*0.08)*sin(on/{n}*PI)':"
                f"y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")

    # "none" or unrecognised — static hold, same fit every other still uses.
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
