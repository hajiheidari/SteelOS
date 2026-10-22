# Testing

Full commands are in README.md. Python 3.12, PostgreSQL 17, Node 22+, Chromium.
Only disposable database names ending `_test` are accepted by destructive fixtures.
Migrations must run first. Migration test creates a separate scratch database and exercises
upgrade → downgrade → upgrade and `alembic check` for model drift. Requires CREATEDB.
SQLite is intentionally not used as a substitute for PostgreSQL constraints/locking/JSON.

Automated backend coverage: liveness/readiness/OpenAPI/error envelopes; auth organization
verification, refresh/logout, brute force throttle, value redaction; roles/member changes,
password revocation; tenant CRUD isolation and direct composite FK rejection; category rules,
SKU/spec duplicate prevention, product editing/search; CRM dual roles, deduplication,
idempotency replay and audit atomicity; warehouse access/hierarchy/cycle prevention; price
decisions, expired/unapproved exclusion, immutable history, precision and mock adapter.

Playwright checks real API login, HttpOnly cookie and empty localStorage, Persian RTL,
CRM create/update/delete, both party roles, logout, desktop/mobile overflow and proxy origin
rejection. Failure traces and screenshots remain local or CI artifacts, not source control.
Production frontend build, TypeScript, Ruff and pip/npm vulnerability audits are required.

GitHub workflow has backend and frontend jobs with disposable PostgreSQL services and the
same checks. GitHub account billing currently prevents jobs from starting; this external
blocker is distinct from local passing checks. Never report CI green until actual jobs run.

Additional coverage and known acceptance limits are tracked in DEVELOPMENT_STATUS.md.
Avoid using test fixture accounts/databases for real business data.
