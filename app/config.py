from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Local Yandex.Disk Uploader"
APP_VERSION = "0.1.0"

YANDEX_DISK_API_ORIGIN = "https://cloud-api.yandex.net"
YANDEX_DISK_API_BASE = f"{YANDEX_DISK_API_ORIGIN}/v1/disk"
YANDEX_OAUTH_ORIGIN = "https://oauth.yandex.ru"

FIXED_ALLOWED_EXTERNAL_ORIGINS = {
    YANDEX_DISK_API_ORIGIN,
    YANDEX_OAUTH_ORIGIN,
}

# The official upload flow returns a one-time href. It is not configured by the
# user, must be HTTPS, and must stay in Yandex-owned hostnames.
TRUSTED_UPLOAD_HOST_SUFFIXES = (
    ".yandex.net",
    ".yandex.ru",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("YDISK_LOCAL_DATA_DIR", PROJECT_ROOT / "data"))
DATABASE_PATH = Path(os.getenv("YDISK_LOCAL_DB", DATA_DIR / "app.sqlite3"))

KEYRING_SERVICE_NAME = "local-yandex-disk-uploader"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("YDISK_LOCAL_PORT", "8765"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("YDISK_HTTP_TIMEOUT", "60"))

MAX_UPLOAD_FILE_BYTES = int(os.getenv("YDISK_MAX_UPLOAD_FILE_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_UPLOAD_FOLDER_BYTES = int(os.getenv("YDISK_MAX_UPLOAD_FOLDER_BYTES", str(10 * 1024 * 1024 * 1024)))
MAX_UPLOAD_FOLDER_FILES = int(os.getenv("YDISK_MAX_UPLOAD_FOLDER_FILES", "10000"))
MIN_TEMP_FREE_BYTES = int(os.getenv("YDISK_MIN_TEMP_FREE_BYTES", str(512 * 1024 * 1024)))
