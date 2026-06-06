# Security Policy

## Local-only model

This app is designed to run only on `127.0.0.1`. It has no external backend, no telemetry, no crash reporting, and no auto-update mechanism.

The FastAPI app rejects non-local clients and non-local `Host` headers. Mutating API calls require the `X-Local-Yandex-Disk: 1` header so ordinary cross-site form posts cannot trigger uploads or account changes.

## External network access

Fixed outbound origins:

- `https://cloud-api.yandex.net`
- `https://oauth.yandex.ru`

Yandex.Disk uploads use the official two-step REST flow: first the app requests an upload URL from `https://cloud-api.yandex.net/v1/disk/resources/upload`, then it performs a `PUT` to that one-time HTTPS URL. The upload URL is accepted only when it is returned by the official API and points to a Yandex-owned HTTPS host. The OAuth token is not sent to that upload URL.

## Token handling

- OAuth tokens are never stored in SQLite.
- Persistent token storage uses the operating system keyring through the `keyring` package.
- The app also supports a "memory only" mode; the token is lost when the process exits.
- Tokens must not be placed in URLs.
- The app does not log tokens or `Authorization` headers.
- API errors shown to users are sanitized before they are returned by the backend.

## SQLite data

SQLite stores account metadata and upload history only:

- account label, login/display name when available;
- token storage mode (`keyring` or `memory`);
- uploaded file name, size, target disk path, status, and optional public URL.

SQLite must not contain OAuth tokens.

## Reporting issues

Please report security issues privately to the project maintainer before publishing details. Include the affected version, reproduction steps, and whether a token or local file path could be exposed.

