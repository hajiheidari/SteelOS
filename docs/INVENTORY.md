# Inventory operations — approved M2 warehouse scope

The founder approved the warehouse proposal and admin-only posting after M1 acceptance.
This is the limited warehouse scope, not the broader trading/accounting roadmap.

## Persistence and authority

`inventory_lots` identify an immutable product, unit and legal owner (`company` or a
specified tenant party). A lot can span physical positions; location never determines
ownership. Product technical specifications/unit cannot change after a lot exists.
Editors/admins create lots and immutable-payload drafts. Editors require grants for
all referenced warehouses; only admins post/reject. Viewers see positions in granted
warehouses. Editors can read tenant lot identity metadata without a position grant;
quantities and draft legs remain warehouse-filtered. Both transfer warehouses must be
visible. Organization membership is rechecked and locked for every mutation/replay.

`inventory_drafts` transition once from draft to posted/rejected. Correction of an
unposted draft means reject/new. `inventory_entries` are append-only signed deltas of
on-hand, blocked and reserved quantities; no balance write API exists. `inventory_reservations`
are immutable holds with UTC expiry. PostgreSQL triggers reject ledger update/delete,
lot/reservation mutation and terminal draft changes. Tenant/lot/location compound FKs
prevent cross-tenant references. Database owners/superusers can bypass triggers; operational
DB credentials must not be shared with agents or end users. Backup/restore remains an
operator responsibility; no automatic ledger retention/deletion is provided.

## Operations and invariants

Receipt adds on-hand; dispatch removes on-hand; transfer atomically debits/credits two
positions without changing ownership. Block/unblock change blocked quantity. Reserve
creates a hold, release reduces its remaining quantity, fulfill reduces both held and
on-hand quantity. Release/fulfill derive their position from the reservation. Reversal
negates all legs of one posted operation, for its full quantity, at most once; reversal
of reversal is rejected. Dependent activity can prevent reversal. Create a new valid
operation after correction rather than altering history.

All posting locks the lot before validating positions, serializing concurrent consumption
and transfer for that lot. Each resulting position must satisfy `on_hand >= blocked +
active_reserved >= 0`, with each component nonnegative. Reservation remaining stays
between zero and its original quantity. Expired reservations are ignored in available
stock automatically, without a scheduler, but retain historical outstanding quantities;
release can close expired history, fulfill cannot consume it. A reversal restoring an
expired reservation does not renew its expiry. Quantities are exact NUMERIC(20,3), sent
as decimal strings; piece quantities are integral. There is no implicit unit conversion.

Posting time comes from the database UTC clock; client backdating is unavailable. Draft,
posting, audit and idempotency changes commit atomically. Retried posting never duplicates
legs. Audit events record actor/action/entity. History does not represent accounting
valuation or evidence of legal title transfer.

## API

All paths below are under `/api/v1/inventory`; bearer authorization is mandatory.

- `GET|POST /lots`: code, product_id, owner_kind, optional owner_party_id, unit.
- `GET|POST /drafts`: lot_id, kind, quantity, reference, optional note. Receipt requires
  to_location_id; dispatch/block/unblock/reserve require from_location_id; transfer
  requires both distinct positions. Reserve requires future timezone-aware expires_at.
  Release/fulfill require reservation_id and no client position. Reversal requires
  reverses_id, same lot and full original quantity, and no client position.
- `POST /drafts/{id}/post` and `/reject`: admin only, no body.
- `GET /lots/{id}`, `/drafts/{id}`, `/entries/{id}`, `/reservations/{id}`.
- `GET /entries`, `/reservations`: immutable history; reservation lists include remaining/expired.
- `GET /balances`: grouped lot/warehouse/location with owner_kind, owner_party_id,
  product_id, unit, on_hand, blocked, reserved, available and server as_of.

All writes require `Idempotency-Key` (maximum 100 characters); reuse with another payload
returns 409. Lists use limit (1–100, default 25), offset and total. Filters include lot_id,
product_id and warehouse_id where meaningful; status is draft-only. Unsupported filters
return 422. Lots have no warehouse filter because their identity is location-independent.
Errors follow the common structured API envelope. Conflicting stock/expiry/terminal-state
operations return 409; invalid request shapes return 422; inaccessible records return404.

## UI and validation

The Persian inventory workspace shows derived balances, ownership, drafts, ledger and
reservations. Draft forms normalize Persian decimal input as strings. Posting/rejection
requires an explicit admin confirmation showing quantity, owner and physical positions.
No editable stock balance is exposed. Read the actual backend OpenAPI for field limits.
Backend integration tests cover tenant/warehouse isolation, database guards, expiry,
idempotency, reversal dependencies and concurrent consumption. Browser tests cover
receipt draft, no balance effect before approval, explicit posting, reservation fulfillment/
release, block/unblock, cross-warehouse transfer, reversal and rejection of excessive
dispatch with unchanged stock. Persian decimal quantities are verified through the API.

Trading documents, valuation/accounting, tax filing, title transfer, backdating, partial
reversal, configurable approval chains and public deployment remain outside this scope.

## Master changes and warehouse grant revocation

Posting holds shared row locks on the validated product, third-party owner, warehouses
and locations until commit. A preceding uncommitted deactivation is awaited and rechecked;
posting fails without ledger effects if the master is now inactive. Independent postings
can share these validation locks. Warehouse is locked before location, matching hierarchy
edits. Warehouse grant checks used by mutations also hold a shared grant lock: a preceding
revocation is awaited and denied, while a mutation already holding the grant finishes
before revocation. This policy does not retroactively cancel committed drafts or history.
