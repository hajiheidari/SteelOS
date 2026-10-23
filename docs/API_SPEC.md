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

Filters: `q` searches name/code/SKU/registration ID where supported, `kind`, `role`
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
