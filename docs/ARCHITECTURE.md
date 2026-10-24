# Architecture

Modular monolith: FastAPI + Pydantic + SQLAlchemy 2 + Alembic, PostgreSQL 17; Next.js
App Router + React + TypeScript. One API process can scale horizontally; persistent sessions,
throttles and idempotency use PostgreSQL. No Redis, Celery, queue, paid AI or object store needed
for M1. Requirements are pinned, frontend uses npm lockfile.

`app/config.py` handles environment settings; `db.py` owns pool/session lifecycle; models
contain DB constraints; schemas define bounded request contracts; `security.py` authenticates
and authorizes; `modules/identity.py` handles identity and settings; `modules/resources.py`
shares list/transaction mechanics and explicit catalog/CRM/warehouse/pricing domain validators.
Router registration preserves concrete Pydantic request schemas in OpenAPI. SQL schemas and
more granular service extraction can follow real complexity rather than premature infrastructure.

Each mutation commits domain data, audit and idempotency atomically where applicable.
Hierarchy and retry locks serialize conflicting operations. Prices are immutable observations
with one explicit admin decision, validated source and time interval. Raw price records are
history; approved_only query is the current eligible view, not a quotation API.

Next.js server proxy holds the API credential in an HttpOnly cookie and applies exact-origin
CSRF checks. UI retrieves real APIs, paginates tables, validates forms, displays Persian labels
and uses Intl Persian calendar/Tehran timezone. Dates stored UTC; local datetime form input
is labelled as device-local and converted to UTC before sending. Financial strings never pass
through JavaScript Number. Native font fallback avoids external font dependencies.

PWA manifest and responsive layout are implemented. No offline caching of sensitive data.
Data entry uses dynamic category dimension rules, typed contact/address rows, warehouse
hierarchy selection, price provenance and source approval. Reference pickers currently fetch
all authorized rows in pages; server-side autocomplete is a future scalability improvement.

Stock operations, trading and accounting remain separate future modules. Inventory contracts
only define ownership/location/movement/reservation boundaries. Accounting journal invariants
and parallel reconciliation are specified in DATA_MODEL.md. No engine is represented as ready.

Product forms are driven by the selected category's dimension rules: required fields cannot
be removed, optional blank dimensions are omitted, and their configured units are read-only.
Persian/Arabic digits and standard Arabic decimal/grouping separators are normalized to ASCII
decimal strings at submission; money and dimension values are never converted to JS Number.

Workspace loads carry a view identity (organization/role/page/filter/pagination) plus a request
sequence. Late responses, errors and pending mutation refreshes from an obsolete view cannot
replace the current page. Navigating also clears the previous page's table immediately.

## Approved warehouse operations extension

See [INVENTORY.md](INVENTORY.md) for the implemented M2 API, immutable ledger,
role/warehouse policy, concurrency rules, migration `0002_inventory` and test coverage.
M1 historical boundaries describe the foundation before this approved extension.

The sales module prepares internal drafts through controlled domain APIs. It snapshots
approved pricing evidence and records optimistic revisions in one transaction with audit
and shared idempotency mechanics. It has no direct stock-ledger or accounting dependency;
future trading/financial approval must be a separately validated domain transition using
the founder's tax rule (exclusive addition with configurable default10%), never a side
effect of saving this draft. Iranian invoice
currency is IRR and monetary amounts use two-place ROUND_HALF_UP; internal
foreign-currency estimates do not authorize domestic invoice issuance or implicit FX.

Internal tax policy is organization-scoped and admin-versioned. Drafts snapshot their
rate; editing the default cannot change old amounts. Base, separate tax and grand total
use Decimal ROUND_HALF_UP per line to two places, then sum line amounts. Raw input
evidence remains exact; no binary float calculations occur. Tax-inclusive pricing must supply an approved net base
observation explicitly; no implicit netting or double tax is allowed. See SALES_DRAFTS.md.

Internal review records immutable, version-bound human decisions separately from editable
sales drafts. Current usability is derived, not a stored approval flag; price expiry or a
new version invalidates it. Domain master locks and the draft-row lock serialize acceptance
against changes. No financial issuance or agent execution is implied. AGENT_READINESS.md
tracks implemented prerequisites and unimplemented AI adapters/principals/tools explicitly.

The first model-connected assistant is a bounded local intent extractor plus controlled API
retrieval, not a free-form authority on domain data. Assistant modules separate schemas,
local provider, fixed read-only tools and router. Its domain client calls existing APIs with
current user authorization; only audit recording touches persistence. No model gets domain
credentials/results or an arbitrary tool/URL chooser. Returned facts come from domain source
cards with original timestamps/units/provenance. Stateless requests avoid conversation memory;
local provider is optional/default-disabled, with a resource-limited Compose profile and no new
mandatory dependencies. Production agents, writable proposals and broader quality evaluation
remain separate work. See SALES_ASSISTANT.md and AGENT_READINESS.md.

Technical search is split into deterministic measurement extraction, optional local product-term
extraction and exact catalog filtering. Generic catalog_search supports bounded extensible
attribute keys, canonical Decimal comparisons and mm/cm/m equivalence before pagination.
Assistant recognized linear names are deliberately narrower than the catalog's extensible
attributes. Ambiguity stops data retrieval; no unconstrained fallback exists. This preserves
business constraints even when a small local model misinterprets language. No migration or
change to stored dimensions, financial precision, inventory units or ownership is needed.

Catalog search additionally supports inclusive ranges. Bound equivalence uses Decimal;
PostgreSQL compares stored string measurements through a regex-guarded CASE numeric cast,
never a cast relying on WHERE evaluation order. JSON type checks exclude non-string values.
Existing tenant predicates/count/pagination remain in the same query. No migration is needed;
range scans need future performance measurement before large-catalog production adoption.

Measured catalog range comparisons now select a compatible unit with CASE before checking
its bounds. The inner bounded numeric CASE and JSON string guard remain intact. Synthetic
query plans and performance limits are documented in CATALOG_SEARCH_PERFORMANCE.md; observed
warm-cache medians are not an API SLO or evidence that tenant scans have been eliminated.

Exact dimensions and both inclusive range bounds share one deterministic finite-number parser.
Persian number words are resolved before model inference into existing Decimal search schemas;
no new domain filter, persistence field or pricing calculation is introduced by word ranges.

One-sided dimension comparisons share the catalog range SQL guard and compatible-unit CASE.
A typed operator enum selects a fixed Python/SQLAlchemy comparison, with no missing-endpoint
sentinel or interpolated SQL. Assistant extraction records consumed valid operator spans;
unsupported markers remaining outside them prevent inference and retrieval. Domain writes,
tenant authorization and monetary calculations are unchanged.
