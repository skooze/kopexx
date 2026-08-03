"""A threaded HTTP server over the standard library. No framework, no ASGI server, no bundler.

WHY THIS IS THE RIGHT SIZE. The parser-review application serves about twenty routes, two static
assets and one event stream, to one developer, on loopback. `http.server` does that with no
dependency, no supply-chain surface, no `pip-audit` obligation and no build step. rules.md
prohibits introducing a large framework without need, and the repository's whole runtime dependency
list is two packages.

WHY IT IS THREADED. A server-sent-event stream holds its connection open. A single-threaded server
would let one open stream block every other request, which is the difference between a review tool
and a hung browser tab.

REQUEST SIZE IS BOUNDED HERE. A body larger than the limit is refused before it is read into
memory. It is the one place a remote client controls an allocation.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .handlers import ReviewApp
from .router import Request

#: The largest request body accepted. Every state-changing request here is a small form post; a
#: megabyte is generous and still bounded.
MAX_REQUEST_BYTES: int = 1024 * 1024


def build_request(
    *, method: str, raw_path: str, headers: dict[str, str], body: bytes, client_host: str
) -> Request:
    """Turn raw HTTP input into the request object every handler takes."""
    split = urlsplit(raw_path)
    return Request(
        method=method.upper(),
        path=split.path or "/",
        query=parse_qs(split.query, keep_blank_values=True),
        headers={k.lower(): v for k, v in headers.items()},
        body=body,
        client_host=client_host,
    )


class _Handler(BaseHTTPRequestHandler):
    """Adapts the standard library's handler to the pure request/response handlers."""

    app: ReviewApp
    server_version = "Kopexx-Review"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        """Silence the default stderr access log.

        SECURITY-INVARIANT: it logs the full request line, which carries the query string, which
        carries entity identifiers and search terms. `packages/observability` is the single home
        for structured logging with centralized redaction; an unredacted second log is exactly what
        that rule exists to prevent.
        """
        return

    def _dispatch(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_REQUEST_BYTES:
            self.send_response(413)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = self.rfile.read(length) if length else b""
        request = build_request(
            method=method,
            raw_path=self.path,
            headers=dict(self.headers.items()),
            body=body,
            client_host=self.client_address[0] if self.client_address else "",
        )
        response = self.app.handle(request)

        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        for name, value in response.headers.items():
            self.send_header(name, value)

        if response.stream is not None:
            self.end_headers()
            try:
                for chunk in response.stream:
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # The browser navigated away mid-stream. Ordinary, and not an error.
                return
            return

        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(response.body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch("POST")

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch("HEAD")


class ReviewServer:
    """The listening server. Loopback unless deliberately configured otherwise."""

    def __init__(self, app: ReviewApp, *, host: str, port: int) -> None:
        handler = type("BoundHandler", (_Handler,), {"app": app})
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None
        self.app = app

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
