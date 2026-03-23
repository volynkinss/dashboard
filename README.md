# Secure Service Catalog (SSR, Keycloak, FastAPI)

A production-oriented internal shortcuts portal where users see only services they are allowed to access.

## Security Principles
- Authentication via Keycloak OIDC Authorization Code flow in `keycloak` mode.
- Authorization evaluated only on the server.
- Frontend receives only server-rendered allowed items.
- No endpoint exposing full catalog or ACL metadata.
- Unauthenticated users are immediately redirected to Keycloak.
- Session is server-side (`user_sessions` table + opaque cookie).

## Architecture
- Backend: FastAPI
- Rendering: Jinja2 SSR templates
- Database: PostgreSQL
- ORM: SQLAlchemy 2.x
- Migrations: Alembic
- AuthN/AuthZ: Keycloak OIDC + server-side access control service
- Containerization: Docker Compose

## Project Layout
- `app/main.py` application bootstrap and security headers
- `app/routers/auth.py` login/callback/logout routes
- `app/routers/catalog.py` SSR catalog route
- `app/security/oidc.py` OIDC client, token validation, claim parsing
- `app/security/session_store.py` server-side session management
- `app/services/access_control.py` deny-by-default access filtering
- `app/services/audit.py` audit event recording
- `app/services/activity_log.py` rotating JSONL activity log writer
- `app/models/*` SQLAlchemy models
- `app/templates/*` SSR templates
- `alembic/*` migrations
- `scripts/seed_demo.py` idempotent demo data seed
- `scripts/seed_from_dashy.py` Dashy YAML to DB import
- `scripts/import_access_groups.py` controlled import of groups/roles
- `data/dashy.yaml` active Dashy source for import at container startup

## Database Schema
Core tables:
- `categories`
- `services`
- `access_groups`
- `service_access`

Additional tables:
- `category_access`
- `user_sessions`
- `audit_events`

Access model:
- `access_groups.source = client_role | group`
- `access_groups.name = exact claim value`
- `service_access` / `category_access` map principals to resources
- `allow_all_authenticated` allows all authenticated users only
- Dashy import rule: item with no `showForKeycloakUsers.groups` is imported as `allow_all_authenticated=true`

## Local Run (Docker Compose)
1. Copy config:
   ```bash
   cp .env.example .env
   cp docker-compose.example.yml docker-compose.yml
   ```
   `docker-compose.yml` is local and ignored by Git, so you can change it freely.
   `app` service reads runtime settings from `.env` via Compose `env_file`.
2. Put your real Dashy YAML to:
   - `data/dashy.yaml`
3. Fill Keycloak values in `.env`.
   - If Keycloak runs on your host machine and app runs in Docker, use `KEYCLOAK_ISSUER_URL=http://host.docker.internal:<port>/realms/<realm>` instead of `localhost`.
   - Set `ADMIN_EMAIL` to the Keycloak email of the user who should see the **Reload config** button in the top bar.
4. Start:
   ```bash
   docker compose up --build
   ```
