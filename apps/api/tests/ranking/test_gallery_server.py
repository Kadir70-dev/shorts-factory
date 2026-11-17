"""Gallery server: Range/206/416, If-Range, favicon, disconnect handling,
blocked files — against a real server on an ephemeral localhost port."""
from __future__ import annotations

import http.client
import os
import socket
import threading
import time

import pytest

from app.ranking.gallery_server import make_server, parse_range

SIZE = 300_000


@pytest.fixture
def srv(tmp_path, capfd):
    (tmp_path / "v").mkdir()
    blob = os.urandom(SIZE)
    (tmp_path / "v" / "clip.mp4").write_bytes(blob)
    (tmp_path / "ranking.db").write_bytes(b"sqlite")
    (tmp_path / "empty.mp4").write_bytes(b"")
    server = make_server(tmp_path, port=0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server.server_address[1], blob
    server.shutdown()
    server.server_close()


def _get(port, path, headers=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body


@pytest.mark.parametrize("hdr,expect", [
    (None, None), ("bytes=0-99", (0, 99)), ("bytes=100-", (100, SIZE - 1)),
    ("bytes=-500", (SIZE - 500, SIZE - 1)), ("bytes=0-999999999", (0, SIZE - 1)),
    ("bytes=-999999999", (0, SIZE - 1)), ("bytes=5-1", "unsatisfiable"),
    (f"bytes={SIZE}-", "unsatisfiable"), ("bytes=-0", "unsatisfiable"),
    ("bytes=0-1,5-9", None), ("items=0-5", None), ("bytes=abc", None), ("bytes=-", None),
])
def test_parse_range(hdr, expect):
    assert parse_range(hdr, SIZE) == expect


def test_full_get_advertises_ranges(srv):
    port, blob = srv
    r, body = _get(port, "/v/clip.mp4")
    assert r.status == 200 and body == blob
    assert r.getheader("Accept-Ranges") == "bytes"
    assert r.getheader("Content-Type") == "video/mp4"
    assert int(r.getheader("Content-Length")) == SIZE


@pytest.mark.parametrize("rng,start,end", [
    ("bytes=0-1", 0, 1), ("bytes=1000-1999", 1000, 1999),
    ("bytes=299000-", 299000, SIZE - 1), ("bytes=-4096", SIZE - 4096, SIZE - 1),
])
def test_partial_content(srv, rng, start, end):
    port, blob = srv
    r, body = _get(port, "/v/clip.mp4", {"Range": rng})
    assert r.status == 206
    assert r.getheader("Content-Range") == f"bytes {start}-{end}/{SIZE}"
    assert int(r.getheader("Content-Length")) == end - start + 1
    assert body == blob[start:end + 1]


def test_unsatisfiable_range_is_416(srv):
    port, _ = srv
    r, body = _get(port, "/v/clip.mp4", {"Range": f"bytes={SIZE + 10}-"})
    assert r.status == 416 and body == b""
    assert r.getheader("Content-Range") == f"bytes */{SIZE}"
    r, _ = _get(port, "/empty.mp4", {"Range": "bytes=0-"})
    assert r.status == 416


def test_head_with_range_has_no_body(srv):
    port, _ = srv
    r, body = _get(port, "/v/clip.mp4", {"Range": "bytes=10-19"}, method="HEAD")
    assert r.status == 206 and body == b"" and r.getheader("Content-Length") == "10"


def test_if_range_mismatch_falls_back_to_full(srv):
    port, blob = srv
    r, _ = _get(port, "/v/clip.mp4")
    etag = r.getheader("ETag")
    r, body = _get(port, "/v/clip.mp4", {"Range": "bytes=0-9", "If-Range": etag})
    assert r.status == 206 and len(body) == 10
    r, body = _get(port, "/v/clip.mp4", {"Range": "bytes=0-9", "If-Range": '"stale"'})
    assert r.status == 200 and body == blob


def test_keep_alive_serves_sequential_seeks(srv):
    """A player issues several range requests on one connection while seeking."""
    port, blob = srv
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    for a, b in ((0, 65535), (150000, 160000), (299900, 299999), (0, 10)):
        c.request("GET", "/v/clip.mp4", headers={"Range": f"bytes={a}-{b}"})
        r = c.getresponse()
        assert r.status == 206 and r.read() == blob[a:b + 1]
    c.close()


def test_favicon_and_blocked_db(srv):
    port, _ = srv
    r, body = _get(port, "/favicon.ico")
    assert r.status == 200 and r.getheader("Content-Type") == "image/svg+xml"
    assert body.startswith(b"<svg")
    assert _get(port, "/ranking.db")[0].status == 404
    assert _get(port, "/../../etc/passwd")[0].status == 404
    assert _get(port, "/missing.mp4")[0].status == 404


def test_client_disconnect_is_silent_and_server_survives(srv, capfd):
    port, blob = srv
    for _ in range(5):                         # abort mid-body, like a seek/switch
        s = socket.create_connection(("127.0.0.1", port))
        s.sendall(b"GET /v/clip.mp4 HTTP/1.1\r\nHost: x\r\n\r\n")
        s.recv(1024)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
        s.close()                              # RST
    time.sleep(0.3)
    r, body = _get(port, "/v/clip.mp4", {"Range": "bytes=0-9"})
    assert r.status == 206 and body == blob[:10]
    err = capfd.readouterr().err
    assert "Traceback" not in err and "ConnectionResetError" not in err


def test_server_refuses_non_localhost(tmp_path):
    with pytest.raises(ValueError):
        make_server(tmp_path, port=0, host="0.0.0.0")


def test_gallery_page_has_inline_favicon(tmp_path):
    from app.ranking import gallery
    from app.ranking.db import connect
    with connect(tmp_path / "g.db") as con:
        html = gallery.build(con, tmp_path / "index.html").read_text()
    assert 'rel="icon"' in html and "data:image/svg+xml," in html
