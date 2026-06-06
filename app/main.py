from __future__ import annotations

import os
import posixpath
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any, BinaryIO

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.accounts import AccountError, AccountStore, TokenUnavailable
from app.config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_FOLDER_BYTES,
    MAX_UPLOAD_FOLDER_FILES,
    MIN_TEMP_FREE_BYTES,
    PROJECT_ROOT,
)
from app.history import UploadHistory
from app.schemas import AddAccountRequest, PathRequest
from app.security import (
    LocalAPIMutationHeaderMiddleware,
    LocalOnlyMiddleware,
    configure_safe_logging,
)
from app.storage import db
from app.yandex_disk import YandexDiskAPIError
from app.yandex_disk.client import normalize_disk_path


configure_safe_logging()
db.initialize()
accounts = AccountStore(db)
history = UploadHistory(db)

app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url=None, redoc_url=None)
app.add_middleware(LocalAPIMutationHeaderMiddleware)
app.add_middleware(LocalOnlyMiddleware)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")

FOLDER_UPLOAD_EXCLUDED_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

METADATA_RESPONSE_FIELDS = (
    "path",
    "type",
    "name",
    "created",
    "modified",
    "size",
    "mime_type",
    "md5",
    "sha256",
    "media_type",
    "antivirus_status",
    "public_url",
)


def _safe_yandex_error_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "Яндекс.Диск отклонил запрос. Проверьте OAuth-токен и права доступа."
    if status_code == 404:
        return "Ресурс на Яндекс.Диске не найден."
    if status_code == 409:
        return "Ресурс уже существует или конфликтует с текущим состоянием Яндекс.Диска."
    if status_code == 413:
        return "Яндекс.Диск отклонил слишком большой запрос."
    return "Яндекс.Диск вернул ошибку. Проверьте путь, токен и доступ к файлу."


@app.exception_handler(YandexDiskAPIError)
async def yandex_error_handler(_request, exc: YandexDiskAPIError) -> JSONResponse:
    status_code = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
    return JSONResponse({"detail": _safe_yandex_error_message(status_code)}, status_code=status_code)


@app.exception_handler(AccountError)
async def account_error_handler(_request, exc: AccountError) -> JSONResponse:
    status_code = 401 if isinstance(exc, TokenUnavailable) else 400
    detail = "Токен аккаунта недоступен. Добавьте аккаунт заново." if status_code == 401 else "Не удалось обработать аккаунт."
    return JSONResponse({"detail": detail}, status_code=status_code)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/accounts", status_code=201)
def add_account(payload: AddAccountRequest) -> dict[str, Any]:
    return accounts.create_account(label=payload.label, token=payload.token, storage=payload.storage)


@app.get("/api/accounts")
def list_accounts() -> list[dict[str, Any]]:
    return accounts.list_accounts()


@app.delete("/api/accounts/{account_id}", status_code=204, response_class=Response)
def delete_account(account_id: str) -> Response:
    accounts.delete_account(account_id)
    return Response(status_code=204)


@app.post("/api/accounts/{account_id}/check")
def check_account(account_id: str) -> dict[str, bool]:
    with accounts.get_client(account_id) as client:
        ok = client.check_token()
    if ok:
        accounts.mark_checked(account_id)
    return {"ok": ok}


@app.get("/api/accounts/{account_id}/disk-info")
def disk_info(account_id: str) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        result = client.get_disk_info()
    accounts.mark_checked(account_id)
    return result


@app.get("/api/accounts/{account_id}/list")
def list_folder(account_id: str, path: Annotated[str, Query()] = "disk:/") -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.list_folder(path)


@app.get("/api/accounts/{account_id}/metadata")
def metadata(account_id: str, path: Annotated[str, Query(min_length=1)]) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.get_metadata(path)


@app.post("/api/accounts/{account_id}/folders", status_code=201)
def create_folder(account_id: str, payload: PathRequest) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.create_folder(payload.path)


@app.post("/api/accounts/{account_id}/publish")
def publish(account_id: str, payload: PathRequest) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.publish(payload.path)


@app.post("/api/accounts/{account_id}/unpublish")
def unpublish(account_id: str, payload: PathRequest) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.unpublish(payload.path)


@app.delete("/api/accounts/{account_id}/resource")
def delete_resource(account_id: str, path: Annotated[str, Query(min_length=1)]) -> dict[str, Any]:
    with accounts.get_client(account_id) as client:
        return client.delete(path)


