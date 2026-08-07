"""Locate the Scribus executable across platforms without hardcoding a
version-numbered path (the Windows install directory is `Scribus <version>`,
so a fixed path breaks on every Scribus upgrade)."""
from __future__ import annotations

import shutil
from pathlib import Path


def find_scribus_binary() -> str:
    found = shutil.which("scribus") or shutil.which("Scribus.exe")
    if found:
        return found

    for root in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        if not root.is_dir():
            continue
        for candidate in sorted(root.glob("Scribus*/Scribus.exe"), reverse=True):
            return str(candidate)

    for candidate in ("/usr/bin/scribus", "/usr/local/bin/scribus",
                      "/Applications/Scribus.app/Contents/MacOS/scribus"):
        if Path(candidate).is_file():
            return candidate

    return ""
