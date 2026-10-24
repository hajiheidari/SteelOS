# API contract — implemented M1

Base: `/api/v1`. OpenAPI is generated at `/openapi.json`, interactive docs at `/docs`.
English request/response identifiers, UUID IDs, decimal strings, timezone-aware timestamps.
Request models reject unknown fields, including client-supplied organization IDs in domain data.

## Identity

- `POST /auth/login`: `{email,password,organization_id}`. Organization choice is verified
  against membership, not treated as authorization. Returns opaque bearer token, expiry.
- `GET /auth/me`: user, current organization, role and effective permissions.
- `POST /auth/refresh`: single-use rotation; requires valid unexpired bearer session.
- `POST /auth/logout`: revoke current session.
- `PUT /auth/password`: current/new password; revokes all of this user's sessions.
- `PUT /organization`: admin updates organization name.
- `GET|POST /organization/members`: admin lists/enrolls new users.
- `PUT|DELETE /organization/members/{user_id}`: admin changes another user's role/removes
  membership. Self removal/demotion is rejected. Sessions and warehouse grants of a
  removed membership are revoked. Existing global email enrollment requires operator review.

Bootstrap is local CLI only. No anonymous signup, password recovery or email sending.
Roles are a fixed, documented M1 permission matrix, not configurable role tables.

## Domain resources

`catalog-references`, `products`, `product-identifiers`, `parties`, `warehouses`,
`locations`, `warehouse-access`, `price-sources`, `price-observations`:

- `GET /{resource}`: `{items,total,offset,limit}`, default limit 25, maximum 100.
- `GET /{resource}/{id}`: one tenant-scoped record.
- `POST /{resource}`: create; **Idempotency-Key required**, scoped by organization and
  actor. Same key/body replays original result; different body/resource returns 409.
  Retries serialize through membership locking. Replay entries retained indefinitely in M1.
- `PUT /{resource}/{id}`: full validated replacement; immutable identity/organization.
- `DELETE /{resource}/{id}`: admin only; foreign-key references prevent unsafe deletion.
- Exception: price observations cannot be edited/deleted. `POST /price-observations/{id}/decision`
  accepts `{status: "approved"|"rejected"}`, admin only, pending observations only.
- `GET /audit-events`: admin-only tenant-scoped paginated audit history.

Filters: `q` searches name/code/SKU/registration ID or identifier value where supported, `kind`, `role`
(parties), `product_id`, `warehouse_id`, `status`, `category_id`, `manufacturer_id`,
`grade_id`, `standard_id`, `unit`, `active`. Unsupported typed filters return 422.
Sort: `created_at` (default), `name`, `code`, `sku`, `observed_at` where supported;
`direction=asc|desc`. UUID breaks ties for stable pagination.
`price-observations?approved_only=true` additionally requires approved source, approved
observation, observed time reached, and validity strictly in the future at query time.
Never use a raw `status=approved` filter as quotation authorization. There is no quotation
or trading API in M1; future execution must revalidate prices at action time.

Catalog references use kind category/manufacturer/grade/standard. Category rules are a
map, e.g. `{"thickness":{"unit":"mm","required":true}}`. Product attributes are
`{"thickness":{"value":"2.000","unit":"mm"}}`. Only declared rules are accepted;
required dimensions must be present. Units must exactly match the category rule. Categories
with products cannot have rules changed. SKU is uppercased; decimal values are normalized
for technical duplicate detection. Product selling unit and display name do not create a
new technical identity. Identifiers are unique by tenant, kind, value.

Parties support customer and supplier simultaneously, typed contact persons/email/phone
and addresses. Registration ID is unique when provided; names alone are not unique because
different legal parties may share a name. No fabricated Iranian identity checks are applied.

Money must be an integer or a decimal string, never a JSON float. Prices record amount,
currency (IRR/IRT/USD/EUR, no implicit conversion), unit, source, provenance, observed time,
expiry, tax indicator and delivery location/terms. API accepts historical expired observations
for history, but cannot approve them. Source adapters return validated pending observations
only; `MockPriceProvider` supplies local fixtures without network or paid integrations.