def _join_disk_path(base_path: str, relative_path: str) -> str:
    base = normalize_disk_path(base_path)
    prefix, _, raw_path = base.partition(":")
    root = raw_path if raw_path.startswith("/") else f"/{raw_path}"
    safe_parts = []
    for part in relative_path.replace("\\", "/").split("/"):
        if not part or part in {".", ".."}:
            continue
        safe_parts.append(part)
    joined = posixpath.normpath(posixpath.join(root, *safe_parts))
    if not joined.startswith("/"):
        joined = f"/{joined}"
    return f"{prefix}:{joined}"


def _parent_disk_paths(disk_path: str) -> list[str]:
    prefix, _, raw_path = disk_path.partition(":")
    parent = posixpath.dirname(raw_path)
    parents: list[str] = []
    while parent and parent != "/":
        parents.append(f"{prefix}:{parent}")
        parent = posixpath.dirname(parent)
    return list(reversed(parents))


def _relative_path_parts(relative_path: str) -> list[str]:
    return [part for part in relative_path.replace("\\", "/").split("/") if part and part not in {".", ".."}]


def _should_skip_folder_upload_path(relative_path: str) -> bool:
    return any(part in FOLDER_UPLOAD_EXCLUDED_PARTS for part in _relative_path_parts(relative_path))


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {key: metadata[key] for key in METADATA_RESPONSE_FIELDS if key in metadata}


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / 1024 / 1024:.1f} MB"
    return f"{value / 1024 / 1024 / 1024:.1f} GB"


def _ensure_temp_space() -> None:
    free_bytes = shutil.disk_usage(tempfile.gettempdir()).free
    if free_bytes < MIN_TEMP_FREE_BYTES:
        raise HTTPException(
            status_code=507,
            detail=f"Недостаточно свободного места во временной папке. Нужно минимум {_format_bytes(MIN_TEMP_FREE_BYTES)}.",
        )


def _copy_upload_to_temp(source: BinaryIO, destination: BinaryIO, *, max_bytes: int) -> int:
    _ensure_temp_space()
    copied = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            break
        copied += len(chunk)
        if copied > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой. Максимум {_format_bytes(MAX_UPLOAD_FILE_BYTES)} на файл.",
            )
        destination.write(chunk)
        if shutil.disk_usage(tempfile.gettempdir()).free < MIN_TEMP_FREE_BYTES:
            raise HTTPException(
                status_code=507,
                detail=f"Недостаточно свободного места во временной папке. Нужно минимум {_format_bytes(MIN_TEMP_FREE_BYTES)}.",
            )
    return copied


