# Data model plan

Schemas: `core`, `catalog`, `partners`, `warehouse`, `pricing`, `trading`, `accounting`, `documents`, `automation`, `audit`.

M1 entities: organizations, users, memberships, roles, permissions; manufacturers, grades, product categories, products and identifiers; parties, party roles and contacts; warehouses and hierarchical locations; price sources and price observations; audit events.

Each tenant-owned table includes organization_id; enforce tenant-aware FKs and permission checks. Physical location and legal owner are separate. Lot stock movements are the source of truth, not mutable balance counters. Currency amounts use NUMERIC; kg weights use NUMERIC(20,3). Future journals must be balanced and immutable after posting.
