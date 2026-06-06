from __future__ import annotations

from typing import Any

from app.storage import Database, row_to_dict


class UploadHistory:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start(
        self,
        *,
        account_id: str,
        local_filename: str,
        local_size: int,
        disk_path: str,
        overwrite: bool,
        published: bool,
    ) -> int:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO upload_history (
                    account_id, local_filename, local_size, disk_path, overwrite, published, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'in_progress')
                """,
                (account_id, local_filename, local_size, disk_path, int(overwrite), int(published)),
            )
            return int(cursor.lastrowid)

    def complete(self, upload_id: int, *, public_url: str | None) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                UPDATE upload_history
                SET status = 'completed',
                    public_url = ?,
                    completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                RETURNING *
                """,
                (public_url, upload_id),
            ).fetchone()
        return row_to_dict(row) or {}

    def fail(self, upload_id: int, *, error_message: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                UPDATE upload_history
                SET status = 'failed',
                    error_message = ?,
                    completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                RETURNING *
                """,
                (error_message, upload_id),
            ).fetchone()
        return row_to_dict(row) or {}

    def recent(self, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT h.*, a.label AS account_label
                FROM upload_history h
                JOIN accounts a ON a.id = h.account_id
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [row_to_dict(row) or {} for row in rows]

