"""Vercel entry point for the dashboard summary-data API."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dashboard


class handler(BaseHTTPRequestHandler):
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Data-Backend", dashboard.CONFIG.data_backend)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            self.send_json(dashboard.build_data())
        except Exception:
            # Keep deployment configuration and Supabase response details server-side.
            self.send_json({"error": "Could not load dashboard data."}, status=503)

    def log_message(self, format: str, *args: object) -> None:
        return
