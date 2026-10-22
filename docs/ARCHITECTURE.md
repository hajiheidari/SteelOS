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
