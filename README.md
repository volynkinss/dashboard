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
   ```
2. Put your real Dashy YAML to:
   - `data/dashy.yaml`
3. Fill Keycloak values in `.env`.
   - If Keycloak runs on your host machine and app runs in Docker, use `KEYCLOAK_ISSUER_URL=http://host.docker.internal:<port>/realms/<realm>` instead of `localhost`.
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

## Production Hardening Checklist
- Set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Rotate `SECRET_KEY` and `KEYCLOAK_CLIENT_SECRET` using secret manager.
- Restrict `TRUSTED_HOSTS` to real hostnames.
- Add database backups and retention policy.
- Add periodic cleanup for expired `user_sessions` and old `audit_events`.
- Apply network policies between app and database.
- Run app behind reverse proxy with TLS and request size limits.
