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

Permission concurrency tests hold an actual membership row lock while an authenticated domain
request queues, then commit a demotion or membership removal. Create, replay, update, delete,
admin catalog definition and removed-member requests must be rejected without changing data.
Catalog rule concurrency uses different actors so membership serialization cannot mask the
category-row invariant. Current backend suite: 24 tests.

## Approved warehouse operations extension

See [INVENTORY.md](INVENTORY.md) for the implemented M2 API, immutable ledger,
role/warehouse policy, concurrency rules, migration `0002_inventory` and test coverage.
M1 historical boundaries describe the foundation before this approved extension.

## Internal sales monetary policy — current suite

58 backend integration tests and22 desktop/mobile Playwright tests pass locally. Added
cases cover scoped/admin/versioned tax defaults, concurrent stale updates, rate validation
(no floats/booleans,0–100,6 decimals), default changes preserving draft/history, legacy null
policy handling, inclusive-price rejection and half-up ties. Monetary line/tax/document
amounts are cross-checked between Decimal details and SQL page aggregates, including
maximum inputs and two0.045 lines at10% producing grand0.12. Migration testing upgrades a
populated0003 draft/revision without inventing historical tax, then downgrades/upgrades
and checks model drift. Browser flows set Persian tax rates, preserve revisions, update
organization defaults and retain zero stock effects. Earlier counts above are historical.

## Version-bound internal reviews

Current local suite:63 backend tests and22 desktop/mobile browser tests. Review regressions
cover admin-only scope, editor/viewer denial, cross-tenant404, replay, one decision per version,
new edits invalidating current usability, immutable evidence/update-delete guards, expired
price rejection, expiry during snapshot (no orphan audit/idempotency), concurrent reviewers
(one201/one409), and zero stock effects. The browser sales workflow accepts version1,
edits version2, records a rejection after source revocation, and preserves revision history.

## Local-model read-only sales assistant

Current backend suite:77 passed, one opt-in local-model integration test skipped by default.
The opt-in actual-model API test also passed separately, with exact PostgreSQL price evidence;
7 synthetic Persian extraction cases matched. CI does not download weights or require paid
services: the browser provider fixture is a loopback-only _test-guarded HTTP server, clearly
separate from actual-model evaluation. New tests cover tenant isolation, bounded fixed tools,
no business writes, pending/expired/source-revoked prices, live session revocation during
inference, URL/model allowlists, malformed/oversized/redirected provider output, per-worker
concurrency and total deadline, and absence of question/search text in application logs.
See SALES_ASSISTANT.md for opt-in commands and limits of the small actual-model evaluation.

The sales assistant UI adds two real-API browser scenarios (desktop/mobile): exact price
evidence/source rendering, unsupported intent and unchanged draft count. Current browser
suite:24 passing. Raw synthetic local-model evidence is in evidence/local-assistant-2026-10-24.json.

## Exact catalog dimensions and grounded model extraction

Current suite:99 backend tests pass, with2 opt-in actual-model tests skipped by default.
Both actual-model tests passed in a separate35-test assistant run. The expanded local
synthetic evaluation matched12/12 cases; the initial10/12 artifact remains alongside the
final evidence to document the spelling failure and the copied-term guard that addressed it.
This small evaluation is not a production accuracy benchmark.

New regressions cover exact mm/cm/m equivalence, AND filters, extensible attributes,
tenant scope and pagination, invalid/duplicate/deep JSON, malformed grouping, float/bool
rejection, ambiguous dimensions skipping inference/search, no broadening on zero matches,
and model terms absent from the question being rejected. Existing desktop/mobile assistant
flows now assert exact dimensional filtering, source attributes and clarification with no
business writes. No migration is needed; alembic check reports no model drift.

Persian number-word regressions cover یک/دو/ده/نیم, integer-plus-half and ZWNJ
separators, exact Decimal extraction before inference, real domain API equivalence with
numeric2mm, and unsupported compound forms requiring clarification. No new model claim
or financial calculation is introduced by this parser extension.

Final number-word extension suite:108 passed,2 opt-in model tests skipped by default;
24 production-build browser tests pass in PR CI40111717238. Both CI jobs, migration/model
drift, formatting, build/typecheck and dependency checks passed. Earlier counts are historical.

## Inclusive catalog ranges

Range regressions cover both inclusive endpoints, equal bounds, interior nonmatches,
mm/cm/m equivalence, mixing exact/range attributes, pagination and tenant scope. Reversed,
missing or incompatible bounds are rejected. Legacy JSON strings, exponents, arrays,
oversized numbers, JSON numeric values and nulls are exercised against guarded SQL casts.
Assistant tests cover از…تا / بین…و, mixed bound units, invalid/missing/reversed ranges,
API result preservation and no relaxed criteria. Browser scenarios display two matching
boundary products and explicitly label inclusive limits. Synthetic actual-local-model
evaluation matched14/14 cases; evidence/local-assistant-ranges-2026-10-24.json retains outputs.
The prior number-word case now expects supported extraction; historical artifacts are unchanged.
