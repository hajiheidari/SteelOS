# Internal sales drafts

This module prepares internal, non-binding sales drafts. It cannot approve/issue a customer
quotation, reserve/move stock, transfer title, post accounting, charge money or submit tax.
Financial rounding and tax workflow are awaiting the founder's actual business rules.

## Contracts

All routes below use `/api/v1/sales-drafts`. Tenant identity comes from the authenticated
session. Admin/editor may mutate; all organization members may read. Every write requires
`Idempotency-Key` (max 100). Authorization is checked before replay. Replay returns the
original response including its `price_checks_as_of`; GET refreshes current price checks.

- POST collection: code, customer_id, currency, optional note, 1–100 lines. Each line has
  price_id and quantity only. Code is normalized uppercase and unique per organization.
- GET collection: limit 1–100 (default 25), offset, literal q (code/customer name, max200),
  optional status=draft/cancelled. Returns total, page, customer label, line_count and
  exact estimated_total; list has_expired_price concerns snapshot expiry only. GET detail
  additionally checks current source approval, product/customer eligibility and price status.
- GET /{id}: header, snapshots, quantities, units, unit prices, raw estimated amounts,
  customer_eligible, per-line price_usable and overall prices_usable as of price_checks_as_of.
  financial_approval is always false. These indicators never authorize final issuance.
- PUT /{id}: same payload plus expected_version. Code is immutable. Version conflict or
  cancelled state returns409. The full line set is replaced atomically with a new revision.
- POST /{id}/cancel: expected_version; retains lines and adds a terminal revision.
- GET /{id}/revisions: paginated version/actor/timestamp metadata without large snapshots.
- GET /{id}/revisions/{version}: immutable historical response snapshot.

There is no DELETE or approve/export/send endpoint. Inaccessible tenant IDs return404.

## Pricing and arithmetic

Customer must be an active party with customer role (supplier role may coexist). New/edited
lines require an approved, currently valid observation and approved source from the same
organization, active product and matching draft currency. Product, price, source, tax-inclusion
indicator, delivery terms, provenance and validity are snapshotted from domain records;
clients cannot supply line amounts or tax values. Shared locks stabilize validation against
master edits and price-source approval changes. Snapshot names/technical specifications
remain historical even when labels change. Current expiry/source revocation is shown by GET.

Quantities use NUMERIC(20,3), unit prices NUMERIC(24,6). Floats/booleans, invalid precision,
duplicate price lines and fractional piece quantities are rejected. Quantity is in the
explicit price unit, which may differ from the product stock unit; no conversion occurs.
Raw quantity × price estimates use Decimal precision60 and nine fractional digits. Up to
100 maximum-sized lines fit this calculation without default Decimal-context rounding.
Estimates are not rounded legal money totals; tax, transport, discounts, FX and financial
approval remain outside this draft stage. No assumed Iranian tax rate is introduced.

## Persistence and retention

Migration0003_sales_drafts adds tenant-scoped header/lines/revisions and a compound unique
price observation key for tenant FKs. Database triggers prevent header deletion, invalid
version transitions, changes after cancellation, line mutation outside editable drafts and
revision update/delete. Revisions, audit and idempotency commit with the draft in one
transaction. Database owner privileges can bypass guards; do not expose DB credentials to
end users or agents. Draft history has no automatic deletion/retention job.

Tests cover snapshots, exact large-number arithmetic through DB/HTTP, source/expiry checks,
customer roles, explicit units, tenant isolation/FKs, replay, immutable history, terminal
cancellation, optimistic concurrency and absence of stock effects. UI delivery status is
reported in DEVELOPMENT_STATUS.md; this document does not imply final financial approval.

## Persian workspace

The sales-draft page uses real APIs and bounded searchable customer/product/price selects.
Only currently approved, unexpired prices in the selected currency are offered. Explicit
price units, tax-inclusion and delivery conditions are displayed. Exact raw estimates are
server-calculated. Native search Enter does not submit its surrounding form.

Users can create/edit internal drafts, view immutable historical versions, reload current
price/customer checks and cancel with explicit confirmation. Historical views show the
original check time and cannot be edited. There are no financial approval, customer export
or send controls. Browser tests on desktop/mobile verify the full lifecycle, snapshot
history, source-approval revocation warnings and unchanged stock entry count.
