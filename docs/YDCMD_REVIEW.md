# ydcmd Review

Reference implementation: <https://github.com/abbat/ydcmd>

`ydcmd` was reviewed only as a reference for Yandex.Disk REST API behavior. This project does not call `ydcmd.py`, does not vendor it, and does not copy its CLI architecture.

## Ideas reused

- Use the official REST base URL `https://cloud-api.yandex.net/v1/disk`.
- Treat paths in the Yandex format such as `disk:/path/to/file`.
- Implement upload as the official two-step flow: get an upload link from `/resources/upload`, then upload the local file to the returned `href`.
- Use `/resources` for folder creation, metadata, listing, and deletion.
- Use `/resources/publish` and `/resources/unpublish` for public link management.
- Surface API descriptions to the user, but keep them sanitized.

## Parts not used

- CLI command parsing and command-dispatch layout.
- External execution of `ydcmd.py`.
- INI-style token/config file storage.
- Recursive sync, multiprocessing workers, progressbar integration, and shell-oriented output formatting.
- Download-to-local and remote URL download commands in the MVP UI.
- Debug logging of request details that could accidentally expose sensitive data.

## Security differences

- OAuth tokens are stored in OS keyring or only in process memory.
- OAuth tokens are not stored in SQLite.
- `Authorization` headers and token-like values are redacted from logs and API errors.
- The app binds to `127.0.0.1` and rejects non-local requests and non-local `Host` headers.
- Mutating local API calls require a custom local header to reduce cross-site request risks.
- The upload `href` is validated as HTTPS and Yandex-owned before use.
- The OAuth token is sent only to `cloud-api.yandex.net`, not to the one-time upload `href`.
- No telemetry, crash reporting, auto-update, or external backend is included.

## Endpoints used

- `GET https://cloud-api.yandex.net/v1/disk/` for token checks and disk info.
- `GET https://cloud-api.yandex.net/v1/disk/resources` for metadata and folder listing.
- `PUT https://cloud-api.yandex.net/v1/disk/resources` for folder creation.
- `DELETE https://cloud-api.yandex.net/v1/disk/resources` for resource deletion.
- `GET https://cloud-api.yandex.net/v1/disk/resources/upload` for a one-time upload link.
- `PUT <upload href returned by the official API>` for file upload.
- `PUT https://cloud-api.yandex.net/v1/disk/resources/publish` for public links.
- `PUT https://cloud-api.yandex.net/v1/disk/resources/unpublish` to remove public access.
- `https://oauth.yandex.ru` is the allowed OAuth origin for manually obtaining tokens; this MVP accepts a pasted token rather than running a full OAuth redirect flow.

