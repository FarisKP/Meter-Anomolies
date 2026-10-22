"""Vercel entry point for associate-owned ticket updates."""

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
from ticket_workspace import SupabaseTicketWorkspace, TicketWorkspaceError


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if dashboard.CONFIG.data_backend != "supabase":
            self._send({"error": "Ticket editing requires the Supabase backend."}, 403)
            return
        ticket_id = parse_qs(urlparse(self.path).query).get("ticket_id", [""])[0]
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 14_000:
                raise ValueError
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            ticket = SupabaseTicketWorkspace(
                dashboard.CONFIG.supabase_url or "", dashboard.CONFIG.supabase_secret_key or ""
            ).update(ticket_id, payload)
            self._send({"ticket": ticket})
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self._send({"error": "Submit one valid ticket update."}, 400)
        except TicketWorkspaceError as error:
            self._send({"error": str(error)}, 422)

    def _send(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Data-Backend", dashboard.CONFIG.data_backend)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return
