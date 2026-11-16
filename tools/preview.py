"""Serve site/ for a local preview, telling the browser never to cache, so every reload shows the latest files.

    python tools/preview.py            # http://localhost:8000
"""
import functools
import http.server
import sys
from pathlib import Path


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    site = Path(__file__).resolve().parent.parent / "site"
    handler = functools.partial(NoCache, directory=str(site))
    http.server.ThreadingHTTPServer(("", port), handler).serve_forever()
