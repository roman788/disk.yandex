from __future__ import annotations

import uuid
from typing import Any, Literal

import keyring
from keyring.errors import KeyringError

from app.config import KEYRING_SERVICE_NAME
from app.security import redact_secrets
from app.storage import Database, row_to_dict
from app.yandex_disk import YandexDiskClient


TokenStorage = Literal["keyring", "memory"]

_memory_tokens: dict[str, str] = {}


class AccountError(RuntimeError):
    pass


class TokenUnavailable(AccountError):
    pass


class AccountStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_account(self, *, label: str, token: str, storage: TokenStorage) -> dict[str, Any]:
        account_id = str(uuid.uuid4())
        token = token.strip()
        token_saved = False
        try:
            if storage == "keyring":
                try:
                    keyring.set_password(KEYRING_SERVICE_NAME, account_id, token)
                except KeyringError as exc:
                    raise AccountError(f"Could not save token in keyring: {redact_secrets(exc)}") from exc
            else:
                _memory_tokens[account_id] = token
            token_saved = True

            disk_info = self._get_disk_info(token)
        except Exception:
            if token_saved:
                self._discard_token(account_id, storage)
            raise

        user = disk_info.get("user") if isinstance(disk_info.get("user"), dict) else {}
        login = user.get("login") if isinstance(user, dict) else None
        display_name = user.get("display_name") if isinstance(user, dict) else None
        effective_label = label.strip() or login or "Yandex.Disk"

        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, label, login, display_name, token_storage, last_checked_at)
                VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (account_id, effective_label, login, display_name, storage),
            )
        return self.get_account(account_id) or {}

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, label, login, display_name, token_storage, created_at, updated_at, last_checked_at
                FROM accounts
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [row_to_dict(row) or {} for row in rows]

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT id, label, login, display_name, token_storage, created_at, updated_at, last_checked_at
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()
        return row_to_dict(row)

    def delete_account(self, account_id: str) -> None:
        account = self.get_account(account_id)
        if account and account["token_storage"] == "keyring":
            self._discard_token(account_id, "keyring")
        else:
            self._discard_token(account_id, "memory")
        with self.database.connect() as conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def get_token(self, account_id: str) -> str:
        account = self.get_account(account_id)
        if not account:
            raise AccountError("Account not found.")
        if account["token_storage"] == "memory":
            token = _memory_tokens.get(account_id)
        else:
            try:
                token = keyring.get_password(KEYRING_SERVICE_NAME, account_id)
            except KeyringError as exc:
                raise AccountError(f"Could not read token from keyring: {redact_secrets(exc)}") from exc
        if not token:
            raise TokenUnavailable("OAuth token is not available. Add the account again.")
        return token

    def get_client(self, account_id: str) -> YandexDiskClient:
        return YandexDiskClient(self.get_token(account_id))

    def mark_checked(self, account_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE accounts
                SET last_checked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (account_id,),
            )

    @staticmethod
    def _get_disk_info(token: str) -> dict[str, Any]:
        with YandexDiskClient(token) as client:
            return client.get_disk_info()

    @staticmethod
    def _discard_token(account_id: str, storage: TokenStorage) -> None:
        if storage == "keyring":
            try:
                keyring.delete_password(KEYRING_SERVICE_NAME, account_id)
            except KeyringError:
                pass
        _memory_tokens.pop(account_id, None)
