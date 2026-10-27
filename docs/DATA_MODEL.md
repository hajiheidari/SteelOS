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

Migration0005_sales_review adds sales_draft_reviews: tenant/draft/version FK to immutable
revisions, accepted/rejected decision, note, reviewer, timestamp and evidence JSON snapshot.
One decision per version. Trigger prevents update/delete and insertion against any noncurrent
or cancelled draft. Editing/cancelling the header preserves prior reviews but invalidates
current-version usability. No financial-approval, stock or accounting row is created.

Product attribute search compares canonical JSON value/unit pairs. Length-unit equivalence
is derived for search only (mm/cm/m); other units require equality. No stored specification,
quantity, price or balance changes. Search adds no tables/migration; schema remains0005.

Inclusive dimension search ranges are query contracts, not new stored product attributes.
Products retain one canonical positive decimal string and unit per dimension. Range bounds
never rewrite dimensions or create stock/price conversions; invalid legacy JSON is excluded
by guarded query extraction. No schema migration accompanies range search.

One-sided dimension comparisons are query-only contracts with an explicit positive bound,
not new persisted dimensions. No artificial minimum/maximum sentinel is stored. Guarded
numeric extraction additionally excludes invalid nonpositive legacy values from comparisons.

min_inclusive/max_inclusive are query-only flags, both default true; they are never stored
on products. Equal bounds with an excluded end are invalid. No ledger, monetary precision,
product identity or existing dimension value changes when an interval excludes an endpoint.

Product identifiers remain unique by organization/kind/value, with existing tenant/product FKs.
Searching them neither normalizes nor changes identity/uniqueness. Multiple matching aliases
must not duplicate their product in list totals. Alias edits/deletion affect future lookups;
price/stock product references and historical snapshots keep their original product IDs.

ProductIdentifier.kind is VARCHAR(30); its input Code max_length30 matches this existing
storage boundary. This validation fix changes no stored identifier values, tenant uniqueness,
FKs, migration or identity rules. Overlong kinds are rejected before attempting writes.

## Approved invoice transcription extension

Migration0006_invoice_intake adds tenant-scoped invoice_intakes and immutable revisions.
Source hash is unique per tenant; original text/extraction evidence are immutable, corrected
text/fields are optimistically versioned. No binary/source file, business party/product/price,
stock or accounting reference is stored. Decimal transcription candidates serialize as strings
inside validated JSON; they are not a financial ledger. No deletion API/automatic retention
job; sensitive text/history/idempotency remain until a separately reviewed policy. See
INVOICE_INTAKE.md for native boundaries, tenant FKs, errors and actual OCR accuracy limits.

Migration0007_crm_follow_ups adds crm_follow_ups with UUID/TIMESTAMPTZ, indexed organization/due,
composite tenant-party FK and kind/status checks. It is a normal shared CRM task record with
existing admin deletion and metadata audit, not an immutable financial/stock/history ledger.

Migration0008_agent_workbench adds tenant-scoped agent_sources/runs/evidence/reviews. Source
content is immutable/revocable; evidence/reviews have composite tenant FKs and run history is
append-only. Runs retain model_name/policy_version. Source/run text is private organization data;
there is no erasure/retention automation or public publishing contract. INTERNAL_AGENTS.md.

The documented learning catalog (`foundation-learning-v1`) is application-authored shared content, not tenant business data. Its self-check endpoint performs no writes. No learning-attempt/progress/certificate table is implemented; the UI retains answers only for its mounted lesson. Catalog version is required when checking answers to prevent grading against a changed lesson contract.
