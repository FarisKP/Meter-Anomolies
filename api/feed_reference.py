"""Vercel entry point for the four-hour feed form's reference data."""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dashboard


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            body = json.dumps(dashboard.build_feed_reference(), separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(503)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return