## System/errors

- `GET /health`: process liveness independent of DB.
- `GET /ready`: DB connectivity and expected Alembic revision; otherwise 503.
- Errors: `{"error":{"code":"...","message":"...","details":null,"request_id":"UUID"}}`.
- 401 authentication, 403 permission, 404 unknown/out-of-scope record, 409 constraint/retry
  conflict, 422 validation, 429 login throttled, 503 database unavailable.
- Validation details contain field locations/type, never rejected input values.
- `X-Request-ID`, `Cache-Control: no-store`, no stack traces in responses.

Direct API consumers use Authorization Bearer. The Next.js server proxy keeps the bearer
in an HttpOnly SameSite=Strict cookie, removes tokens from browser-visible responses,
and enforces configured APP_ORIGIN for all mutations.

Local mock ingestion can run via `python -m app.modules.pricing fixture.json` with
`STEELOS_INGEST_TOKEN` supplied in the operator environment. Fixture is an array of
PriceInput objects referencing a `mock` source. The adapter uses the authorized API,
deterministic retry keys and pending-only intake; it never writes directly to tables
or calls approval. Do not use real customer data in committed test fixtures.

Concurrent organization-administration requests recheck the actor's current administrator
role after acquiring the organization lock. If another administrator removed or demoted the
actor while it waited, the request returns 403 and does not perform its mutation.

For `PUT /auth/password`, an incorrect current password returns 400 while the existing
session remains valid. A genuinely invalid/expired bearer still returns 401. On a successful
password change, all backend sessions are revoked and the browser proxy deletes its cookie.
Authenticated browser requests receiving 401 return to a fresh login page with a Persian
session-ended message. Explicit logout also uses a fresh navigation to discard workspace state.

Catalog category rules and product validation share a PostgreSQL row lock held until commit.
If product creation wins a concurrent race, changing that category's rules returns 409 after
the product commits. If the rule change wins first, the product validates against the updated
rules. A stale in-memory category object is refreshed when acquiring the lock.

Domain writes also recheck membership after acquiring their transaction lock. A request queued
before a role change/removal cannot perform a write or replay a write response using stale
permission: revoked membership returns 401, insufficient current role returns 403. This applies
to create, full update, admin deletion and pricing decisions.

## Approved warehouse operations extension

See [INVENTORY.md](INVENTORY.md) for the implemented M2 API, immutable ledger,
role/warehouse policy, concurrency rules, migration `0002_inventory` and test coverage.
M1 historical boundaries describe the foundation before this approved extension.

Inventory paged read projections and `q`, `remaining_only`, `unexpired_only`,
`reversible_only` filters are documented in [INVENTORY.md](INVENTORY.md). These are
additive read contracts; no posting or authorization rule changes.

## Bounded foundation reads

`GET /organization/members` is admin-only and now uses the common pagination contract:
limit 1–100 (default 25), nonnegative offset, total and literal case-insensitive email `q`
(maximum 200 characters). Each item includes id (an alias of user_id), user_id, email and
role. Consumers must page explicitly; a single request is not a complete member roster.

Generic domain lists include page-scoped `display_names` for accessible foreign records.
Product list items additionally contain `category_rules` for editing technical dimensions
without downloading the whole catalog. These are read projections; write and single-record
contracts stay unchanged. Warehouse grant labels include tenant member email only for
admin-authorized grant lists. No foreign labels bypass organization/warehouse scope.

Product technical identity/unit becomes immutable once any price observation or stock lot
exists, preserving the meaning of historical prices. Name/SKU edits remain allowed. First
price intake and technical edits serialize on the product row; conflicting edits return409.

## Internal sales draft extension

See [SALES_DRAFTS.md](SALES_DRAFTS.md) for `/api/v1/sales-drafts`, price snapshots,
optimistic versions, immutable revisions and explicit non-binding financial status.
Price observation lists also accept currency and literal search in provenance/delivery fields.

