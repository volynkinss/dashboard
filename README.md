# Dashboard (FastAPI + Keycloak)

Краткая инструкция: что указать в `.env`, как запустить проект и куда положить `dashy.yaml`.

## 1) Настройка `.env`

Создайте файл:

```bash
cp .env.example .env
```

Заполните/проверьте в `.env`:

- `SECRET_KEY` — длинный случайный секрет.
- `KEYCLOAK_ISSUER_URL` — URL realm в Keycloak (пример: `https://keycloak.example.internal/realms/company`).
- `KEYCLOAK_CLIENT_ID` — ID клиента в Keycloak.
- `KEYCLOAK_CLIENT_SECRET` — client secret этого клиента.
- `KEYCLOAK_REDIRECT_URI` — callback приложения (обычно `http://localhost:8000/auth/callback`).
- `KEYCLOAK_POST_LOGOUT_REDIRECT_URI` — редирект после logout (обычно `http://localhost:8000/`).
- `KEYCLOAK_ROLES_CLIENT_ID` — клиент, из которого читаются роли (обычно тот же, что `KEYCLOAK_CLIENT_ID`).
- `ADMIN_EMAIL` — email администратора (показывает кнопку `Reload config` в UI).
- `DASHY_CONFIG_PATH` — путь к YAML внутри контейнера (обычно `/app/data/dashy.yaml`).

По БД обычно достаточно значений по умолчанию:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

`DATABASE_URL` в `.env` можно не заполнять при запуске через Docker Compose, он задается в `docker-compose.yml`.

## 2) Куда положить `dashy.yaml`

Положите файл в:

- `data/dashy.yaml`

## 3) Запуск проекта

1. Создайте локальный compose-файл:

```bash
cp docker-compose.example.yml docker-compose.yml
```

2. Запустите проект:

```bash
docker compose up --build
```

3. Откройте приложение:

- [http://localhost:8000](http://localhost:8000)

При старте контейнера приложение автоматически применяет миграции и импортирует `dashy.yaml`.

## 4) Остановка

```bash
docker compose down
```
