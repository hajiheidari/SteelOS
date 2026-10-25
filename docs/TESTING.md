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

Range implementation CI40117117885 passed113 backend and24 browser tests. Subsequent
comparison-safety regressions cover missing-unit operators, negated equality/ranges,
approximation and comparison symbols; API tests prove the planner is never called and
no products are returned for these unsupported intents.

Final comparison-guard CI40117392872 passed124 backend tests (2 actual-model tests opt-in
skipped),24 desktop/mobile browser tests, migrations/model drift, formatting, build/typecheck
and dependency checks. Local full backend execution also passed124 tests. Prior counts above
are historical; the14-case actual local-model extraction evidence belongs to this range batch.

## Opt-in catalog query measurement

See CATALOG_SEARCH_PERFORMANCE.md for the isolated `_benchmark` database command, recorded
10000-product query plans and baseline/selected/discarded measurements. The harness asserts
scope/count/page correctness and rollback, with no flaky timing gate or ordinary CI seed.
Range regression coverage additionally checks dimensionless units, incompatible kg vs length,
missing attributes, tiny metre thresholds and maximum-scale bounds after unit-branch selection.

## Finite Persian word ranges

Regressions cover finite word bounds, integer-plus-half, ZWNJ, mixed digits/words and units,
reversed/invalid fractions, missing units, unknown word bounds, unsupported kg and negation.
The domain API test compares numeric and word ranges against the same products with an exact
width filter. Actual-model API coverage additionally verifies a word range returns the exact
approved PostgreSQL price ID/amount. Synthetic evaluation16/16 is recorded separately from
CI's disposable provider fixture. Browser range scenarios now enter Persian word bounds.

Local word-range batch:139 backend tests pass with2 opt-in model tests skipped by default;
all75 assistant tests pass when opting into the installed actual local model. The24
production-build browser tests pass on desktop/mobile. Synthetic extraction evaluation16/16
is recorded in evidence/local-assistant-word-ranges-2026-10-24.json; it is a small regression
set rather than a broad Persian language benchmark. Previous counts above are historical.

Word-range implementation2425273 passed both PR CI jobs40123749493:139 backend tests,
2 opt-in actual-model skips,24 production-build browser tests, migration/model drift,
Ruff/format, TypeScript/build and dependency audits. Actual-model tests ran separately75/75.

## Explicit dimension comparisons

Regressions compare gt/gte/lt/lte against boundary products across mm/cm units and tenants,
with malformed operator/bound rejection. Parser/API cases include symbols, Persian phrases,
number words, invalid/missing units, duplicate-key constraints, negation, approximation and
یا/or rejection. Browser coverage checks strict >2mm excludes2mm and displays only3mm with
its operator and no fabricated price. Actual-model integration additionally verifies lte2mm
returns the exact stored approved price and gt2mm returns no match without relaxing the filter.

Local comparison batch:158 backend tests pass (2 actual-model tests skipped by default),
94 assistant tests pass with the installed actual model, and24 production-build browser tests
pass. Synthetic actual-model extraction18/18 is recorded separately in
 evidence/local-assistant-comparisons-2026-10-24.json. Regression coverage excludes invalid
nonpositive legacy dimensions from upper-bound comparisons and retains safe JSON casts.

Comparison implementation4d0f9cf passed both PR CI jobs40129040543:158 backend tests,
2 opt-in skips,24 desktop/mobile browser tests, migration/model drift, Ruff/format,
TypeScript/build and dependency audits.94 actual-local-model assistant tests and18 synthetic
extraction cases were run separately; no weights are downloaded or model service required in CI.

## Inclusive/exclusive two-bound intervals

Database regressions exercise all four endpoint modes against2/2.5/3mm products stored in
mm/cm/m categories, foreign-organization duplicates and paginated counts/results. Validation
rejects nonboolean flags, reversed/incompatible bounds and equal physical bounds with an
excluded endpoint. Parser/API regressions cover explicit conjunction, reversed clause order,
word bounds, unchanged inclusive response shapes, contradictory/repeated/nonadjacent/OR
conditions and no unconstrained fallback. Browser coverage checks2<x≤3 returns only3mm.

Local exclusive-bound batch:178 backend tests passed,2 actual-model tests skipped by default;
113 assistant tests passed with the installed actual local model, and24 production-build
browser tests passed. Expanded synthetic actual-model evaluation21/21 is recorded in
 evidence/local-assistant-exclusive-ranges-2026-10-25.json (Tehran date). This small regression
set is not a general language accuracy/production-readiness benchmark. Earlier counts are historical.

Exclusive-bound implementation9f9a61b passed both PR CI jobs40133189700:178 backend tests,
2 actual-model opt-in skips,24 desktop/mobile browser tests, migration/model drift,
Ruff/format, TypeScript/build and dependency audits.113 actual-model assistant tests and
21 synthetic extraction cases were run separately; CI downloads no weights or paid services.

## Registered product identifier search

Two new API regressions failed against the previous head: product q ignored registered
identifier values, and identifier-list q ignored its value entirely. They pass after the
fix, exercising multiple matching aliases without count inflation, pagination, literal
percent/underscore/backslash, case-insensitive lookup, tenant/viewer scope, active/dimension
filters, unchanged SKU search and immediate rename/delete visibility. Assistant domain tests
check exact approved price evidence, zero cross-tenant matches and no business writes.
New desktop/mobile browser scenarios search both catalog and identifier pages through real
APIs; existing assistant scenarios additionally query an alias with technical filters.

Local validation:181 backend passed,2 actual-model opt-in skips; separate opt-in assistant
run114 passed;26 desktop/mobile browser tests passed after backend database tests. Ruff,
format and TypeScript passed. Provider/grammar did not change; no new model accuracy
benchmark is claimed for identifier intent.

