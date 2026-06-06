from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path.home() / ".builder-profile" / "cache"
CACHE_DB = CACHE_DIR / "llm_cache.sqlite3"


class LLMCache:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or CACHE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                prompt_hash TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_mtime REAL
            )
        """)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self._conn

    @staticmethod
    def _hash(prompt: str, model: str) -> str:
        return hashlib.sha256(f"{prompt}\x00{model}".encode()).hexdigest()

    def get(self, prompt: str, model: str, source_mtime: float | None = None) -> str | None:
        h = self._hash(prompt, model)
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT result, source_mtime FROM llm_cache WHERE prompt_hash = ?", (h,)
            ).fetchone()

        if row is None:
            return None

        if source_mtime is not None and row[1] is not None and source_mtime > row[1]:
            return None

        return str(row[0])

    def put(self, prompt: str, model: str, result: str, source_mtime: float | None = None):
        h = self._hash(prompt, model)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """INSERT OR REPLACE INTO llm_cache (prompt_hash, model, result, created_at, source_mtime)
                   VALUES (?, ?, ?, ?, ?)""",
                (h, model, result, now, source_mtime),
            )
            conn.commit()

    def clear(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM llm_cache")
        conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def stats(self) -> dict:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()
        return {"entries": row[0] if row else 0}
