"""A made-up service, used to practice upgrades. Standard library only.

Serves GET /health on 127.0.0.1. It answers 200 with its version, unless the release folder
contains a BROKEN file, in which case it answers 500. That lets a bad release fail the health check.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True)
    ap.add_argument("--port", type=int, required=True)
    args = ap.parse_args()
    release = Path(args.release)
    version = (release / "VERSION").read_text().strip()
    healthy = not (release / "BROKEN").exists()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health":
                self._send(404, {"status": "not found"})
            elif healthy:
                self._send(200, {"status": "ok", "version": version})
            else:
                self._send(500, {"status": "error", "version": version})

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