### Iranian invoice monetary policy

Founder-confirmed: IRR, two decimal places, ROUND_HALF_UP (123.456 →123.46), tax added
separately with configurable current default10%. This supersedes the initial no-rounding
interpretation; raw pricing evidence remains exact.

Sales draft list/detail and new revision snapshots include invoice_policy version
iran-invoice-v3, currency=IRR, rounding=half_up, decimal_places=2, calculation=per_line,
currency_matches boolean, tax_workflow=exclusive. amount_rounding=half_up_2 is persisted
per new draft/edit. Per line: base_amount=round(quantity×unit_price,2); tax_total=
round(base_amount×rate/100,2); grand_total=base_amount+tax_total. Header subtotal/tax_total/
grand_total sum line amounts, returned as two-place decimal strings. Raw estimated_amount/
estimated_total remain nine-place evidence for compatibility, not monetary totals.

GET /organization/tax-policy: current session organization default (tax_rate_percent
string, version, mode=exclusive, rounding=half_up, decimal_places=2, calculation=per_line,
invoice_currency=IRR). PUT admin-only: {tax_rate_percent: decimal string0–100, up to6
decimals, expected_version: positive integer};409 on stale version, audit update_tax_policy.
The default10% is the founder's internal business rule, not a statutory assertion.

Sales draft POST optionally accepts tax_rate_percent; omission snapshots the organization
default. PUT omission retains the existing rate (legacy null gets the current default).
Tax-inclusive price observations return409 on draft writes. Price lists support boolean
tax_included. Legacy drafts have null subtotal/tax/grand until a new edit; cancellation
does not configure them. Old revisions/replays are not retroactively changed.
Foreign currencies remain internal estimates only; no implicit conversion or final issuance.

### Internal sales review

POST /sales-drafts/{id}/review (admin, Idempotency-Key): expected_version (strict positive
integer), decision accepted|rejected, optional note≤2000 (nonblank required for rejection).
201 with immutable evidence snapshot and financial_approval=false;409 on stale/cancelled/
already-reviewed version, unconfigured/non-IRR acceptance or invalid price/customer. Editors
and viewers cannot review. Acceptance revalidates locked domain records; rejection may record
an expired/invalid draft for correction. One decision per version; edit for another review.
GET /sales-drafts/{id}/reviews: paginated summaries, limit25,max100,offset.
GET /sales-drafts/{id}/reviews/{review_id}: immutable evidence; tenant scoped404.
Detail adds internal_review and internal_review_usable (current eligibility); list adds only
a bounded current-version summary. Review is internal evidence and never customer issuance.

### Read-only local sales assistant

Authenticated GET /sales-assistant/status: configured/provider/model, availability unchecked
or disabled, read_only=true, fixed tool names and financial_approval=false. Configured does
not assert provider readiness. POST /sales-assistant/query accepts only question (2–1000 chars).
One validated local model extraction (product_query≤120|null,currency), then fixed GET calls
to scoped products/current approved prices (max5 products ×5 prices). No client/model URL,
organization ID, method, mutation or paging override is accepted. Returns source cards with
exact decimal strings, provenance/timestamps/delivery/tax flag, retrieval interval and totals.
Null query means unsupported intent; no invented answer or quote.503 when disabled/model
invalid/unavailable,429 at per-worker concurrency2. Session is rechecked before returning data.
Successful reads audit actor/org without question text. Details/setup in SALES_ASSISTANT.md.

### Exact product attribute filters and assistant dimensions

GET /products accepts attributes=<JSON object>, max4096 characters, max8 Code keys. Each
value is {value:positive decimal string,unit:mm|cm|m|kg|none}, with existing20-digit/6-place
bounds. All predicates are ANDed with existing tenant/q/reference/active filters and applied
before pagination/count. mm/cm/m match exact equivalence; kg/none only the same unit. No
float/bool, malformed/grouped/duplicate-key JSON, unsupported unit or arbitrary SQL expression
is accepted;422. Other resources reject this parameter. Example width1.2m matches1200mm.

