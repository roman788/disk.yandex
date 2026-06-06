# Local Yandex.Disk Uploader

Локальное open-source приложение для загрузки файлов на Яндекс.Диск через официальный REST API.

## Возможности MVP

- добавление аккаунта по OAuth-токену;
- проверка токена и получение информации о диске;
- создание папок;
- загрузка одного файла или папки с `overwrite=true/false`;
- опциональная публикация файла;
- история загрузок в SQLite без хранения токена;
- хранение токена в системном keyring или только в памяти процесса.

## Запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
```

Откройте `http://127.0.0.1:8765`.

Подробности сборки: [BUILD_FROM_SOURCE.md](BUILD_FROM_SOURCE.md). Модель безопасности: [SECURITY.md](SECURITY.md).
