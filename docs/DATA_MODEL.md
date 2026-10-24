# Data model — M1 implementation and M2 contracts

PostgreSQL tables are currently in `public`; Python modules define bounded responsibilities.
The earlier list of separate SQL schemas was a plan, not an implemented requirement.
A single reviewed Alembic baseline creates all M1 tables. UUID primary keys, TIMESTAMPTZ
created/observed/expiry dates and indexed organization IDs throughout tenant data.

Implemented tables: organizations, users, memberships, auth_sessions, login_attempts,
catalog_references, products, product_identifiers, parties, warehouses, locations,
warehouse_access, price_sources, price_observations, audit_events, idempotency_records.

- Users are global; memberships bind users to organizations with fixed M1 roles.
- Sessions bind to an existing composite organization/user membership. Token SHA-256
  digests are stored; raw bearer secrets are not persisted.
- Catalog reference kind represents category/manufacturer/grade/standard. Extensible
  category rules and product dimensions use validated JSON; numeric dimension strings
  avoid binary floating point. Specification fingerprint and SKU unique per organization.
- Product, identifier, warehouse grant, location and pricing FKs include organization ID.
  A location's parent FK also includes warehouse ID. API prevents cycles and serializes
  hierarchy changes using a warehouse row lock. Parent/warehouse moves are validated.
- Parties have multiple roles, contact records and addresses as bounded typed JSON collections.
  A non-null registration ID is unique per organization. Missing ID is allowed; name-only
  deduplication would incorrectly merge real parties.
- Price amount uses NUMERIC(24,6), explicit currency and unit, positive amount, expiry later
  than observed_at, immutable observation payload and separate approval decision.
- No stock or accounting balances exist. Physical warehouse location never implies ownership.

## Deletion and retention

Foreign keys default to RESTRICT/NO ACTION. Admin deletion of unused master data is allowed;
referenced records return conflict. Deactivate products, parties or warehouses when retention
is needed. Price observations and audit events have no edit/delete API. Audit stores actor,
action, resource, resource UUID and time; sensitive payloads are not copied. No blanket cascade
for organizations/users. Membership removal explicitly revokes sessions/grants but keeps user
and audit history. Idempotency results retained indefinitely for M1; future cleanup requires
business retention and retry-window policy. No claimed statutory retention duration.
Operational database backups and privileged access remain operator responsibilities.

## M2 inventory contracts (defined, not operational)

`app/modules/inventory_contracts.py` defines LotContract, MovementContract and
ReservationContract. IDs and references must all resolve inside the authorized organization
when M2 persists them. A lot has product, physical warehouse/location, unit and legal owner:
`company` means current organization; `party` requires explicit owner_party_id. Company and
customer goods can coexist at one location without transferring title.

Quantities: NUMERIC(20,3) for kg (Decimal), strictly positive event quantities, explicit unit.
Future movement histories are append-only receipt/dispatch/transfer/block/unblock/reversal
events. Corrections reference original events. Transfers must be atomic and conserve quantity
and ownership. Reservation histories are separate active/released/fulfilled/expired events.
Available = on-hand − blocked − active reserved, within one ownership/product/location/unit
scope, with transactional non-negative enforcement. No editable available/reserved counters.
Ownership transfer requires a separately authorized business event, never a location transfer.

## Future accounting boundary

Unit rates NUMERIC(24,6); quantities NUMERIC(20,3); no float arithmetic. Founder-confirmed
Iranian invoice currency is IRR with two-place ROUND_HALF_UP monetary amounts. Preserve
raw rate/quantity precision for calculation evidence. Future invoice/journal amount
columns must have scale2 and a validated integer range; NUMERIC(20,2) is a recommendation
only and must not silently overflow the larger supported internal draft amounts. Accounting module consumes
validated domain events through controlled APIs with idempotent posting references. For each
posted journal: same organization, valid open period/accounts, explicit currency, total debits
= total credits, at least two nonzero lines, no negative debits/credits, exactly one side per line.
Posted journals are immutable; corrections use linked reversals. FX and accounting integration policy must
be specified before implementation; domestic monetary amounts use two-place ROUND_HALF_UP.
Internal tax uses separate addition with configurable default10% (founder business rule,
not a legal compliance claim). Run in parallel with the existing reference process;
reconcile opening balances, daily journals, counterparties, inventory valuation and period-end
trial balance before any authority transfer. M1 contains no accounting engine or tax connector.
Current official Iranian specifications must be reviewed before later production tax integration.

## Approved warehouse operations extension

See [INVENTORY.md](INVENTORY.md) for the implemented M2 API, immutable ledger,
role/warehouse policy, concurrency rules, migration `0002_inventory` and test coverage.
M1 historical boundaries describe the foundation before this approved extension.

## Internal sales draft extension

Migration0003_sales_drafts adds sales_drafts (tenant code/customer/currency/version/state),
sales_draft_lines (tenant FKs, NUMERIC20,3 quantities, NUMERIC24,6 source prices and immutable
per-version evidence) and append-only sales_draft_revisions. See SALES_DRAFTS.md for exact
raw Decimal estimates, draft-only line replacement, terminal cancellation, retention and
explicit absence of final financial money/tax/inventory/accounting transactions.

Migration0004_sales_tax adds organization sales_tax_rate_percent NUMERIC(9,6), default10,
tax_policy_version, nullable sales_drafts.tax_rate_percent and amount_rounding. DB checks
enforce internal0–100 bounds, positive policy versions and the half_up_2 policy. Legacy
null values preserve unconfigured history; new edits snapshot rate/policy. Derived two-place
monetary totals and raw nine-place evidence are retained as strings in revision JSON.
