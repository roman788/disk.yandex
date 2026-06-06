from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import (
    HTTP_TIMEOUT_SECONDS,
    TRUSTED_UPLOAD_HOST_SUFFIXES,
    YANDEX_DISK_API_BASE,
)


class YandexDiskAPIError(RuntimeError):
    """A sanitized error raised for Yandex.Disk API failures."""

    def __init__(self, status_code: int | None, message: str, *, error_code: str | None = None) -> None:
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


def normalize_disk_path(path: str) -> str:
    value = path.strip()
    if not value:
        return "disk:/"
    if value.startswith(("disk:/", "app:/", "trash:/")):
        return value
    if value.startswith("/"):
        return f"disk:{value}"
    return f"disk:/{value}"


def _bool_query(value: bool) -> str:
    return "true" if value else "false"


def _extract_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"Yandex.Disk API returned HTTP {response.status_code}."

    for key in ("description", "message", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Yandex.Disk API returned HTTP {response.status_code}."


def _extract_error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None
    value = payload.get("error")
    return value if isinstance(value, str) else None


def _validate_upload_href(href: str) -> str:
    parsed = urlparse(href)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname:
        raise YandexDiskAPIError(None, "Upload link from Yandex.Disk API is not a valid HTTPS URL.")
    if parsed.username or parsed.password:
        raise YandexDiskAPIError(None, "Upload link from Yandex.Disk API contains credentials.")
    if hostname != "cloud-api.yandex.net" and not hostname.endswith(TRUSTED_UPLOAD_HOST_SUFFIXES):
        raise YandexDiskAPIError(None, "Upload link from Yandex.Disk API points to an unexpected host.")
    return href


class YandexDiskClient:
    """Small service-oriented wrapper around the official Yandex.Disk REST API."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = YANDEX_DISK_API_BASE,
        timeout: float = HTTP_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not token or not token.strip():
            raise ValueError("OAuth token is required.")
        self._token = token.strip()
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "YandexDiskClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def check_token(self) -> bool:
        try:
            self.get_disk_info()
            return True
        except YandexDiskAPIError as exc:
            if exc.status_code == 401:
                return False
            raise

    def get_disk_info(self) -> dict[str, Any]:
        return self._request("GET", "/")

    def list_folder(self, path: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/resources",
            params={"path": normalize_disk_path(path), "limit": 1000},
        )

    def create_folder(self, path: str) -> dict[str, Any]:
        return self._request("PUT", "/resources", params={"path": normalize_disk_path(path)})

    def ensure_folder(self, path: str) -> dict[str, Any]:
        try:
            return self.create_folder(path)
        except YandexDiskAPIError as exc:
            if exc.status_code == 409:
                return self.get_metadata(path)
            raise

    def get_metadata(self, path: str) -> dict[str, Any]:
        return self._request("GET", "/resources", params={"path": normalize_disk_path(path)})

    def get_upload_link(self, path: str, overwrite: bool = False) -> dict[str, Any]:
        return self._request(
            "GET",
            "/resources/upload",
            params={"path": normalize_disk_path(path), "overwrite": _bool_query(overwrite)},
        )

    def upload_file(self, local_path: str | os.PathLike[str], disk_path: str, overwrite: bool = False) -> dict[str, Any]:
        source = Path(local_path)
        if not source.is_file():
            raise FileNotFoundError(f"Local file does not exist: {source}")

        link = self.get_upload_link(disk_path, overwrite=overwrite)
        href = link.get("href")
        method = str(link.get("method", "PUT")).upper()
        if not isinstance(href, str) or not href:
            raise YandexDiskAPIError(None, "Yandex.Disk API did not return an upload URL.")
        if method != "PUT":
            raise YandexDiskAPIError(None, "Yandex.Disk API returned an unexpected upload method.")

        upload_url = _validate_upload_href(href)
        size = source.stat().st_size
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
            "User-Agent": "local-yandex-disk-uploader/0.1.0",
        }
        with source.open("rb") as stream:
            response = self._client.request(method, upload_url, headers=headers, content=stream)
        self._raise_for_status(response)
        return self.get_metadata(disk_path)

    def publish(self, path: str) -> dict[str, Any]:
        self._request("PUT", "/resources/publish", params={"path": normalize_disk_path(path)})
        return self._wait_for_public_url(path)

    def unpublish(self, path: str) -> dict[str, Any]:
        self._request("PUT", "/resources/unpublish", params={"path": normalize_disk_path(path)})
        return self.get_metadata(path)

    def delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", "/resources", params={"path": normalize_disk_path(path)})

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"OAuth {self._token}",
            "User-Agent": "local-yandex-disk-uploader/0.1.0",
        }

    def _request(self, method: str, endpoint: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url(endpoint)
        response = self._client.request(method, url, headers=self._headers(), params=params)
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise YandexDiskAPIError(response.status_code, "Yandex.Disk API returned invalid JSON.") from exc

    def _url(self, endpoint: str) -> str:
        if endpoint == "/":
            return f"{self._base_url}/"
        return f"{self._base_url}{endpoint}"

    def _wait_for_public_url(self, path: str, *, attempts: int = 10, delay_seconds: float = 1.0) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for _ in range(attempts):
            latest = self.get_metadata(path)
            if latest.get("public_url"):
                return latest
            time.sleep(delay_seconds)
        return latest

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        raise YandexDiskAPIError(
            response.status_code,
            _extract_api_error(response),
            error_code=_extract_error_code(response),
        )
