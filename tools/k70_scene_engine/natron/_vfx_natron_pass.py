"""K70 VFX Director -- Natron/OpenFX compositing stage. Run by
NatronRenderer.exe (Natron 2.5.0, portable Windows build already vendored
in this repo -- see collage_scene.py for the established precedent this
follows).

Real, LIVE-introspection-confirmed plugin IDs (see _introspect_params.py's
dump -- getScriptName()/getParams() against this actual install, not
guessed), each ALSO verified by an isolated single-frame render (see
_isolate_gmic.py) since introspection alone doesn't prove a node actually
renders correctly:
  fr.inria.openfx.ReadOIIO    -- read the Blender-stage output sequence
  net.sf.openfx.GradePlugin   -- multiply/offset grade (VERIFIED working)
  eu.gmic.RainSnow            -- rain (VERIFIED working)
  eu.gmic.LightGlow           -- tinted glow accent (VERIFIED working)
  eu.gmic.AddGrain            -- film grain (VERIFIED working, but ONLY
                                after creating %AppData%/Roaming/gmic --
                                this node writes a grain-texture cache
                                there and silently produces a BLANK white
                                frame if the directory doesn't exist; the
                                director creates it defensively before
                                every Natron invocation)
  fr.inria.openfx.WriteOIIO   -- WriteFFmpeg segfaults on this build
                                (confirmed real crash, exit 139, per
                                collage_scene.py) -- PNG sequence out,
                                ffmpeg encodes the container same as
                                every other K70 style.

NOT used: eu.gmic.Vignette -- isolated test produced a BLANK white frame
every time, with a genuine internal G'MIC script error ("Undefined
variable 'blur'") on this build, not a cosmetic warning. Vignette is
instead handled entirely by the Blender compositor stage (built from
primitive nodes -- Blender has no single Vignette node either, but that
implementation is verified working).

Args are passed via the K70_VFX_NATRON_ARGS environment variable (a path
to a JSON file) -- NatronRenderer scripts have no native CLI-arg passing,
same constraint collage_scene.py worked within.

    NatronRenderer.exe _vfx_natron_pass.py
"""
import json
import os

app = app1


