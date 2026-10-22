"""Server-side update contract for the associate ticket workspace."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class TicketWorkspaceError(RuntimeError):
    """Raised when a ticket workspace write cannot be completed."""


class SupabaseTicketWorkspace:
    """Persist bounded associate updates without exposing Supabase credentials."""

    _LIMITS = {
        "status": 32,
        "assigned_team": 64,
        "title": 255,
        "possible_cause": 1000,
        "recommended_solution": 2000,
        "associate_notes": 4000,
        "last_edited_by": 128,
    }

    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url.rstrip("/")
        self._secret_key = secret_key

    def _request(self, table: str, method: str, payload: dict[str, Any], query: dict[str, str] | None = None) -> list[dict[str, Any]]:
        target = f"{self._url}/rest/v1/{table}"
        if query:
            target = f"{target}?{urlencode(query)}"
        request = Request(
            target,
            data=json.dumps(payload).encode("utf-8"),
            method=method,
            headers={
                "apikey": self._secret_key,
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                decoded = response.read().decode("utf-8")
                value = json.loads(decoded) if decoded else []
                return value if isinstance(value, list) else []
        except HTTPError as error:
            raise TicketWorkspaceError(f"Ticket workspace request failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise TicketWorkspaceError("Could not save the ticket workspace update.") from error

    @classmethod
    def _text(cls, payload: dict[str, Any], name: str) -> str:
        value = payload.get(name, "")
        if not isinstance(value, str):
            raise TicketWorkspaceError(f"{name.replace('_', ' ').title()} must be text.")
        value = value.strip()
        if len(value) > cls._LIMITS[name]:
            raise TicketWorkspaceError(f"{name.replace('_', ' ').title()} is too long.")
        return value

    def update(self, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not ticket_id.startswith("TKT-") or len(ticket_id) > 64:
            raise TicketWorkspaceError("Invalid ticket identifier.")
        status = self._text(payload, "status").lower()
        if status not in {"open", "in_progress", "awaiting_data", "resolved"}:
            raise TicketWorkspaceError("Choose a valid ticket status.")
        values = {name: self._text(payload, name) for name in self._LIMITS if name != "status"}
        values["status"] = status
        values["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updated = self._request("investigation_tickets", "PATCH", values, {"ticket_id": f"eq.{ticket_id}"})
        if not updated:
            raise TicketWorkspaceError("Ticket not found or migration 011 has not been applied.")

        comment = payload.get("comment", "")
        if not isinstance(comment, str):
            raise TicketWorkspaceError("Comment must be text.")
        comment = comment.strip()
        if len(comment) > 2000:
            raise TicketWorkspaceError("Comment is too long.")
        if comment:
            author = values["last_edited_by"] or "Associate"
            self._request("investigation_ticket_comments", "POST", {
                "comment_id": f"TMC-{uuid4().hex.upper()}",
                "ticket_id": ticket_id,
                "author": author,
                "comment_text": comment,
                "created_at": values["updated_at"],
            })
        return updated[0]
