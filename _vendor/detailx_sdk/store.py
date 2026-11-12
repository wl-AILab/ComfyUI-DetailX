import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .errors import DetailXError


class RequestStore:
    """Durable request snapshots; API keys are never stored here."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS requests (scope TEXT, kind TEXT, id TEXT, value TEXT NOT NULL, PRIMARY KEY(scope,kind,id))")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, scope: str, kind: str, request_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM requests WHERE scope=? AND kind=? AND id=?", (scope, kind, request_id)).fetchone()
        return json.loads(row[0]) if row else None

    def put_once(self, scope: str, kind: str, request_id: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?,?)", (scope, kind, request_id, json.dumps(value, sort_keys=True)))
            row = connection.execute("SELECT value FROM requests WHERE scope=? AND kind=? AND id=?", (scope, kind, request_id)).fetchone()
        return json.loads(row[0])

    def update(self, scope: str, kind: str, request_id: str, value: dict[str, Any]):
        with self._connect() as connection:
            connection.execute("UPDATE requests SET value=? WHERE scope=? AND kind=? AND id=?", (json.dumps(value, sort_keys=True), scope, kind, request_id))

    @staticmethod
    def require_same(actual: Any, expected: Any):
        if actual != expected:
            raise DetailXError("This request ID already has a different immutable request. Use a new ID for a new operation.", code="request_conflict")
