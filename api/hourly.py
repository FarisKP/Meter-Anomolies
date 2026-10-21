"""Vercel entry point for the dashboard's individual-reading API."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


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
        query = parse_qs(urlparse(self.path).query)
        customer = query.get("customer", ["all"])[0]
        days_text = query.get("days", ["90"])[0]
        try:
            days = None if days_text == "all" else max(1, min(int(days_text), 3650))
        except ValueError:
            self.send_json({"error": "days must be a whole number or 'all'."}, status=400)
            return
        try:
            self.send_json(dashboard.build_hourly_data(customer, days))
        except Exception:
            self.send_json({"error": "Could not load historical readings."}, status=503)

    def log_message(self, format: str, *args: object) -> None:
        return
