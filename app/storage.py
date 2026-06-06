from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import DATABASE_PATH


def utc_now_sql() -> str:
    return "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


class Database:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    login TEXT,
                    display_name TEXT,
                    token_storage TEXT NOT NULL CHECK (token_storage IN ('keyring', 'memory')),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    last_checked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS upload_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    local_filename TEXT NOT NULL,
                    local_size INTEGER NOT NULL,
                    disk_path TEXT NOT NULL,
                    overwrite INTEGER NOT NULL CHECK (overwrite IN (0, 1)),
                    published INTEGER NOT NULL CHECK (published IN (0, 1)),
                    public_url TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    completed_at TEXT,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                );
                """
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        finally:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


db = Database()

