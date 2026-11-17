"""
Localhost-only static server for the review gallery.

Adds what `SimpleHTTPRequestHandler` lacks for video review:

  * HTTP Range (RFC 9110 §14): single `bytes=` ranges → 206 Partial Content
    with Content-Range; unsatisfiable → 416 with `bytes */size`; malformed or
    multi-range headers are ignored and the full file is served (allowed by
    the RFC). `Accept-Ranges: bytes` on every file response. Without this,
    browsers can't seek and Safari/iOS refuses to play MP4 at all.
  * If-Range: a stale validator falls back to the full 200 response.
  * Quiet disconnects: browsers abort media requests constantly (seek, switch
    video, pause-and-preload). BrokenPipe/ConnectionReset are expected, not
    errors, and are no longer printed as tracebacks.
  * /favicon.ico served from an embedded SVG.
  * Never serves SQLite catalogs (*.db) even on localhost.

Read-only: the server has no write endpoints, so it cannot approve, render or
publish anything. Those stay behind the CLI's approval and uploads_enabled gates.
"""
from __future__ import annotations

import email.utils
import functools
import http.server
import os
import re
import shutil
import socket
from http import HTTPStatus
from pathlib import Path

DISCONNECTS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout)
BLOCKED_SUFFIXES = {".db", ".db-journal", ".sqlite", ".sqlite3"}
CHUNK = 64 * 1024

FAVICON_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    b'<rect width="64" height="64" rx="14" fill="#e11d2a"/>'
    b'<text x="32" y="45" font-family="Arial Black,Arial,sans-serif" font-size="34" '
    b'font-weight="900" text-anchor="middle" fill="#ffd400">5</text></svg>'
)

_RANGE = re.compile(r"^\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*$", re.I)


def parse_range(header: str | None, size: int) -> tuple[int, int] | None | str:
    """→ (start, end) inclusive, None to serve the whole file, or "unsatisfiable"."""
    if not header or "," in header:            # absent, or multi-range: send it all
        return None
    m = _RANGE.match(header)
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None                            # malformed: ignore per RFC
    first, last = m.group(1), m.group(2)
    if first == "":                            # suffix: last N bytes
        n = int(last)
        if n == 0 or size == 0:
            return "unsatisfiable"
        return max(0, size - n), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or (last != "" and int(last) < start):
        return "unsatisfiable"
    return start, end


class GalleryHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "RankingGallery/1.0"
    protocol_version = "HTTP/1.1"              # keep-alive; media players expect it

    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mp4": "video/mp4", ".svg": "image/svg+xml",
                      ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json"}

    # -- quiet logging: errors only, one line, no tracebacks for disconnects --
    def log_message(self, fmt, *args):
        pass

    def log_error(self, fmt, *args):
        msg = fmt % args
        if "Request timed out" not in msg:
            print(f"[gallery] {self.address_string()} {msg}", flush=True)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except DISCONNECTS:
            self.close_connection = True       # client went away mid-response

    # -- routing ----------------------------------------------------------- #
    def send_head(self):
        path = self.translate_path(self.path)
        if self.path.split("?", 1)[0] == "/favicon.ico":
            return self._bytes(FAVICON_SVG, "image/svg+xml", cache="max-age=86400")
        if Path(path).suffix.lower() in BLOCKED_SUFFIXES:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return None
        if os.path.isdir(path) or not os.path.isfile(path):
            return super().send_head()         # directory listing / index / 404
        return self._file(path)

    def _bytes(self, body: bytes, ctype: str, cache: str = "no-cache"):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return None

    def _file(self, path: str):
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            st = os.fstat(f.fileno())
            size, mtime = st.st_size, st.st_mtime
            last_mod = self.date_time_string(int(mtime))
            etag = f'"{int(mtime)}-{size}"'
            rng = parse_range(self.headers.get("Range"), size)
            if rng is not None and not self._if_range_ok(etag, mtime):
                rng = None                     # resource changed: full body
            if rng == "unsatisfiable":
                f.close()
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if rng is None:
                start, end, status = 0, size - 1, HTTPStatus.OK
            else:
                start, end = rng
                status = HTTPStatus.PARTIAL_CONTENT
            self.send_response(status)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", last_mod)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")   # re-renders reuse paths
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.end_headers()
            f.seek(start)
            self._remaining = max(0, end - start + 1)
            return f
        except Exception:
            f.close()
            raise

    def _if_range_ok(self, etag: str, mtime: float) -> bool:
        cond = self.headers.get("If-Range")
        if not cond:
            return True
        if cond.startswith('"') or cond.startswith("W/"):
            return cond == etag
        try:
            return int(email.utils.parsedate_to_datetime(cond).timestamp()) >= int(mtime)
        except (TypeError, ValueError):
            return False

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return shutil.copyfileobj(source, outputfile)
        try:
            while remaining > 0:
                buf = source.read(min(CHUNK, remaining))
                if not buf:
                    break
                outputfile.write(buf)
                remaining -= len(buf)
        except DISCONNECTS:
            self.close_connection = True
        finally:
            self._remaining = None


class GalleryServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, DISCONNECTS):
            return                             # expected with media; stay silent
        print(f"[gallery] error from {client_address[0]}: {exc!r}", flush=True)


def make_server(directory: Path, port: int = 8765, host: str = "127.0.0.1") -> GalleryServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the review gallery only binds to localhost")
    handler = functools.partial(GalleryHandler, directory=str(directory))
    return GalleryServer((host, port), handler)
