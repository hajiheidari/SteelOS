# Internal sales drafts

This module prepares internal, non-binding sales drafts. It cannot approve/issue a customer
quotation, reserve/move stock, transfer title, post accounting, charge money or submit tax.
The founder clarified Iranian invoices use IRR and monetary amounts use two decimal places
with normal rounding (ROUND_HALF_UP, e.g.123.456 →123.46), superseding the earlier
“no rounding” interpretation.
Tax is added separately to the base price. The founder confirmed the current internal
default is 10%, configurable rather than hardcoded as a legal rate.

## Contracts

All routes below use `/api/v1/sales-drafts`. Tenant identity comes from the authenticated
session. Admin/editor may mutate; all organization members may read. Every write requires
`Idempotency-Key` (max 100). Authorization is checked before replay. Replay returns the
original response including its `price_checks_as_of`; GET refreshes current price checks.

- POST collection: code, customer_id, currency, optional note and tax_rate_percent, 1–100 lines. Each line has
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

Quantities use NUMERIC(20,3), source unit prices NUMERIC(24,6). Floats/booleans, invalid
precision, duplicate price lines and fractional piece quantities are rejected. Quantity is
in the explicit price unit, which may differ from the product stock unit; no conversion
occurs. Calculations use Decimal precision60, covering 100 maximum-sized lines.

For each configured line (no JavaScript/float money arithmetic):

1. base_amount = ROUND_HALF_UP(quantity × unit_price, 2).
2. tax_total = ROUND_HALF_UP(base_amount × tax_rate_percent / 100, 2).
3. grand_total = base_amount + tax_total.

Header subtotal, tax_total and grand_total are sums of the corresponding rounded line
amounts, serialized with exactly two fractional digits. This per-line policy keeps line and
document sums consistent. For example two0.045 base lines at10% each become base0.05 +
tax0.01 =0.06 per line, with document subtotal0.10, tax0.02, grand0.12. SQL page aggregates
and Decimal detail calculations are tested against the same boundary cases.
`estimated_amount`/`estimated_total` retain raw nine-place exact products as compatibility
and calculation evidence; they are not the two-place monetary subtotal/total. Source unit
price precision and quantity precision are not reduced. UI monetary totals use the two-place
fields; old historical raw evidence remains readable without retroactive rounding.

List/detail responses expose invoice_policy: version=iran-invoice-v3, currency=IRR,
rounding=half_up, decimal_places=2, calculation=per_line, currency_matches (draft currency
equals IRR), tax_workflow=exclusive. Each new draft/edit stores amount_rounding=half_up_2
and its tax rate; old revisions/replays are not rewritten. This metadata never grants
financial approval/issuance. IRT/USD/EUR remain internal estimates only and cannot become
Iranian invoices in those currencies; no implicit FX/toman conversion occurs. Freight,
discounts, FX and final approval are outside this calculation stage.

Tax-inclusive observations are rejected for new/edited drafts; provide an explicitly
approved tax-exclusive base observation instead of implicit netting or double taxation.
Price lists support tax_included=false for the form.

GET /api/v1/organization/tax-policy reads the session organization's default; its members
may read. PUT is admin-only with tax_rate_percent and expected_version, serialized with
organization administration and audited; stale version returns409. Default10%, range0–100
inclusive, at most6 decimal places, decimal strings (no floats/booleans). This range is an
application bound, not a legal assertion. New drafts snapshot the organization default
unless an editor/admin explicitly supplies a rate. Updates retain the stored rate unless
explicitly changed. Changing defaults never reprices existing drafts/revisions. Concurrent
default changes may be observed before or after a draft's default read; the selected rate
is persisted. Cancellation retains rate and rounding policy.

Migration0004_sales_tax adds organization default/version and nullable draft rate/rounding.
Existing drafts retain null rates/policies and null subtotal/tax/grand until explicitly
edited into a new version. Cancellation does not configure legacy tax. Old immutable
revisions and idempotent responses remain unchanged. Founder currency, decimal/rounding
and tax questions are resolved; final customer issuance still requires its own controlled
domain transition, not this calculation alone.

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
Only currently approved, unexpired, tax-exclusive prices in the selected currency are offered. Explicit
price units, tax-inclusion and delivery conditions are displayed. Two-place monetary totals are
server-calculated; the form accepts a version-specific tax rate and settings expose the
organization default. Native search Enter does not submit its surrounding form.

Users can create/edit internal drafts, view immutable historical versions, reload current
price/customer checks and cancel with explicit confirmation. Historical views show the
original check time and cannot be edited. There are no financial approval, customer export
or send controls. Browser tests on desktop/mobile verify the full lifecycle, snapshot
history, source-approval revocation warnings and unchanged stock entry count.

## Internal review (implemented, not financial issuance)

POST /{id}/review is admin-only with Idempotency-Key and {expected_version, decision:
accepted|rejected, note (max2000)}. A rejection requires a nonblank reason. One immutable
decision per version; edits create a new version requiring a fresh review. A current review
never freezes edits or becomes financial approval. Self-review by an administrator is allowed
at this internal stage; no maker/checker segregation or agent principal is claimed.

Acceptance requires an editable draft, matching current version, IRR and configured
half_up_2/rate. The API revalidates stored customer/price/source/product data under the same
shared master locks as draft creation; the review caller cannot supply prices or totals.
A final snapshot validity check rejects prices expiring during preparation. Rejection can
record invalid/expired pricing for correction. Review snapshot, audit and idempotency commit
atomically. Concurrent reviewers yield one201/one409; replay rechecks current admin authority
and organization scope, retaining original evidence rather than recalculating it.

GET detail returns internal_review summary for the current version and internal_review_usable
based on current version/state/customer/prices. Expiry/revocation can make it false while the
original accepted review remains immutable. List returns a page-batched current review summary
without evidence snapshots or a live usability claim. Neither field authorizes customer use;
financial_approval remains false. GET /{id}/reviews is paginated (limit25,max100,offset);
GET /{id}/reviews/{review_id} reads immutable snapshot evidence. Cross-tenant IDs return404.

Migration0005_sales_review adds a tenant/version FK to immutable draft revisions, one review
per version and a PostgreSQL guard prohibiting update/delete or insert against an old,
cancelled or different-tenant draft. API locks the draft to serialize review/edit/cancel.
No automatic retention/deletion job exists. The Persian panel requires a confirmation step,
shows notes/version history and has no customer-send/export or financial-approval control.
