#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:50.300855
Revised: 2026/11/15 14:24:50.300855

A release server on localhost for the updater's tests: routes with canned replies, a declared length that can
differ from the body, bodies paced chunk by chunk, and a count of the requests each route had.
"""

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Route:
    body: bytes = b""
    status: int = 200
    length: int | None = None
    """The ``Content-Length`` sent; the body's own when ``None``, none at all when ``-1``."""
    pace: float = 0.0
    """Seconds to wait before each chunk."""
    chunk: int = 64 * 1024
    stall_after: int | None = None
    """Stop sending (but keep the connection) after this many bytes."""
    headers: dict[str, str] = field(default_factory=dict)


class ReleaseServer:
    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.requests: dict[str, int] = {}
        self.seen_headers: list[dict[str, str]] = []
        self._stop = threading.Event()
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass

            def do_GET(self) -> None:
                server.requests[self.path] = server.requests.get(self.path, 0) + 1
                server.seen_headers.append(dict(self.headers))
                route = server.routes.get(self.path, Route(b"not found", 404))
                self.send_response(route.status)
                length = len(route.body) if route.length is None else route.length
                if length >= 0:
                    self.send_header("Content-Length", str(length))
                for name, value in route.headers.items():
                    self.send_header(name, value)
                self.send_header("Connection", "close")
                self.end_headers()
                sent = 0
                try:
                    for start in range(0, len(route.body), route.chunk):
                        if route.stall_after is not None and sent >= route.stall_after:
                            server._stop.wait(120)
                            return
                        if route.pace:
                            time.sleep(route.pace)
                        piece = route.body[start : start + route.chunk]
                        self.wfile.write(piece)
                        self.wfile.flush()
                        sent += len(piece)
                except OSError:
                    pass

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._http.daemon_threads = True
        self._thread = threading.Thread(target=self._http.serve_forever, name="test-release-server", daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        host, port = self._http.server_address[:2]
        return f"http://{host}:{port}"

    def url(self, path: str) -> str:
        return self.base + path

    def close(self) -> None:
        self._stop.set()
        self._http.shutdown()
        self._http.server_close()
