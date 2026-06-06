from __future__ import annotations

import tempfile
import unittest
import asyncio
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.main import _copy_upload_to_temp, _join_disk_path, _parent_disk_paths, yandex_error_handler
from app.yandex_disk.client import YandexDiskAPIError, YandexDiskClient, normalize_disk_path


class ClientTests(unittest.TestCase):
    def test_normalize_disk_path(self) -> None:
        self.assertEqual(normalize_disk_path("folder/file.txt"), "disk:/folder/file.txt")
        self.assertEqual(normalize_disk_path("/folder/file.txt"), "disk:/folder/file.txt")
        self.assertEqual(normalize_disk_path("disk:/folder"), "disk:/folder")

    def test_folder_upload_path_join_stays_under_root(self) -> None:
        self.assertEqual(_join_disk_path("disk:/uploads/", "Folder/Sub/file.txt"), "disk:/uploads/Folder/Sub/file.txt")
        self.assertEqual(_join_disk_path("disk:/uploads", "../bad/file.txt"), "disk:/uploads/bad/file.txt")

    def test_parent_disk_paths(self) -> None:
        self.assertEqual(
            _parent_disk_paths("disk:/uploads/Folder/Sub/file.txt"),
            ["disk:/uploads", "disk:/uploads/Folder", "disk:/uploads/Folder/Sub"],
        )

    def test_copy_upload_to_temp_rejects_over_limit_stream(self) -> None:
        with tempfile.NamedTemporaryFile() as tmp:
            with self.assertRaises(HTTPException) as raised:
                _copy_upload_to_temp(BytesIO(b"abcdef"), tmp, max_bytes=5)
        self.assertEqual(raised.exception.status_code, 413)

    def test_copy_upload_to_temp_accepts_stream_under_limit(self) -> None:
        with tempfile.NamedTemporaryFile() as tmp:
            copied = _copy_upload_to_temp(BytesIO(b"abc"), tmp, max_bytes=5)
            self.assertEqual(copied, 3)

    def test_yandex_error_handler_does_not_return_raw_exception_text(self) -> None:
        response = asyncio.run(yandex_error_handler(None, YandexDiskAPIError(401, "OAuth secret-token leaked")))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(b"secret-token", response.body)
        self.assertIn("OAuth", response.body.decode("utf-8"))

    def test_upload_does_not_send_authorization_to_upload_href(self) -> None:
        seen_upload_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/resources/upload"):
                return httpx.Response(200, json={"href": "https://uploader.disk.yandex.net/upload", "method": "PUT"})
            if request.url.host == "uploader.disk.yandex.net":
                seen_upload_headers.update(dict(request.headers))
                return httpx.Response(201)
            if request.url.path.endswith("/resources"):
                return httpx.Response(200, json={"path": "disk:/file.txt", "name": "file.txt"})
            return httpx.Response(404, json={"description": "not found"})

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cloud-api.yandex.net")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"hello")
            tmp_path = Path(tmp.name)
        try:
            disk = YandexDiskClient("secret-token", client=client)
            disk.upload_file(tmp_path, "disk:/file.txt")
            self.assertNotIn("authorization", {key.lower(): value for key, value in seen_upload_headers.items()})
        finally:
            tmp_path.unlink(missing_ok=True)
            client.close()

    def test_upload_rejects_unexpected_href_host(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/resources/upload"):
                return httpx.Response(200, json={"href": "https://example.com/upload", "method": "PUT"})
            return httpx.Response(200, json={})

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://cloud-api.yandex.net")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"hello")
            tmp_path = Path(tmp.name)
        try:
            disk = YandexDiskClient("secret-token", client=client)
            with self.assertRaises(YandexDiskAPIError):
                disk.upload_file(tmp_path, "disk:/file.txt")
        finally:
            tmp_path.unlink(missing_ok=True)
            client.close()


if __name__ == "__main__":
    unittest.main()