def main():
    args_path = os.environ["K70_VFX_NATRON_ARGS"]
    a = json.loads(open(args_path, encoding="utf-8").read())
    input_dir = a["input_dir"]
    output_dir = a["output_dir"]
    frame_start = a.get("frame_start", 0)
    frame_end = a.get("frame_end", a.get("frame_count", 1) - 1)  # inclusive
    width, height = a["width"], a["height"]
    cfg = a["natron_cfg"]

    r = app.createNode("fr.inria.openfx.ReadOIIO")
    r.setScriptName("k70_vfx_read")
    r.getParam("filename").setValue(f"{input_dir}/frame_{frame_start:04d}.png")
    last = r

    grade = app.createNode("net.sf.openfx.GradePlugin")
    grade.setScriptName("k70_vfx_grade")
    grade.connectInput(0, last)
    mult = cfg["grade_multiply"]
    off = cfg["grade_offset"]
    grade.getParam("multiply").set(mult[0], mult[1], mult[2], 1.0)
    grade.getParam("offset").set(off[0], off[1], off[2], 0.0)
    last = grade

    if cfg["rain"]:
        rain = app.createNode("eu.gmic.RainSnow")
        rain.setScriptName("k70_vfx_rain")
        rain.connectInput(0, last)
        rain.getParam("Angle").setValue(cfg["rain_angle"])
        rain.getParam("Speed").setValue(cfg["rain_speed"])
        rain.getParam("Density_").setValue(cfg["rain_density"] * 100.0)  # GMIC density is 0-100 scale
        last = rain

    if cfg["glow"]:
        glow = app.createNode("eu.gmic.LightGlow")
        glow.setScriptName("k70_vfx_glow")
        glow.connectInput(0, last)
        glow.getParam("Amplitude").setValue(cfg["glow"]["amplitude"] * 100.0)  # GMIC amplitude is 0-100 scale
        glow.getParam("Density").setValue(40.0)
        last = glow

    if cfg["grain_opacity"] > 0.001:
        grain = app.createNode("eu.gmic.AddGrain")
        grain.setScriptName("k70_vfx_grain")
        grain.connectInput(0, last)
        # NOT x100: a live calibration test (_calibrate_grain.py/_calibrate_grain2.py,
        # rendering a real HERO frame at Opacity=0.02/0.05/0.1/0.2/0.3/1/2/4/8) showed
        # this node's "Opacity" is NOT a 0-100 percentage -- 1.0 already reads as heavy,
        # dominant grain, and the previous x100 scaling (sending 2-16) made grain the
        # single most visible element in every preset. The 0-1 preset knob now maps
        # directly onto GMIC's native Opacity range, where ~0.05-0.2 is genuinely subtle.
        grain.getParam("Opacity").setValue(cfg["grain_opacity"])
        last = grain

    # Vignette is intentionally NOT applied here (eu.gmic.Vignette is
    # broken on this build -- see module docstring); Blender's stage
    # already applies it.

    w = app.createNode("fr.inria.openfx.WriteOIIO")
    w.setScriptName("k70_vfx_write")
    w.connectInput(0, last)
    # Explicit output format -- do NOT rely on auto-detection/ambient
    # Natron project-cache state: a real test showed the Write node can
    # default to an unrelated canvas size (input image confined to a
    # corner, rest black) when the project's own cached default format
    # doesn't match the actual frame dimensions. formatType=1 selects a
    # fixed/explicit format (NatronParamFormatSize).
    w.getParam("formatType").set(1)
    w.getParam("NatronParamFormatSize").set(width, height)

    # Render ONE frame at a time with a PLAIN (non-padded) filename, not
    # a single app.render(w, 0, frame_count-1) call against a '####'
    # padded filename pattern. Confirmed via a real, isolated test: a
    # padded filename makes this Write node silently IGNORE the explicit
    # format above (reverting to Natron's default 1920x1080 project
    # canvas -- the exact corner-cropped/black-bordered bug) AND makes
    # NatronRenderer immediately render its own implicit 0-250 frame
    # range regardless of the requested (0, 0) bounds.
    #
    # A SECOND real bug, found only after fixing the first: the explicit
    # format above does not actually take effect until the FIRST render
    # call on this node completes -- that first call still uses the
    # stale/default 1920x1080 canvas regardless of formatType/
    # NatronParamFormatSize being set beforehand. Confirmed via a real
    # test: two consecutive render calls on the same configured Write
    # node produced 1920x1080 then 378x672. A throwaway warm-up render
    # (discarded) forces the format to actually apply before any of the
    # real frames are written.
    warmup_path = f"{output_dir}/_warmup_discard.png"
    w.getParam("filename").setValue(warmup_path)
    app.render(w, 0, 0)
    try:
        import os as _os
        _os.remove(warmup_path)
    except OSError:
        pass

    # frame_start/frame_end let the DIRECTOR process one clip in small
    # BATCHES, each a fresh NatronRenderer invocation -- found necessary
    # after a real run hung after ~24-25 renders within a single process
    # session (reproduced identically at two different total frame
    # counts, so it's an internal resource/session limit on THIS Natron
    # build, not content-specific). Restarting the process periodically
    # avoids it entirely.
    #
    # The Read node's filename is explicitly re-set to the EXACT input
    # frame on every iteration, deliberately NOT relying on Natron's
    # implicit sequence-number auto-detection from a single literal
    # filename. That auto-detection was confirmed unreliable via pixel-
    # diffing real output: with eu.gmic.RainSnow in the chain, the whole
    # clip came out near-frozen (max channel diff of 2/255 between frames
    # 30+ apart) even though the Blender-stage input genuinely varied
    # frame to frame (diff up to ~200/255) -- i.e. the reader was serving
    # the same source image for every requested output frame. Setting the
    # filename explicitly right before each render() call, exactly like
    # the writer already does, removes any dependency on Natron's own
    # frame-to-file mapping and makes input->output frame correspondence
    # deterministic regardless of which OFX nodes are in the chain.
    for f in range(frame_start, frame_end + 1):
        r.getParam("filename").setValue(f"{input_dir}/frame_{f:04d}.png")
        w.getParam("filename").setValue(f"{output_dir}/frame.{f:04d}.png")
        app.render(w, f, f)
    print(f"K70_VFX_NATRON_PASS_OK frames={frame_start}-{frame_end}")
    w.destroy()  # prevents NatronRenderer's own implicit default-range render afterward


main()
