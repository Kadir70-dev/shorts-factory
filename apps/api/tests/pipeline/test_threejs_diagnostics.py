"""Three.js launch-failure diagnostics.

Regression cover for a real incident: Chromium was present and correctly
selected, but could not load because Puppeteer downloads the browser without its
system libraries. The render fell back to a chart and the pipeline printed
nothing at all — the error existed only inside `threejs_provenance`, which no
operator reads. Diagnosis took an hour for a four-package problem.

These tests pin the two behaviours that make it a one-line problem instead:
the missing soname is mapped to the package that ships it, and the failure is
actually surfaced.
"""
from __future__ import annotations

import pytest

from app.pipeline import threejs_engine as tj


# The verbatim error Puppeteer emits when NSS is absent.
REAL_ERROR = (
    "Error: Failed to launch the browser process!\n"
    "/home/u/.cache/puppeteer/chrome/linux-139.0.7258.66/chrome-linux64/chrome: "
    "error while loading shared libraries: libnspr4.so: cannot open shared "
    "object file: No such file or directory\n\n"
    "TROUBLESHOOTING: https://pptr.dev/troubleshooting"
)


def test_missing_nss_maps_to_an_install_command():
    hint = tj.diagnose_launch_failure(REAL_ERROR)
    assert hint, "a known missing library must produce remediation"
    assert "libnspr4.so" in hint, "name the library that is actually missing"
    assert "sudo apt-get install" in hint
    assert "libnspr4" in hint


def test_nss_sonames_collapse_to_one_package():
    """libnss3.so, libnssutil3.so and libsmime3.so all ship in libnss3 — the
    hint must not tell the operator to install the same package three times."""
    error = ("error while loading shared libraries: libnss3.so libnssutil3.so "
             "libsmime3.so")
    hint = tj.diagnose_launch_failure(error)
    # Assert on the install command, not the whole string — the sonames are also
    # listed (correctly) and contain the package name as a substring.
    packages = hint.split("install -y ", 1)[1].split()
    assert packages == ["libnss3"], f"packages not deduplicated: {packages}"


def test_unrelated_errors_produce_no_hint():
    """A timeout or a template error must not be reported as a missing library."""
    for error in ("TimeoutError: worker did not respond",
                  "storyboard beat does not map to a clarity-improving template",
                  ""):
        assert tj.diagnose_launch_failure(error) == ""


def test_failure_is_reported_once_not_per_scene(capsys, monkeypatch):
    """Seven scenes failing for one reason should log one remediation, not seven."""
    monkeypatch.setattr(tj, "_diagnosed", False)
    for scene_id in ("s1", "s2", "s3"):
        tj._report_failure(scene_id, REAL_ERROR)
    out = capsys.readouterr().out
    assert out.count("sudo apt-get install") == 1
    assert "s1" in out and "s2" not in out


def test_report_names_the_scene_and_the_error(capsys, monkeypatch):
    monkeypatch.setattr(tj, "_diagnosed", False)
    tj._report_failure("s6", REAL_ERROR)
    out = capsys.readouterr().out
    assert "[threejs] s6" in out
    assert "unresolved" in out


@pytest.mark.parametrize("soname,package", [
    ("libgbm.so", "libgbm1"),
    ("libatk-1.0.so", "libatk1.0-0"),
    ("libcups.so", "libcups2"),
    ("libxkbcommon.so", "libxkbcommon0"),
])
def test_other_common_headless_deps_are_mapped(soname, package):
    """The NSS set is what this machine hit; these are the other libraries a
    minimal image routinely lacks, so a different host gets a hint too."""
    hint = tj.diagnose_launch_failure(
        f"error while loading shared libraries: {soname}: cannot open")
    assert package in hint