@app.post("/api/accounts/{account_id}/upload")
def upload_file(
    account_id: str,
    file: Annotated[UploadFile, File()],
    disk_path: Annotated[str, Form()],
    overwrite: Annotated[bool, Form()] = False,
    publish_after_upload: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a file to upload.")

    target_path = normalize_disk_path(disk_path)
    if target_path.endswith("/"):
        target_path = f"{target_path}{Path(file.filename).name}"

    temp_name: str | None = None
    upload_id: int | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_name = tmp.name
            size = _copy_upload_to_temp(file.file, tmp, max_bytes=MAX_UPLOAD_FILE_BYTES)
        upload_id = history.start(
            account_id=account_id,
            local_filename=Path(file.filename).name,
            local_size=size,
            disk_path=target_path,
            overwrite=overwrite,
            published=publish_after_upload,
        )

        with accounts.get_client(account_id) as client:
            metadata_result = client.upload_file(temp_name, target_path, overwrite=overwrite)
            public_url: str | None = None
            if publish_after_upload:
                metadata_result = client.publish(target_path)
                public_url_value = metadata_result.get("public_url")
                public_url = public_url_value if isinstance(public_url_value, str) else None

        return {"metadata": _safe_metadata(metadata_result), "history": history.complete(upload_id, public_url=public_url)}
    except Exception as exc:
        safe_message = "Не удалось загрузить файл."
        if isinstance(exc, HTTPException) and isinstance(exc.detail, str):
            safe_message = exc.detail
        elif isinstance(exc, YandexDiskAPIError):
            status_code = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
            safe_message = _safe_yandex_error_message(status_code)
        elif isinstance(exc, TokenUnavailable):
            safe_message = "Токен аккаунта недоступен. Добавьте аккаунт заново."
        elif isinstance(exc, AccountError):
            safe_message = "Не удалось обработать аккаунт."
        if upload_id is not None:
            history.fail(upload_id, error_message=safe_message)
        if isinstance(exc, (YandexDiskAPIError, AccountError, HTTPException)):
            raise
        raise HTTPException(status_code=500, detail="Не удалось загрузить файл.") from exc
    finally:
        if temp_name:
            try:
                os.remove(temp_name)
            except OSError:
                pass


@app.post("/api/accounts/{account_id}/upload-folder")
def upload_folder(
    account_id: str,
    files: Annotated[list[UploadFile], File()],
    disk_path: Annotated[str, Form()],
    overwrite: Annotated[bool, Form()] = False,
    publish_after_upload: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="Choose a folder with files.")
    if len(files) > MAX_UPLOAD_FOLDER_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"В папке слишком много файлов. Максимум {MAX_UPLOAD_FOLDER_FILES}.",
        )

    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    created_folders: set[str] = set()
    root_path = normalize_disk_path(disk_path)
    total_size = 0

    with accounts.get_client(account_id) as client:
        try:
            client.ensure_folder(root_path)
            created_folders.add(root_path)
        except YandexDiskAPIError:
            if root_path != "disk:/":
                raise

        for upload in files:
            relative_name = upload.filename or ""
            if not relative_name:
                skipped.append({"file": "", "reason": "Файл без имени пропущен."})
                continue
            if _should_skip_folder_upload_path(relative_name):
                skipped.append({"file": relative_name, "reason": "Служебный файл или папка пропущены."})
                continue

            target_path = _join_disk_path(root_path, relative_name)
            temp_name: str | None = None
            upload_id: int | None = None
            try:
                for folder_path in _parent_disk_paths(target_path):
                    if folder_path not in created_folders:
                        client.ensure_folder(folder_path)
                        created_folders.add(folder_path)

                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    temp_name = tmp.name
                    size = _copy_upload_to_temp(upload.file, tmp, max_bytes=MAX_UPLOAD_FILE_BYTES)
                total_size += size
                if total_size > MAX_UPLOAD_FOLDER_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Папка слишком большая. Максимум {_format_bytes(MAX_UPLOAD_FOLDER_BYTES)} за одну загрузку.",
                    )
                upload_id = history.start(
                    account_id=account_id,
                    local_filename=Path(relative_name).name,
                    local_size=size,
                    disk_path=target_path,
                    overwrite=overwrite,
                    published=False,
                )
                metadata_result = client.upload_file(temp_name, target_path, overwrite=overwrite)
                completed.append({"metadata": _safe_metadata(metadata_result), "history": history.complete(upload_id, public_url=None)})
            except Exception as exc:
                safe_message = "Не удалось загрузить файл."
                if isinstance(exc, HTTPException) and isinstance(exc.detail, str):
                    safe_message = exc.detail
                elif isinstance(exc, YandexDiskAPIError):
                    status_code = exc.status_code if exc.status_code and 400 <= exc.status_code < 600 else 502
                    safe_message = _safe_yandex_error_message(status_code)
                elif isinstance(exc, TokenUnavailable):
                    safe_message = "Токен аккаунта недоступен. Добавьте аккаунт заново."
                elif isinstance(exc, AccountError):
                    safe_message = "Не удалось обработать аккаунт."
                failed.append({"file": relative_name, "disk_path": target_path, "error": safe_message})
                if upload_id is not None:
                    history.fail(upload_id, error_message=safe_message)
            finally:
                if temp_name:
                    try:
                        os.remove(temp_name)
                    except OSError:
                        pass

    public_url: str | None = None
    published_metadata: dict[str, Any] | None = None
    if publish_after_upload and not failed:
        with accounts.get_client(account_id) as client:
            published_metadata = client.publish(root_path)
            public_url_value = published_metadata.get("public_url")
            public_url = public_url_value if isinstance(public_url_value, str) else None

    return {
        "root_path": root_path,
        "uploaded_count": len(completed),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "public_url": public_url,
        "published_metadata": _safe_metadata(published_metadata),
        "uploaded": completed,
        "failed": failed,
        "skipped": skipped,
    }


@app.get("/api/uploads")
def upload_history(limit: Annotated[int, Query(ge=1, le=100)] = 25) -> list[dict[str, Any]]:
    return history.recent(limit=limit)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False, access_log=False)
