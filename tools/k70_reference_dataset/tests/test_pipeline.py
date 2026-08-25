from pathlib import Path

from PIL import Image

from tools.k70_reference_dataset.pipeline import (_dhash, _eligible_license, connect,
                                                   discover_openverse, discover_wikimedia,
                                                   disk_guard, ensure_layout)


def test_layout_and_schema(tmp_path):
    ensure_layout(tmp_path)
    assert (tmp_path / "accepted").is_dir()
    assert (tmp_path / "contact_sheets").is_dir()
    db = connect(tmp_path)
    assert db.execute("SELECT name FROM sqlite_master WHERE name='candidates'").fetchone()
    db.close()


def test_license_fail_closed():
    assert _eligible_license("CC BY 4.0")
    assert _eligible_license("CC0")
    assert not _eligible_license("UNKNOWN")
    assert not _eligible_license("all rights reserved")


def test_dhash_is_stable_and_content_sensitive():
    a = Image.new("RGB", (128, 128), "black")
    b = Image.new("RGB", (128, 128), "black")
    for x in range(64, 128):
        for y in range(128): b.putpixel((x, y), (255, 255, 255))
    assert _dhash(a) == _dhash(a.copy())
    assert _dhash(a) != _dhash(b)


def test_disk_guard(tmp_path):
    result = disk_guard(tmp_path)
    assert result["free_gib"] > 0


def test_openverse_anonymous_page_size_is_bounded(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="page_size"):
        discover_openverse(tmp_path, queries=[], page_size=21)


def test_wikimedia_requires_real_contact_before_network(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="genuine email"):
        discover_wikimedia(tmp_path, queries=[], contact_email="<MY_EMAIL>")


def test_source_metadata_columns_exist(tmp_path):
    db = connect(tmp_path)
    columns = {row[1] for row in db.execute("PRAGMA table_info(candidates)")}
    assert {"reported_width", "reported_height", "reported_mime", "source_sha1",
            "attribution", "metadata_score"} <= columns
    db.close()
