"""
Append-only audit logger.
Writes JSONL (one JSON object per line) for immutability and streaming reads.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from models.audit import AuditEntry
from config import settings


class AuditLogger:
    """Thread-safe, append-only audit logger writing to JSONL."""

    def __init__(self, log_path: str | None = None) -> None:
        self._path = Path(log_path or settings.audit_log_path)
        self._lock = asyncio.Lock()
        self._entries: list[AuditEntry] = []  # in-memory buffer for API reads

    async def log(
        self,
        actor: str,
        action: str,
        reasoning: str,
        input_summary: str = "",
        output_summary: str = "",
        metadata: dict | None = None,
    ) -> AuditEntry:
        """Create and persist an audit entry."""
        entry = AuditEntry(
            actor=actor,
            action=action,
            reasoning=reasoning,
            input_summary=input_summary[:500],   # truncate for safety
            output_summary=output_summary[:500],
            metadata=metadata or {},
        )

        async with self._lock:
            self._entries.append(entry)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")

        return entry

    async def get_entries(
        self, limit: int = 100, action_filter: str | None = None
    ) -> list[AuditEntry]:
        """Retrieve recent audit entries, optionally filtered by action."""
        entries = self._entries
        if action_filter:
            entries = [e for e in entries if e.action == action_filter]
        return entries[-limit:]


# Singleton instance
audit_logger = AuditLogger()