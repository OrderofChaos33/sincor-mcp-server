"""Per-caller daily free-tier ledger.

First ``FREE_CALLS_PER_DAY`` calls per caller ID per UTC day are free;
the ledger counts ONLY free serves (a 402 challenge and a paid settle do
not consume free quota). State is a small JSON file written atomically;
a process lock keeps the gateway's threads consistent.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config


class FreeTierLedger:
    def __init__(self, path: Path | None = None,
                 limit: int | None = None):
        self.path = Path(path) if path else config.STATE_DIR / "free_tier.json"
        self.limit = config.FREE_CALLS_PER_DAY if limit is None else limit
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            with open(self.path) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        tmp.replace(self.path)

    def _count_today(self, data: dict, caller_id: str) -> int:
        entry = data.get(caller_id) or {}
        return int(entry.get("count", 0)) if entry.get("date") == self._today() else 0

    def remaining(self, caller_id: str) -> int:
        with self._lock:
            return max(0, self.limit - self._count_today(self._load(), caller_id))

    def consume(self, caller_id: str) -> bool:
        """Count one free call for this caller. True if within quota."""
        with self._lock:
            data = self._load()
            count = self._count_today(data, caller_id)
            if count >= self.limit:
                return False
            data[caller_id] = {"date": self._today(), "count": count + 1}
            self._save(data)
            return True
