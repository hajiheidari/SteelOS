# Catalog dimension query measurements

This is a reproducible, opt-in PostgreSQL experiment with synthetic data, not a production
latency promise. It exercises the same catalog_search predicates as the product endpoint,
but excludes HTTP, authentication, source-name hydration, response serialization, assistant
inference and price retrieval. It is a single-client warm-cache run without concurrent load.

## Reproduce

Use a separate local PostgreSQL database named with the suffix `_benchmark`, containing
no organizations. Apply the normal Alembic migrations to it first. Do not point the tool
at a business database or run destructive integration/browser fixtures against it.
From the repository root, with DATABASE_URL set to that database:

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/benchmark_catalog_search.py \
  --rows-per-org 5000 --repeats 10 --output /tmp/catalog-query-benchmark.json
```

The tool seeds two organizations with5000 products each, distributed across mm/cm/m
categories with canonical Decimal attribute strings, unique lengths, and some inactive rows.
It runs exact, inclusive mixed-unit and empty-interior filters. Each measurement includes a
count plus a deterministic five-row page, with assertions for expected count, page size and
tenant identity. EXPLAIN ANALYZE/BUFFERS JSON plans accompany each query. It rejects another
database suffix or existing organizations, bounds seed/repeat sizes and imposes a15s SQL
statement timeout. A finally block rolls back all synthetic organizations/references/products;
post-rollback counts are verified. The database/schema itself remains available for reuse.
The benchmark is not collected by pytest or run in ordinary CI and has no timing pass/fail gate.

## Recorded experiment — 2026-10-24

Ten repeats per case,10000 total products,5000 in the queried organization. Values below
are combined count/page milliseconds; the JSON artifacts contain PostgreSQL version and
full plans. p95 with only ten samples is the maximum sample and is particularly noisy.

| Query | Baseline median / p95 | Selected CASE branch median / p95 |
| --- | --- | --- |
| Exact2mm |32.882 /45.220 |34.571 /46.133 |
| Inclusive2–3mm, lower bound0.2cm |190.272 /200.854 |173.702 /202.111 |
| Empty2.000001–2.999999mm |182.607 /194.002 |172.643 /192.291 |

A first attempt multiplied the stored quantity by a selected unit factor. It was slower
(263.692ms median for the inclusive case) and was discarded. Its artifact remains explicit
negative evidence. The selected implementation uses CASE to select one known unit before
checking bounds, retaining the nested regex-guarded numeric CASE and JSON string-type check.
There is no new index, schema, unit-conversion policy, financial arithmetic or infrastructure.

The observed medians improved modestly for ranges; inclusive p95 did not improve and exact
search was unchanged in code. These small sequential samples do not establish statistical
significance, production throughput or acceptable latency for a larger tenant. Tenant scans
remain possible. Query plans and representative larger/concurrent workloads should guide
any future indexed dimension projection; no such index is claimed here.

Evidence:

- [Baseline](evidence/catalog-query-baseline-2026-10-24.json)
- [Discarded normalization attempt](evidence/catalog-query-normalized-attempt-2026-10-24.json)
- [Selected branch implementation](evidence/catalog-query-benchmark-2026-10-24.json)

## Registered identifier search — baseline, 2026-10-25

The same opt-in tool now accepts --identifier-search. It seeds two identifiers (barcode and
vendor) per product with identical literal values containing %, _ and backslash; both tenants
have the same values. This adds direct name/SKU, identifier, missing-identifier and combined
identifier/range cases. The endpoint and benchmark share apply_text_search, so the experiment
uses the actual bound text predicate. All original dimension cases still run unchanged.

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/tests/benchmark_catalog_search.py \
  --rows-per-org 5000 --repeats 5 --identifier-search \
  --output /tmp/catalog-identifiers.json
```

This baseline used correlated EXISTS,10000 total products and20000 identifiers, with five
combined count/page samples per case. Median/p95 milliseconds: name199.787/700.045,
SKU222.238/238.641, literal identifier231.789/232.184, missing identifier221.519/222.720,
identifier plus2–3mm range635.917/653.403. Plans show a very high estimated outer cost and
substantial JIT compilation even for direct-name matches whose identifier subplan never ran.
PostgreSQL used a hashed identifier subplan, not one executed scan per product; no quadratic
execution claim is made. No PostgreSQL/JIT configuration was changed.

Count, five-row page size and tenant identity were asserted in every repetition, including
multiple aliases without count inflation. All synthetic organizations/products/identifiers
rolled back and absence was verified. This is query-only, single-client, small-sample evidence;
no API, concurrency or production SLO is measured. No new index is justified by this run.
Baseline plans: [catalog-identifiers-baseline-2026-10-25.json](evidence/catalog-identifiers-baseline-2026-10-25.json).

### Selected product-ID membership predicate

The baseline implementation/tool is reproducible at227e1fe. The selected implementation
replaces only the identifier EXISTS term with Product.id IN (SELECT product_id WHERE
organization_id=:authorized_org AND value ILIKE :escaped_pattern). The outer tenant scope,
name/SKU OR terms, dimensions, ordering and pagination remain intact. IN membership does
not duplicate products when several identifiers select the same ID; DISTINCT is unnecessary.
No index, migration, cache, JIT override or new service was introduced.

