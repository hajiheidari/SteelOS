# SteelOS

Persian RTL steel trading foundation. Modular FastAPI/SQLAlchemy backend, PostgreSQL 17,
Next.js/TypeScript workspace. M1 features and automated GitHub Actions checks pass; the milestone is ready
for founder acceptance review. The subsequently approved warehouse operations extension
adds ownership-aware lots, immutable stock movements and reservations; see
[Inventory contracts](docs/INVENTORY.md). No production deployment is included. See [development status](docs/DEVELOPMENT_STATUS.md).

## Clean local setup

Requirements: Docker with Compose v2, Python 3.12, Node.js 22+, npm. No paid service needed.
All commands below run from the repository root unless shown otherwise.

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD and the matching DATABASE_URL password in .env.
# Use a URL-safe local password; never commit .env.
docker compose up --build -d
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
# Explicit operator-only setup. Password is prompted, never passed in argv.
docker compose exec api python -m app.bootstrap --organization 'شرکت نمونه' --email admin@example.test
# Save the printed organization UUID for login.
cd apps/web
npm ci
npm run dev
```

Open **http://127.0.0.1:3000**. Login with the operator-created email, password and
organization UUID. No default application account or public registration exists.
Create catalog references (category with dimension rules, manufacturer, grade,
standard), then products, parties, warehouses/locations and pricing sources.
A source must be explicitly authorized by an admin before its observations can be approved.
Frontend API requests use a server proxy and an HttpOnly session cookie.

Backend OpenAPI: http://127.0.0.1:8000/docs. Ports bind only to loopback.
`docker compose down` stops services; named volume retains data. Do not use `down -v`
for data you need. No public deployment is included or authorized.

## Backend development without an API container

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt
set -a
. ./.env
set +a
docker compose up -d db
cd apps/api
../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`DATABASE_URL` must be exported when running from `apps/api`; the root `.env` is
read by Compose but not automatically by commands in another directory.
The API container runs migrations on startup for local development. Future production
rollouts must run migrations as a separate reviewed release step with backups.

## Checks

Use a disposable database ending in `_test`. Tests deliberately refuse other database
names and truncate test data. Migration tests need CREATEDB permission and create/drop
only their separate scratch database.

```sh
docker compose exec db createdb -U steelos steelos_test
# Replace the password below with your local password, URL-encoded if needed.
export DATABASE_URL='postgresql+psycopg://steelos:YOUR_LOCAL_PASSWORD@localhost:5432/steelos_test'
(cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic check)
.venv/bin/ruff check apps/api
.venv/bin/ruff format --check apps/api
.venv/bin/pytest -q
.venv/bin/pip-audit -r apps/api/requirements.txt --progress-spinner off
(cd apps/web && npm ci && npm run typecheck && npm run build && npm audit --audit-level=moderate)
```

Browser tests require the API running against that test database, with port 8000 free:

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/seed_e2e.py
PYTHONPATH=apps/api .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# In another terminal:
cd apps/web
npx playwright install --with-deps chromium
npm test
```

The fixture account in `seed_e2e.py` is restricted to disposable `_test` databases.
Playwright starts the frontend and checks desktop/mobile with real backend requests.
Do not run destructive backend tests concurrently with browser tests on the same database.

## Configuration

- `DATABASE_URL`: PostgreSQL psycopg URL; never print real credentials in logs.
- `SESSION_HOURS`: 1–24, default 8; refresh rotates and revokes the old token.
- `ALLOWED_ORIGINS`: JSON array of backend CORS origins for direct API clients.
- `API_BASE_URL`: frontend server-only backend base URL, default `http://127.0.0.1:8000`.
- `APP_ORIGIN`: exact browser origin for CSRF checks, default `http://127.0.0.1:3000`.
  Set explicitly if changing hostname or port. Never derive it from untrusted forwarded headers.
- `NEXT_TELEMETRY_DISABLED=1`: optional Next.js telemetry opt out.

Production builds use Secure cookies and require HTTPS. PWA metadata is present;
offline data caching/service worker is deliberately absent for sensitive business data.
For cloud build proxies, the backend Dockerfile accepts an optional BuildKit secret
`proxy_ca` containing the trusted CA bundle (`docker build --secret id=proxy_ca,src=...`).

Read [AGENTS.md](AGENTS.md), [API](docs/API_SPEC.md), [security](docs/SECURITY.md),
[data model](docs/DATA_MODEL.md), and [testing](docs/TESTING.md) before extending modules.
