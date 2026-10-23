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
same checks. Initial private-repository attempts were blocked by account billing. After the
founder made the repository public and service health-command quoting was fixed, both jobs
passed in run 39928699090 on commit a1c22f5: 17 backend tests and 6 production-browser tests.
The hosted Ubuntu runner supplies browser runtime libraries; CI installs Chromium without
redundant apt upgrades. Browser install and test steps have separate timeouts and failure
artifacts include the API log. Local Linux machines may still need --with-deps.
Never infer success on a new commit without checking its actual workflow result.

Additional coverage and known acceptance limits are tracked in DEVELOPMENT_STATUS.md.
Avoid using test fixture accounts/databases for real business data.

Administrator race regressions synchronize two requests after authentication, then exercise
mutual demotion, mutual removal and mixed demotion/removal. Each must yield one successful
mutation and one 403, with exactly one administrator remaining in PostgreSQL.

Browser session regressions additionally check incorrect-current-password behavior (same
HttpOnly cookie and continued /auth/me access), and a tab retaining an actually revoked token
(return to login, Persian explanation, no workspace navigation and no session cookie), on both
desktop and mobile. This brings the browser suite to 10 tests. Backend password tests verify
400 preserves the current session and successful change still revokes every session.

Catalog concurrency tests pause a product after domain validation, execute a category-rule
change in another transaction, observe the real PostgreSQL lock wait, then release creation.
The update must return 409 and the persisted product's dimension unit must match its category.

The catalog/pricing browser workflow now enters Persian/Arabic digits with six price decimals,
checks the exact stored decimal string through the real API, leaves an optional dimension blank,
and edits it later. It verifies required/optional flags and fixed category units. An additional
delayed-response scenario deliberately holds the product list while loading parties, then
releases it: the party table must remain intact on desktop and mobile. Browser suite: 12 tests.