Five repeats per case on the same isolated PostgreSQL17 database with the same synthetic
size/distribution and default settings produced the following count+five-row-page times.
The first sample is included; p95 with five samples is the maximum and particularly noisy.

| Query | EXISTS median / p95 (ms) | ID membership median / p95 (ms) |
| --- | --- | --- |
| Direct name |199.787 /700.045 |5.598 /8.819 |
| SKU substring |222.238 /238.641 |13.003 /15.228 |
| Literal identifier substring |231.789 /232.184 |15.399 /16.035 |
| Missing identifier |221.519 /222.720 |14.742 /14.880 |
| Identifier + mixed-unit2–3mm range |635.917 /653.403 |189.639 /192.036 |
| Exact2mm (control, no text) |33.495 /43.703 |32.030 /42.863 |
| Mixed-unit2–3mm range (control, no text) |167.416 /182.737 |164.237 /170.102 |
| Empty range (control, no text) |157.496 /158.763 |158.067 /163.468 |

Plans retain a hashed identifier subplan but remove the inflated correlated-plan cost and
JIT compilation seen in this run. Identifier/tenant substring scans and range work remain;
this does not make search constant-time or prove production scale, statistical significance,
throughput or API latency. Authentication, label hydration, HTTP and model inference are not
included. The existing API regressions cover tenant isolation, wildcards, alias rename/delete,
count/pagination and combination with dimensions; a new case combines name/SKU/duplicate aliases.
All experiment data rolled back and absence was verified after each run.
Selected plans: [catalog-identifiers-set-membership-2026-10-25.json](evidence/catalog-identifiers-set-membership-2026-10-25.json).

## Real HTTP API and bounded concurrency — 2026-10-25

`benchmark_catalog_api.py` runs an ephemeral Uvicorn worker on a pre-bound127.0.0.1 port,
with actual HTTP and independent PostgreSQL request transactions. It includes authentication
checks, query/count/page work, page-scoped reference labels, JSON serialization and loopback
transport; excludes login/seed/warmup timing, Next.js proxy/UI, TLS/WAN and model inference.
No installed model, paid service, new dependency or public listener is needed.

```sh
DATABASE_URL=postgresql+psycopg://steelos:steelos@localhost:5432/steelos_benchmark \
  PYTHONPATH=apps/api .venv/bin/python apps/api/tests/benchmark_catalog_api.py \
  --rows-per-org 5000 --repeats 10 --concurrency 1 4 \
  --output /tmp/catalog-api.json
```

Both benchmark tools now share a session advisory lock and reject a non-_benchmark database,
a populated organization table or another cooperating benchmark. API bounds:100–50000 products
per tenant,3–20 repeats, unique concurrency levels from1/2/4,30s HTTP timeout,15s SQL timeout
and bounded graceful server shutdown. It creates two synthetic viewer accounts and logs in
through the real API. Auth/password/token values never enter the report. Two identical
identifier kinds per product and identical alias values across tenants exercise cardinality
and scope. Every response asserts exact expected IDs/order/count/attributes, tenant identity,
category labels/rules and no-store headers. Workloads alternate tenants and rotate case order.

The HTTP tool must commit its synthetic seed so concurrent transactions can see it. It stops
its server, then deletes only generated organization/user scopes and known login-attempt keys,
verifying absence of all seeded/auth/audit records. It never truncates a database or disables
FK/history guards. Unexpected business history causes cleanup to fail/roll back; do not bypass
that guard. An abrupt process/host kill can leave committed fixtures: inspect/recreate the
isolated disposable database before reuse. Normal/error cleanup is not crash recovery or a
business deletion policy. The query-only tool still uses rollback rather than committed seeding.

PostgreSQL17.11,10000 total products/20000 identifiers, one API process, closed-loop clients:
40 timed requests at concurrency1 and160 at concurrency4. Eight case/tenant warmups and two
logins were outside timing. Every request passed the correctness assertions; cleanup passed.

| API case |1 client median / p95 (ms),10 samples |4 clients median / p95 (ms),40 samples |
| --- | --- | --- |
| Name |55.860 /59.739 |63.999 /96.774 |
| Literal identifier |67.934 /83.804 |98.681 /135.691 |
| Missing identifier |69.918 /72.094 |91.736 /139.523 |
| Identifier + mixed-unit2–3mm range |239.964 /248.016 |345.043 /447.924 |

Whole mixed-workload observed rates were9.241 and25.398 requests/s respectively. These short,
closed-loop, warm-cache samples on one development host are not production capacity, statistical
confidence, an acceptance SLO, a before/after API comparison or a benchmark of full assistant
inference. Query-only and HTTP numbers have different scope and must not be directly treated
as the same measurement. Larger/representative operational load remains a future production
readiness exercise; no additional index, cache, service or database tuning was inferred here.
Evidence: [catalog-api-loopback-2026-10-25.json](evidence/catalog-api-loopback-2026-10-25.json).
