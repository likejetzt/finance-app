"""SQLite storage for posts and the LinkedIn token."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Lifecycle: neu -> entwurf -> geplant -> veroeffentlicht
#                          \-> abgelehnt;  any step can end in fehler
STATUSES = ["neu", "entwurf", "geplant", "veroeffentlicht", "abgelehnt", "fehler"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL UNIQUE,
    source_url TEXT,
    original_text TEXT NOT NULL DEFAULT '',
    original_images TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'neu',
    de_text TEXT,
    de_images TEXT NOT NULL DEFAULT '[]',
    alt_texts TEXT NOT NULL DEFAULT '[]',
    hints TEXT NOT NULL DEFAULT '[]',
    scheduled_at TEXT,
    posted_urn TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

JSON_FIELDS = ("original_images", "de_images", "alt_texts", "hints")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        for key in JSON_FIELDS:
            item[key] = json.loads(item[key] or "[]")
        return item

    def add_post(self, source: str, source_ref: str, source_url: str | None,
                 original_text: str, original_images: list[str]) -> int | None:
        """Insert a new post; returns None if it was imported before."""
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO posts (source, source_ref, source_url, original_text,"
            " original_images, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source, source_ref, source_url, original_text, json.dumps(original_images), ts, ts),
        )
        self.conn.commit()
        return cur.lastrowid if cur.rowcount else None

    def has_ref(self, source_ref: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM posts WHERE source_ref = ?", (source_ref,)
        ).fetchone() is not None

    def get(self, post_id: int) -> dict | None:
        return self._decode(self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())

    def list(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE status = ? ORDER BY COALESCE(scheduled_at, created_at) DESC",
                (status,),
            )
        else:
            rows = self.conn.execute("SELECT * FROM posts ORDER BY COALESCE(scheduled_at, created_at) DESC")
        return [self._decode(r) for r in rows.fetchall()]

    def update(self, post_id: int, **fields) -> None:
        for key in JSON_FIELDS:
            if key in fields:
                fields[key] = json.dumps(fields[key])
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE posts SET {cols} WHERE id = ?", (*fields.values(), post_id))
        self.conn.commit()

    def due(self, now_utc: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE status = 'geplant' AND scheduled_at <= ? ORDER BY scheduled_at",
            (now_utc,),
        )
        return [self._decode(r) for r in rows.fetchall()]

    def taken_slots(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT scheduled_at FROM posts WHERE scheduled_at IS NOT NULL"
            " AND status IN ('entwurf', 'geplant', 'veroeffentlicht')"
        )
        return {r[0] for r in rows.fetchall()}

    def get_kv(self, key: str) -> dict | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_kv(self, key: str, value: dict) -> None:
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self.conn.commit()
