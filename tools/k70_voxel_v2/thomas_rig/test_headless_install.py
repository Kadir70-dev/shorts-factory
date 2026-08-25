"""Minimal headless-compatibility smoke test for Thomas Rig Legacy.
Does NOT build a scene, add a rig instance, or render anything --
just installs+enables the addon and checks it registers cleanly
under --background, which is the single open technical question
research flagged (its operators look UI/interactive-dialog driven).
"""
import sys
import bpy

zip_path = sys.argv[sys.argv.index("--") + 1]

try:
    bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default")
    print("K70_INSTALL_OK")
except Exception as e:
    print(f"K70_INSTALL_FAIL {type(e).__name__}: {e}")
    sys.exit(1)

try:
    bpy.ops.preferences.addon_enable(module="bl_ext.user_default.thomas_rig_legacy")
    print("K70_ENABLE_OK")
except Exception as e:
    print(f"K70_ENABLE_FAIL {type(e).__name__}: {e}")
    sys.exit(1)

print("K70_THOMAS_RIG_HEADLESS_OK")