Assistant POST still accepts question only. The server extracts explicit named length
constraints independently from the model; response adds dimensions and needs_clarification.
Ambiguous/missing/unsupported repeated/unsupported dimensions return no results and skip inference/data
reads (session authorization is still rechecked). Exact no-match never retries without filters.
Model product query must be copied from the remaining question, not generated/translated.
Results remain scoped, read-only, bounded and financially unapproved.

Assistant named dimensions additionally accept a finite Persian number-word grammar:
یک..ده, نیم, and integer + و نیم (whitespace/ZWNJ). These become exact decimal-string
attribute filters before inference; generic product API input remains decimal strings.
Unsupported compound number words request clarification without model or domain reads.

Inclusive product dimension ranges use the existing attributes filter, e.g.
`{"thickness":{"min":{"value":"0.2","unit":"cm"},"max":{"value":"3","unit":"mm"}}}`.
Both positive bounds are required; compatible length units are compared exactly. Equal
bounds are valid only with inclusive endpoints; reversed/incompatible bounds return422. Each attribute is either an exact
value/unit or min/max object (no mixed/extra fields), and all attributes combine with AND.
Assistant dimensions responses preserve this min/max structure. Persian numeric or finite number-word از…تا / بین…و
with named attributes are supported; omitted lower unit inherits the explicit upper unit.

The finite Persian number grammar applies to both inclusive bounds as well as exact values:
`ضخامت از دو تا سه و نیم میلیمتر` produces min2/max3.5mm. Digit/word mixtures and optional
explicit compatible lower units use the same existing decimal-string JSON contract. Reversed,
missing or unsupported word bounds/units request clarification without inference/data search.

One-sided dimension comparison: `{"thickness":{"op":"gt","bound":{"value":"2","unit":"mm"}}}`
in the same attributes parameter. op is gt/gte/lt/lte; bound uses the existing positive
Decimal(20,6) dimension contract. No null/implicit endpoint, extra fields, floats, booleans,
arbitrary operator or mixed exact/range/comparison object. Compatible length-unit conversion
is exact; kg/none only compare to the same unit. Different attribute keys combine with AND.
Assistant responses preserve {op,bound}; explicit Persian phrases and symbols are parsed before
inference. Negation/approximation and disjunction require clarification. Only an explicitly connected adjacent opposite-comparison pair can merge on one key; other repeats require clarification.

Two-bound objects accept min_inclusive/max_inclusive strict booleans, default true. Example:
`{"thickness":{"min":{"value":"2","unit":"mm"},"max":{"value":"3","unit":"mm"},"min_inclusive":false}}`
is2<x≤3mm. Both endpoints are still required; equal physical bounds with any excluded end
are422. Assistant filters omit default-true flags and retain false flags; legacy inclusive
serialization is unchanged. Two adjacent opposite comparisons on the same attribute joined
by و/and map to this contract. Other repeated constraints request clarification.

Product q additionally matches values from registered product-identifiers in the current
organization, case-insensitively as a literal substring. %, _ and backslash remain literal,
not client-controlled LIKE patterns. Correlated EXISTS avoids duplicate product rows/counts
when multiple identifiers match. Existing technical/active/reference filters still combine
with AND. product-identifiers q searches its value; product_id/kind filters remain independent.
Identifier rename/delete is reflected on the next read; uniqueness and stored values are unchanged.

Session refresh revalidates the active user and current, unexpired organization-scoped
session after waiting for locks. A token that expires/is revoked while queued returns401
and produces no new token. Refresh and password changes use user-before-session lock order;
password change also revokes a token issued by an earlier concurrent rotation. Concurrent
refresh of one token yields one successful rotation; the other returns401. Response contracts,
session duration and current-organization membership authorization are unchanged.

product-identifiers kind is an English Code of1–30 characters, matching its database column;
value remains1–100 characters. Both create and replacement update reject longer kinds with422
before database writes (OpenAPI includes maxLength30), not a misleading database-unavailable503.