5. Open [http://localhost:8000](http://localhost:8000).
6. If you see `Invalid host header`, add your host to `TRUSTED_HOSTS` or set `TRUSTED_HOSTS=*` for local development only.
7. Compose startup imports `/app/data/dashy.yaml` automatically and runs with `--deactivate-missing`, so old entries not present in YAML are deactivated.

## Dashy Import
Import custom Dashy config into database:
```bash
python -m scripts.seed_from_dashy --config ./data/dashy.yaml
```

If you want to deactivate entities not present in the file:
```bash
python -m scripts.seed_from_dashy --config ./data/dashy.yaml --deactivate-missing
```

You can also reload `dashy.yaml` from UI without container restart:
- Put admin email into `ADMIN_EMAIL` in `.env`.
- Login with this email.
- Click **Reload config** button (left from RU/EN switch). The app re-imports `DASHY_CONFIG_PATH` with `--deactivate-missing` behavior.

Multilingual labels are supported for section names, service titles, and descriptions.
You can keep string values (single language) or use `{ru, en}` objects:

```yaml
sections:
  - name:
      ru: Терминальный доступ
      en: Terminal Access
    items:
      - title:
          ru: Админ-сервер
          en: Admin Server
        description:
          ru: Подключение к административному серверу
          en: Connect to the admin server
        url: https://example.internal
```

If one language is missing, the app falls back to available text.

Dashy icons are imported too:
- `fa ...` values (for example `fa fa-windows fa-2x`) are rendered as Font Awesome icons.
- URL / path icons (for example `https://.../icon.svg` or `/assets/icon.png`) are rendered as images.
- `favicon` or `favicon:<url>` is resolved via domain favicon lookup.

## Keycloak Claim Mapping (Safe Baseline)
Use client-scoped roles as primary and groups as secondary.

1. Create confidential client `catalog`.
2. Enable Standard Flow.
3. Set redirect URI: `http://localhost:8000/auth/callback`.
4. Set post logout redirect URI: `http://localhost:8000/`.
5. Create client roles under `catalog` (for example `catalog-user`, `catalog-admin`).
6. Assign users/groups to these client roles.
7. Enable groups claim mapper with full group path.
8. Ensure tokens include:
   - `resource_access.catalog.roles` (primary)
   - `groups` with full paths (secondary)
9. Keep `realm_access.roles` out of authorization logic for this app.

## How to Add a New Restricted Service
Example: allow `confluence` only for `/AD/IT/PortalUsers`.

1. Ensure principal exists:
   ```sql
   INSERT INTO access_groups (source, name, is_active, created_at, updated_at)
   VALUES ('group', '/AD/IT/PortalUsers', true, now(), now())
   ON CONFLICT (source, name) DO UPDATE SET is_active = EXCLUDED.is_active, updated_at = now();
   ```
2. Create or reuse category (`engineering` in example).
3. Create service:
   ```sql
   INSERT INTO services (category_id, slug, name, description, url, icon_emoji, sort_order, is_active, allow_all_authenticated, created_at, updated_at)
   VALUES (
     (SELECT id FROM categories WHERE slug = 'engineering'),
     'confluence',
     'Confluence',
     'Knowledge base',
     'https://confluence.example.internal',
     'C',
     30,
     true,
     false,
     now(),
     now()
   );
   ```
4. Bind access:
   ```sql
   INSERT INTO service_access (service_id, access_group_id, created_at, updated_at)
   VALUES (
     (SELECT id FROM services WHERE slug = 'confluence'),
     (SELECT id FROM access_groups WHERE source = 'group' AND name = '/AD/IT/PortalUsers'),
     now(),
     now()
   )
   ON CONFLICT (service_id, access_group_id) DO NOTHING;
   ```

## Controlled Import of Access Groups
- CSV mode (`source,name` columns):
  ```bash
  python -m scripts.import_access_groups --file ./groups.csv
  ```
- Text mode (one value per line):
  ```bash
  python -m scripts.import_access_groups --file ./ad_groups.txt --source group
  python -m scripts.import_access_groups --file ./client_roles.txt --source client_role
  ```

This is controlled import only. Runtime token claims never auto-create ACL entries.

## Internal-Only Sections by IP
You can hide selected catalog sections for users outside internal networks.

Environment variables:
- `INTERNAL_NETWORKS` - comma-separated CIDRs treated as internal sources.
- `TRUSTED_PROXY_NETWORKS` - proxies allowed to provide `X-Forwarded-For` / `X-Real-IP`.
- `INTERNAL_ONLY_CATEGORY_NAMES` - section names hidden for external clients.
- `INTERNAL_ONLY_CATEGORY_SLUGS` - optional slug list hidden for external clients.

Defaults include RFC1918 ranges and hide `Корпоративные Web-приложения` (and its English variant) for external IPs.
If your app is behind reverse proxy/load balancer, add that proxy subnet to `TRUSTED_PROXY_NETWORKS`.

## Database Growth Control
To keep PostgreSQL size stable under high daily usage, the app applies bounded retention and throttling:

- Expired sessions are removed periodically.
- Audit events older than retention window are removed periodically.
- Repeated `catalog_view` events are throttled per user.

Environment variables:
- `AUDIT_RETENTION_DAYS` - how long to keep audit events (default `30`).
- `AUDIT_CATALOG_VIEW_MIN_INTERVAL_SECONDS` - minimum interval between `catalog_view` events for the same user (default `300`).
- `DB_MAINTENANCE_ENABLED` - enable periodic maintenance (default `true`).
- `DB_MAINTENANCE_INTERVAL_SECONDS` - maintenance run interval (default `300`).
- `SESSION_EXPIRED_GRACE_SECONDS` - additional grace period before deleting expired sessions (default `0`).
- `SESSION_LAST_SEEN_UPDATE_INTERVAL_SECONDS` - minimum interval between `last_seen_at` updates for one session (default `120`).

Recommended baseline for ~1000 users/day:
- Keep `AUDIT_RETENTION_DAYS=30` (or `14` if strict minimization is preferred).
- Keep `AUDIT_CATALOG_VIEW_MIN_INTERVAL_SECONDS` in `120-300` range.
- Keep `DB_MAINTENANCE_INTERVAL_SECONDS` in `300-900` range.

## File Activity Log (User Actions)
The app can write structured user-action events to a rotating log file:
- Server-side audit events are mirrored to JSONL log entries.
- Clicks on catalog service shortcuts are logged as `service_click` with service/category slugs.
- File logging is best-effort and does not block user flow on write failures.

Environment variables:
- `ACTIVITY_LOG_ENABLED` - enable file logging (default `true`).
- `ACTIVITY_LOG_FILE_PATH` - target log file path (default `/tmp/catalog_activity.log`).
- `ACTIVITY_LOG_MAX_BYTES` - rotate when file exceeds this size (default `20971520`, 20 MB).
- `ACTIVITY_LOG_BACKUP_COUNT` - number of rotated files to keep (default `10`).

For Docker Compose persistence, mount a writable logs directory (example in `docker-compose.example.yml`):
- `./logs:/app/logs`
- `ACTIVITY_LOG_FILE_PATH=/app/logs/catalog_activity.log`
- Ensure `./logs` is writable for container user (`appuser`), otherwise file logging will be skipped.

## Production Hardening Checklist
- Set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Rotate `SECRET_KEY` and `KEYCLOAK_CLIENT_SECRET` using secret manager.
- Keep `KEYCLOAK_ALLOWED_SIGNING_ALGS` restricted to approved algorithms (for example `RS256`).
- Restrict `TRUSTED_HOSTS` to real hostnames.
- Add database backups and retention policy.
- Keep periodic cleanup for expired `user_sessions` and old `audit_events` enabled.
- Apply network policies between app and database.
- Run app behind reverse proxy with TLS and request size limits.