Identifier-search implementation7ae5814 passed both PR CI jobs40137930093:181 backend,
2 opt-in skips,26 desktop/mobile browser, migration/model drift, Ruff/format,
TypeScript/build and dependency audits. Separate opt-in assistant run114 passed.

## Queued session rotation

Six PostgreSQL concurrency cases in test_session_concurrency.py observe actual lock waits:
session expiry/revocation while waiting; user deactivation/password revocation winning the
user lock; rotation winning before a real password-change request; and two rotations of the
same token. Assertions cover401, zero new tokens/audits for denied refresh, revocation of
newly rotated tokens, single-use rotation and unaffected unrelated-user access.
Three of the first four cases failed against627516b (expiry/deactivation and reversed
user/session lock order); all four passed after the fix. The two winner-order cases then
passed. One accidental overlap of local backend test processes invalidated a preliminary
run; it was stopped and discarded, with the final suite run alone on the disposable _test DB.
No browser tests share that database during backend execution.

Final isolated local run:187 passed,2 actual-model opt-in skips; Ruff/format passed.
One existing Starlette/httpx deprecation warning remains. No provider/grammar changes
were made; no new actual-model evaluation is claimed for this authentication fix.

Identifier kind length regression:30-character Code is accepted;31/80-character kinds are422
on create/update, preserving the original row and leaving no failed-write audit/idempotency
record. A corrected request may reuse its rejected create key. Baseline4ac7080 returned503
DataError for31 characters; the schema now documents/enforces the existing VARCHAR(30) limit.

Both CI jobs passed for authentication4ac7080 (run40141074361), then final combined
implementation b4753b4 (run40141226238). Final job logs confirm188 backend passed,
2 actual-model opt-in skips and26 production desktop/mobile browser passed. Clean migration/
model-drift, Ruff/format, TypeScript/build and both dependency audits passed. Actual-model
extraction was not rerun for these authentication/input-bound changes; historical evidence
remains separate. The existing Starlette/httpx deprecation warning remains.

## Identifier text-query performance regression

The opt-in isolated _benchmark tool additionally accepts --identifier-search, using the
same apply_text_search helper as resource lists. Two aliases per product in each tenant
exercise literal wildcard escaping, direct name/SKU, identifier/missing text and a combined
numeric range, with count/page/scope assertions and verified rollback. It remains outside
ordinary pytest/CI with no latency assertion. test_identifier_search additionally verifies
one query combining direct-name, direct-SKU and duplicate-alias matches yields exactly three
unique products across one-row pages; a technical range preserves the correct two products.

The baseline experiment is reproducible at227e1fe; the selected application query uses
set membership in matching tenant product IDs instead of correlated EXISTS. Both synthetic
experiments asserted the same counts/page sizes/tenant identity and verified rollback;
artifacts and measured limits are in CATALOG_SEARCH_PERFORMANCE.md. No wall-clock performance
gate was added to CI; semantic regressions remain the automated correctness gate.

Selected query05dd1f3 passed both PR CI jobs40153054219. Actual job logs confirm189
backend passed,2 actual-model opt-in skips and26 production desktop/mobile browser passed;
clean migration/model drift, Ruff/format, TypeScript/build and pip/npm audits passed. The
isolated local full run also passed189 with2 skips. Provider/grammar were unchanged and
actual-model extraction was not rerun. Query-only artifacts are not API/concurrent-load evidence.

## Bounded HTTP benchmark safety

Eleven new cases test fail-closed suffix/empty/exclusive guards, bounded options, transactional
refusal to erase unexpected idempotency/business history, and cleanup of a committed synthetic
seed after an injected HTTP-workload failure while preserving existing fixture tenants/users.
All destructive integration assertions run only on the normal disposable *_test fixture DB;
the test-only transport/guard replacement does not exist in the CLI entry point.
The opt-in HTTP tool was actually exercised at200 products (smoke) and10000 products/20000
identifiers (200 timed real HTTP requests,1/4 closed-loop clients). Every response checks exact
IDs/count/order, tenant, attributes, labels/rules and headers; generated seed/auth/audit rows
were removed and verified. The extracted query seed was rerun at200 products/8 cases with
rollback verified. These experiments are separate from pytest and download no model weights.
Details, reproduction, timeout/crash limits and raw evidence: CATALOG_SEARCH_PERFORMANCE.md.

HTTP benchmark/safety implementation7cd3ae4 passed both PR CI jobs40157406505. Actual logs
confirm200 backend passed,2 actual-model opt-in skips and26 production desktop/mobile browser
passed; migration/model drift, Ruff/format, TypeScript/build and pip/npm audits passed. The
local full run also passed200 with2 skips, and all11 safety tests passed again after pooled
connection disposal was added. No actual-model extraction rerun or production SLO is claimed.

## Approved local invoice intake

New invoice tests exercise scopes/roles, raw-byte limits/types, same-file duplicate/replay,
version conflicts/edit-after-review, immutable evidence/revisions/FKs, no business posting,
revocation/demotion during OCR, saturation, exact strings/precision, temporary-file cleanup and
timeout. Real native cases cover PNG OCR, scanned PDF OCR, embedded-text PDF extraction and
invalid/type-mismatched/4-page rejection. A separate three-case synthetic evaluator retains
an observed Persian decimal-separator failure; this is not a broad accuracy benchmark.
Native tools/fas+eng data are installed in Docker/CI. Original text/history remain untrusted;
see INVOICE_INTAKE.md for reproduction/evidence and human numeric-check requirements.

A further subprocess-environment regression asserts OCR/readiness receive no DATABASE_URL,
proxy or unrelated runtime secret, keep one OpenMP thread and use the private working/home
folder. Actual native PNG/scanned-PDF/text-PDF tests still run, checking minimal-env compatibility.
