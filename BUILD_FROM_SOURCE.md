# Build From Source

## Requirements

- Python 3.12 or newer
- A local browser
- Access to Yandex.Disk REST API from the machine running the app

## Install

```powershell
git clone <repo-url>
cd disk.yandex
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

All runtime dependencies are pinned in `requirements.txt` and mirrored in `requirements.lock.txt`. Direct dependencies are also listed in `requirements.direct.txt` and `pyproject.toml`.

## Run

```powershell
python -m app.main
```

The server binds to `127.0.0.1:8765` by default. You can change the port with:

```powershell
$env:YDISK_LOCAL_PORT = "8780"
python -m app.main
```

Open `http://127.0.0.1:8765`.

## Runtime data

By default the SQLite database is created at `data/app.sqlite3`. Tokens are not stored there.

Optional environment variables:

- `YDISK_LOCAL_DATA_DIR`: directory for local app data
- `YDISK_LOCAL_DB`: explicit SQLite path
- `YDISK_LOCAL_PORT`: local server port
- `YDISK_HTTP_TIMEOUT`: outbound API timeout in seconds

## No binary distribution required

The app runs from source. It does not install services, browser extensions, telemetry, crash reporters, or auto-updaters.
